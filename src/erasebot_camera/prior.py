"""Rasterize already-known drawing strokes using teammate calibration.

No camera calibration is estimated here. The caller provides a verified
homography mapping board XY (its documented units) to camera pixels.
"""

from collections.abc import Mapping, Sequence

import cv2
import numpy as np


def rasterize_strokes(stroke_list: Mapping | Sequence, board_to_pixel: np.ndarray,
                      image_size: tuple[int, int], pen_width_px: int = 5) -> np.ndarray:
    """Create a uint8 ink prior from DrawBot-style points.

    Accepts {"strokes": [{"points": [[x,y], ...]}, ...]} or a list of strokes.
    Each point can be [x,y], [x,y,z] (z ignored), or {"x":..., "y":...}.
    H is a 3x3 homography from board XY to image pixel XY. image_size
    is (height, width). Coordinate conventions must come from Calibration.
    """
    H = np.asarray(board_to_pixel, dtype=np.float64)
    if H.shape != (3, 3) or not np.all(np.isfinite(H)):
        raise ValueError("board_to_pixel must be a finite 3x3 homography")
    height, width = image_size
    if height <= 0 or width <= 0 or pen_width_px <= 0:
        raise ValueError("image_size and pen_width_px must be positive")
    strokes = stroke_list.get("strokes", []) if isinstance(stroke_list, Mapping) else stroke_list
    mask = np.zeros((height, width), dtype=np.uint8)
    for stroke in strokes:
        points = stroke.get("points", []) if isinstance(stroke, Mapping) else stroke
        xy = []
        for point in points:
            p = [point["x"], point["y"]] if isinstance(point, Mapping) else point
            if len(p) < 2:
                raise ValueError("Each stroke point needs x,y coordinates")
            xy.append((float(p[0]), float(p[1])))
        if not xy:
            continue
        array = np.asarray(xy, dtype=np.float64)
        if not np.all(np.isfinite(array)):
            raise ValueError("Stroke points must be finite")
        transformed = cv2.perspectiveTransform(array.reshape(-1, 1, 2), H).reshape(-1, 2)
        if not np.all(np.isfinite(transformed)):
            raise ValueError("Stroke mapping produced invalid coordinates")
        vertices = np.rint(transformed).astype(np.int32)
        if len(vertices) == 1:
            cv2.circle(mask, tuple(vertices[0]), max(1, pen_width_px // 2), 255, -1)
        else:
            cv2.polylines(mask, [vertices], False, 255, thickness=pen_width_px,
                          lineType=cv2.LINE_8)
    return mask
