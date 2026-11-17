"""Thin integration API; no dependencies on pylibfranka or a specific UI."""

from pathlib import Path
from typing import Optional, Sequence

import cv2
import numpy as np

from .detection import DetectionConfig, InspectionResult, inspect_erasure, make_overlay


class CameraInspector:
    def __init__(self, config: Optional[DetectionConfig] = None):
        self.config = config or DetectionConfig()

    def inspect(self, empty_bgr: np.ndarray, drawn_bgr: np.ndarray,
                erased_bgr: np.ndarray, *, roi: Optional[Sequence[int]] = None,
                expected_mask: Optional[np.ndarray] = None) -> InspectionResult:
        return inspect_erasure(empty_bgr, drawn_bgr, erased_bgr, roi=roi,
                               expected_mask=expected_mask, config=self.config)

    def inspect_files(self, empty_path: str | Path, drawn_path: str | Path,
                      erased_path: str | Path, *, roi: Optional[Sequence[int]] = None,
                      expected_mask_path: Optional[str | Path] = None,
                      overlay_path: Optional[str | Path] = None) -> InspectionResult:
        images = []
        for filename in (empty_path, drawn_path, erased_path):
            image = cv2.imread(str(filename), cv2.IMREAD_COLOR)
            if image is None:
                raise FileNotFoundError(f"Cannot read image: {filename}")
            images.append(image)
        prior = None
        if expected_mask_path is not None:
            prior = cv2.imread(str(expected_mask_path), cv2.IMREAD_GRAYSCALE)
            if prior is None:
                raise FileNotFoundError(f"Cannot read expected mask: {expected_mask_path}")
        result = self.inspect(*images, roi=roi, expected_mask=prior)
        if overlay_path is not None:
            target = Path(overlay_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(target), make_overlay(images[-1], result)):
                raise OSError(f"Cannot write overlay: {target}")
        return result
