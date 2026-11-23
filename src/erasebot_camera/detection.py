"""Fixed-pose whiteboard inspection using empty/drawn/erased RGB snapshots.

All image arrays use OpenCV BGR channel order. Bounding boxes are pixel
coordinates (x_min, y_min, x_max, y_max) with exclusive upper bounds.
No robot motions or calibration are performed here.
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class DetectionConfig:
    ink_threshold: float = 22.0
    residual_threshold: float = 18.0
    clean_ratio_threshold: float = 0.025
    min_original_pixels: int = 30
    min_component_pixels: int = 6
    significant_component_pixels: int = 40
    prior_dilate_px: int = 12
    residual_search_px: int = 10
    max_brightness_shift: float = 30.0

    def __post_init__(self) -> None:
        if self.ink_threshold <= 0 or self.residual_threshold <= 0:
            raise ValueError("Color-difference thresholds must be positive")
        if not 0 <= self.clean_ratio_threshold <= 1:
            raise ValueError("clean_ratio_threshold must be in [0, 1]")
        if self.min_original_pixels < 1 or self.min_component_pixels < 1 or self.significant_component_pixels < 1:
            raise ValueError("Minimum pixel counts must be positive")
        if self.prior_dilate_px < 0 or self.residual_search_px < 0:
            raise ValueError("Dilation distances cannot be negative")
        if self.max_brightness_shift <= 0:
            raise ValueError("max_brightness_shift must be positive")


@dataclass
class InspectionResult:
    status: str
    residual_ratio: Optional[float]
    original_pixels: int
    residual_pixels: int
    residual_regions: list[dict[str, Any]] = field(default_factory=list)
    residual_mask: Optional[np.ndarray] = field(default=None, repr=False)
    reason: str = ""
    brightness_shift: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """JSON-compatible summary; pixel mask is deliberately not serialized."""
        return {
            "status": self.status,
            "residual_ratio": self.residual_ratio,
            "original_pixels": self.original_pixels,
            "residual_pixels": self.residual_pixels,
            "residual_regions": self.residual_regions,
            "reason": self.reason,
            "brightness_shift": self.brightness_shift,
        }


def _validate_images(empty: np.ndarray, drawn: np.ndarray, erased: np.ndarray) -> None:
    if any(not isinstance(im, np.ndarray) for im in (empty, drawn, erased)):
        raise TypeError("Images must be NumPy arrays")
    if any(im.ndim != 3 or im.shape[2] != 3 or im.dtype != np.uint8 for im in (empty, drawn, erased)):
        raise ValueError("Images must be uint8 BGR arrays with shape (H, W, 3)")
    if drawn.shape != empty.shape or erased.shape != empty.shape:
        raise ValueError("Empty, drawn and erased images must have identical shape")


def _rectangle_mask(shape: tuple[int, int], roi: Optional[Sequence[int]]) -> np.ndarray:
    h, w = shape
    result = np.zeros((h, w), dtype=bool)
    if roi is None:
        result[:] = True
        return result
    if len(roi) != 4:
        raise ValueError("roi must be (x_min, y_min, x_max, y_max)")
    x1, y1, x2, y2 = [int(x) for x in roi]
    if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
        raise ValueError("ROI must be non-empty and inside the image")
    result[y1:y2, x1:x2] = True
    return result


def _expand(mask: np.ndarray, px: int) -> np.ndarray:
    if px == 0:
        return mask.copy()
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (px * 2 + 1, px * 2 + 1))
    return cv2.dilate(mask.astype(np.uint8), kernel) > 0


def _ink_signal(reference: np.ndarray, observed: np.ndarray) -> np.ndarray:
    """Ink contrast relative to a whiteboard baseline, incl. colored ink.

    The positive L-channel drop detects dark strokes. Chroma changes capture
    saturated markers. Noise is reduced by a 3x3 median blur.
    """
    reference_lab = cv2.cvtColor(reference, cv2.COLOR_BGR2LAB).astype(np.float32)
    observed_lab = cv2.cvtColor(observed, cv2.COLOR_BGR2LAB).astype(np.float32)
    darkness = np.maximum(reference_lab[:, :, 0] - observed_lab[:, :, 0], 0.0)
    chroma = np.linalg.norm(reference_lab[:, :, 1:3] - observed_lab[:, :, 1:3], axis=2)
    signal = np.maximum(darkness, chroma * 0.75)
    return cv2.medianBlur(np.clip(signal, 0, 255).astype(np.uint8), 3)


def _components(mask: np.ndarray, minimum: int) -> tuple[np.ndarray, list[dict[str, Any]]]:
    total, labels, stats, centroids = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    retained = np.zeros(mask.shape, dtype=np.uint8)
    regions = []
    for index in range(1, total):
        x, y, w, h, area = [int(v) for v in stats[index]]
        if area < minimum:
            continue
        retained[labels == index] = 255
        regions.append({
            "bbox": [x, y, x + w, y + h],
            "area_px": area,
            "centroid_px": [float(v) for v in centroids[index]],
        })
    regions.sort(key=lambda item: item["area_px"], reverse=True)
    return retained, regions


def inspect_erasure(
    empty_bgr: np.ndarray,
    drawn_bgr: np.ndarray,
    erased_bgr: np.ndarray,
    *,
    roi: Optional[Sequence[int]] = None,
    expected_mask: Optional[np.ndarray] = None,
    config: Optional[DetectionConfig] = None,
) -> InspectionResult:
    """Inspect a selected area; returned status is CLEAN/RESIDUAL/UNCERTAIN.

    Use the *same stationary inspection pose* for all three frames. The user
    ROI is pixel coordinates, not robot coordinates. If provided, expected_mask
    is a (H,W) binary image derived from drawing geometry; it narrows the search
    after dilation to account for drawing and calibration inaccuracies.
    """
    cfg = config or DetectionConfig()
    _validate_images(empty_bgr, drawn_bgr, erased_bgr)
    h, w = empty_bgr.shape[:2]
    roi_mask = _rectangle_mask((h, w), roi)

    if expected_mask is not None:
        if not isinstance(expected_mask, np.ndarray) or expected_mask.shape != (h, w):
            raise ValueError("expected_mask must be a (H, W) NumPy array")
        prior = _expand(expected_mask > 0, cfg.prior_dilate_px)
        search_mask = roi_mask & prior
    else:
        search_mask = roi_mask

    # A global camera auto-exposure jump invalidates naive frame subtraction.
    # In that situation, report uncertainty rather than asserting CLEAN.
    baseline_l = cv2.cvtColor(empty_bgr, cv2.COLOR_BGR2LAB)[:, :, 0].astype(np.float32)
    after_l = cv2.cvtColor(erased_bgr, cv2.COLOR_BGR2LAB)[:, :, 0].astype(np.float32)
    white_reference = (baseline_l > 175) & roi_mask
    if not np.any(white_reference):
        white_reference = roi_mask
    brightness_shift = float(np.median(after_l[white_reference] - baseline_l[white_reference]))
    if abs(brightness_shift) > cfg.max_brightness_shift:
        return InspectionResult("UNCERTAIN", None, 0, 0, reason="Large brightness shift; recapture at fixed exposure", brightness_shift=brightness_shift)

    original_signal = _ink_signal(empty_bgr, drawn_bgr)
    erased_signal = _ink_signal(empty_bgr, erased_bgr)
    original_mask = (original_signal >= cfg.ink_threshold) & search_mask
    original_pixels = int(original_mask.sum())
    if original_pixels < cfg.min_original_pixels:
        return InspectionResult("UNCERTAIN", None, original_pixels, 0, reason="Insufficient original ink in selected area", brightness_shift=brightness_shift)

    # The search halo includes ink smeared a few pixels away from a stroke.
    vicinity = _expand(original_mask, cfg.residual_search_px) & roi_mask
    if expected_mask is not None:
        vicinity &= _expand(search_mask, cfg.residual_search_px)
    candidates = (erased_signal >= cfg.residual_threshold) & vicinity
    residual_mask, regions = _components(candidates, cfg.min_component_pixels)
    count = int(np.count_nonzero(residual_mask))
    ratio = count / original_pixels
    has_significant_blob = any(region["area_px"] >= cfg.significant_component_pixels for region in regions)
    status = "CLEAN" if ratio <= cfg.clean_ratio_threshold and not has_significant_blob else "RESIDUAL"
    return InspectionResult(status, round(ratio, 5), original_pixels, count,
                            regions, residual_mask, brightness_shift=brightness_shift)


def make_overlay(image_bgr: np.ndarray, result: InspectionResult) -> np.ndarray:
    """Visual inspection overlay; red pixels and boxes mark detected residue."""
    if not isinstance(image_bgr, np.ndarray) or image_bgr.ndim != 3:
        raise ValueError("Expected BGR image")
    overlay = image_bgr.copy()
    if result.residual_mask is None:
        return overlay
    if result.residual_mask.shape != overlay.shape[:2]:
        raise ValueError("Result mask and image size differ")
    pixels = result.residual_mask > 0
    overlay[pixels] = (0.4 * overlay[pixels] + 0.6 * np.array([0, 0, 255])).astype(np.uint8)
    for region in result.residual_regions:
        x1, y1, x2, y2 = region["bbox"]
        cv2.rectangle(overlay, (x1, y1), (x2 - 1, y2 - 1), (0, 0, 255), 1)
    return overlay
