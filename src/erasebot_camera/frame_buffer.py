"""Thread-safe RGB frame buffer; independent of ROS 2 imports."""
from threading import Condition
import numpy as np


class FrameBuffer:
    """Return only a new frame received after the snapshot request."""

    def __init__(self) -> None:
        self._cv = Condition()
        self._sequence = 0
        self._image: np.ndarray | None = None

    def push(self, frame: np.ndarray) -> None:
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must be BGR (H, W, 3)")
        if frame.dtype != np.uint8:
            raise ValueError("frame must have dtype uint8")
        with self._cv:
            self._image = frame.copy()
            self._sequence += 1
            self._cv.notify_all()

    def wait_for_next(self, timeout_sec: float) -> np.ndarray:
        if timeout_sec <= 0:
            raise ValueError("timeout_sec must be positive")
        with self._cv:
            before = self._sequence
            if not self._cv.wait_for(lambda: self._sequence > before, timeout_sec):
                raise TimeoutError("No new RGB frame arrived after capture request")
            assert self._image is not None
            return self._image.copy()
