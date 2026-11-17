"""Camera inspection module for the IMPL EraseBot."""

from .detection import DetectionConfig, InspectionResult, inspect_erasure
from .service import CameraInspector
from .prior import rasterize_strokes

__all__ = ["DetectionConfig", "InspectionResult", "inspect_erasure", "CameraInspector", "rasterize_strokes"]
