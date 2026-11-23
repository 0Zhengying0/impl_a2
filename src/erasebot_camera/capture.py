"""Optional RealSense D435 RGB acquisition (no robot movement)."""

from pathlib import Path
from typing import Optional

import cv2
import numpy as np


class RealSenseCamera:
    """Access the D435 directly via pyrealsense2, not via an active ROS driver.

    The robot controller must confirm that the inspection pose was reached and
    the arm is stationary before capture() is called.
    """

    def __init__(self, width: int = 640, height: int = 480, fps: int = 30,
                 warmup_frames: int = 20, serial: Optional[str] = None):
        self.width, self.height, self.fps = width, height, fps
        self.warmup_frames, self.serial = warmup_frames, serial
        self._pipeline = None

    def start(self) -> "RealSenseCamera":
        if self._pipeline is not None:
            raise RuntimeError("Camera already started")
        try:
            import pyrealsense2 as rs
        except ImportError as exc:
            raise RuntimeError("Install pyrealsense2 on the computer connected to D435") from exc
        pipeline = rs.pipeline()
        settings = rs.config()
        if self.serial:
            settings.enable_device(self.serial)
        settings.enable_stream(rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps)
        pipeline.start(settings)
        self._pipeline = pipeline
        try:
            for _ in range(self.warmup_frames):
                pipeline.wait_for_frames(timeout_ms=5000)
        except Exception:
            self.stop()
            raise
        return self

    def capture(self, output_path: Optional[str | Path] = None) -> np.ndarray:
        if self._pipeline is None:
            raise RuntimeError("Call start() before capture()")
        frames = self._pipeline.wait_for_frames(timeout_ms=5000)
        color = frames.get_color_frame()
        if not color:
            raise RuntimeError("D435 returned no RGB frame")
        image = np.asanyarray(color.get_data()).copy()
        if output_path is not None:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(target), image):
                raise OSError(f"Could not save image to {target}")
        return image

    def stop(self) -> None:
        if self._pipeline is not None:
            self._pipeline.stop()
            self._pipeline = None

    def __enter__(self) -> "RealSenseCamera":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()
