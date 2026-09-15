"""M11 — Local Telemetry Gateway & Server.

Streams pipeline state (TelemetryMessage) over WebSockets to mobile and desktop
dashboards in real-time. Serves the web dashboard as static files over HTTP.

Rules (from PROTOCOL.md & Engineering Blueprint):
1. Never block the safety loop — broadcasts are queued and dispatched asynchronously.
2. Disconnected, late-connecting, or slow clients are handled gracefully and dropped if necessary.
3. Completely removable — the safety pipeline operates normally even if TelemetryServer is not running.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import threading
import time
from typing import Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from spatialvector.hmi.schemas import TelemetryMessage

logger = logging.getLogger(__name__)


class TelemetryServer:
    """FastAPI & WebSocket server for streaming telemetry to the phone dashboard."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        stale_threshold_s: float = 1.5,
    ):
        self.host = host
        self.port = port
        self.stale_threshold_s = stale_threshold_s

        self.app = FastAPI(title="SpatialVector-HMI Telemetry")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self._active_connections: Set[WebSocket] = set()
        self._connections_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server_thread: Optional[threading.Thread] = None
        self._uvicorn_server: Optional[uvicorn.Server] = None
        self._stop_event = threading.Event()
        self._latest_message: Optional[dict] = None

        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/api/health")
        async def health():
            return {
                "status": "OK",
                "active_clients": len(self._active_connections),
                "timestamp": time.monotonic(),
            }

        @self.app.get("/api/source")
        async def get_source():
            try:
                from spatialvector.perception.source_resolver import resolve_camera_source, read_camera_source_file
                src, origin = resolve_camera_source()
                return {
                    "source": str(src),
                    "origin": origin,
                    "saved": read_camera_source_file(),
                }
            except Exception as e:
                return {"source": "0", "origin": "error", "error": str(e)}

        @self.app.post("/api/set-source")
        async def set_source(req: dict):
            try:
                from spatialvector.perception.source_resolver import write_camera_source_file
                val = req.get("source")
                if val:
                    p = write_camera_source_file(str(val).strip())
                    return {"status": "OK", "source": str(val).strip(), "path": str(p)}
                return {"status": "ERROR", "message": "Missing 'source'"}
            except Exception as e:
                return {"status": "ERROR", "error": str(e)}


        @self.app.websocket("/ws/telemetry")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            with self._connections_lock:
                self._active_connections.add(websocket)
            logger.info(f"[M11] WebSocket client connected. Total clients: {len(self._active_connections)}")

            # Send immediate latest state if available
            if self._latest_message:
                try:
                    await websocket.send_text(json.dumps(self._latest_message))
                except Exception:
                    pass

            try:
                while not self._stop_event.is_set():
                    # Keep connection open; read ping/pong or client messages
                    try:
                        data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
            except WebSocketDisconnect:
                pass
            except Exception as exc:
                logger.debug(f"[M11] Client connection closed: {exc}")
            finally:
                with self._connections_lock:
                    self._active_connections.discard(websocket)
                logger.info(f"[M11] WebSocket client disconnected. Remaining: {len(self._active_connections)}")

        # Mount web dashboard if it exists
        dashboard_dir = Path(__file__).resolve().parent.parent.parent / "web" / "dashboard"
        if dashboard_dir.exists():
            self.app.mount("/", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

    def start(self):
        """Starts uvicorn server in a daemon background thread."""
        self._stop_event.clear()
        self._server_thread = threading.Thread(target=self._run_server, daemon=True, name="TelemetryServer")
        self._server_thread.start()
        # Give server a brief moment to initialize
        time.sleep(0.15)
        logger.info(f"[M11] TelemetryServer running at http://{self.host}:{self.port}")

    def stop(self):
        """Stops uvicorn server and closes active websocket connections."""
        self._stop_event.set()
        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=2.0)
        with self._connections_lock:
            self._active_connections.clear()
        logger.info("[M11] TelemetryServer stopped.")

    def broadcast(self, message: TelemetryMessage) -> None:
        """Asynchronously dispatches TelemetryMessage to all connected WebSocket clients.

        Never blocks the caller.
        """
        payload = message.to_dict()
        self._latest_message = payload

        if not self._active_connections or not self._loop or not self._loop.is_running():
            return

        json_str = json.dumps(payload)

        # Schedule broadcast coroutine on the server's event loop
        try:
            self._loop.call_soon_threadsafe(self._async_broadcast, json_str)
        except RuntimeError:
            pass

    def _async_broadcast(self, json_str: str):
        with self._connections_lock:
            targets = list(self._active_connections)

        for ws in targets:
            try:
                asyncio.create_task(self._send_safe(ws, json_str))
            except Exception:
                pass

    async def _send_safe(self, ws: WebSocket, text: str):
        try:
            await ws.send_text(text)
        except Exception:
            with self._connections_lock:
                self._active_connections.discard(ws)

    def _run_server(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            loop="asyncio",
        )
        self._uvicorn_server = uvicorn.Server(config)
        try:
            self._loop.run_until_complete(self._uvicorn_server.serve())
        except Exception:
            pass
        finally:
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                self._loop.close()
            except Exception:
                pass

