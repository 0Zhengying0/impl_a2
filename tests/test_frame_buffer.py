import threading
import time
import numpy as np
import pytest
from erasebot_camera.frame_buffer import FrameBuffer


def test_returns_only_next_frame_and_copies_it():
    buffer = FrameBuffer()
    buffer.push(np.zeros((2, 3, 3), dtype=np.uint8))
    target = np.full((2, 3, 3), 7, dtype=np.uint8)
    thread = threading.Thread(target=lambda: (time.sleep(0.02), buffer.push(target)))
    thread.start()
    result = buffer.wait_for_next(0.5)
    thread.join()
    assert result[0, 0, 0] == 7
    result[0, 0, 0] = 99
    assert target[0, 0, 0] == 7


def test_timeout_if_no_new_frame():
    buffer = FrameBuffer()
    buffer.push(np.zeros((2, 3, 3), dtype=np.uint8))
    with pytest.raises(TimeoutError):
        buffer.wait_for_next(0.01)


def test_invalid_frame_and_timeout():
    buffer = FrameBuffer()
    with pytest.raises(ValueError):
        buffer.push(np.zeros((2, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        buffer.push(np.zeros((2, 3, 3), dtype=np.float64))
    with pytest.raises(ValueError):
        buffer.wait_for_next(0)
