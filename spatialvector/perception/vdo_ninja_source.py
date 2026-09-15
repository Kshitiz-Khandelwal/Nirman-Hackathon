"""
VDO.Ninja WebRTC Stream Capture Provider for SpatialVector-HMI.

Allows capturing live video from a remote phone streaming via VDO.Ninja
(e.g., https://vdo.ninja/?view=vYEkARC) into OpenCV in background.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class VdoNinjaCapture:
    """Connects to a VDO.Ninja view link in a headless Chromium process

    and extracts live video frames via HTML5 Video / Canvas in real-time.
    """

    def __init__(
        self,
        url: str,
        on_frame: Callable[[np.ndarray, float], None],
        target_fps: int = 30,
    ):
        self.url = url
        # Ensure clean playback parameters
        if "cleanoutput" not in self.url:
            sep = "&" if "?" in self.url else "?"
            self.url = f"{self.url}{sep}cleanoutput&autostart"

        self.on_frame = on_frame
        self.target_fps = target_fps
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.is_connected = False
        self.last_frame_time = 0.0

    def start(self) -> "VdoNinjaCapture":
        if self._thread is not None and self._thread.is_alive():
            return self

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.is_connected = False

    def _run_loop(self):
        """Run asyncio loop inside thread."""
        asyncio.run(self._async_capture())

    async def _async_capture(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright is required for VDO.Ninja capture. Run: pip install playwright")
            return

        async def _handle_frame(b64_data: str):
            t_cap = time.monotonic()
            self.last_frame_time = t_cap
            self.is_connected = True
            try:
                # b64_data format: "data:image/jpeg;base64,..."
                comma = b64_data.find(",")
                raw = base64.b64decode(b64_data[comma + 1 :])
                arr = np.frombuffer(raw, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is not None:
                    self.on_frame(img, t_cap)
            except Exception as e:
                logger.debug(f"Frame decode error: {e}")

        async with async_playwright() as p:
            logger.info(f"Launching headless Chrome for VDO.Ninja stream: {self.url}")
            browser = await p.chromium.launch(
                channel="chrome",
                headless=True,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            page = await browser.new_page()
            await page.expose_function("sendFrameToPython", _handle_frame)

            await page.goto(self.url)
            logger.info("Waiting for VDO.Ninja video element...")
            await page.wait_for_selector("video", timeout=30000)

            # Injected client script
            frame_interval_ms = int(1000.0 / self.target_fps) if self.target_fps > 0 else 33
            await page.evaluate(
                f"""() => {{
                const video = document.querySelector('video');
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                let running = true;
                window._stopVdo = () => {{ running = false; }};

                function grab() {{
                    if (!running) return;
                    if (video.videoWidth > 0 && video.videoHeight > 0) {{
                        canvas.width = video.videoWidth;
                        canvas.height = video.videoHeight;
                        ctx.drawImage(video, 0, 0);
                        const b64 = canvas.toDataURL('image/jpeg', 0.85);
                        window.sendFrameToPython(b64).then(() => {{
                            if ('requestVideoFrameCallback' in video) {{
                                video.requestVideoFrameCallback(grab);
                            }} else {{
                                setTimeout(grab, {frame_interval_ms});
                            }}
                        }}).catch(() => setTimeout(grab, 100));
                    }} else {{
                        setTimeout(grab, 200);
                    }}
                }}
                grab();
            }}"""
            )

            logger.info("VDO.Ninja streaming active.")
            while not self._stop_event.is_set():
                await asyncio.sleep(0.5)

            try:
                await page.evaluate("() => { if (window._stopVdo) window._stopVdo(); }")
            except Exception:
                pass
            await browser.close()
            self.is_connected = False
            logger.info("VDO.Ninja browser closed.")
