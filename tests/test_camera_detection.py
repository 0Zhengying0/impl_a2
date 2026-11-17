import cv2
import numpy as np
import pytest

from erasebot_camera import CameraInspector, DetectionConfig, inspect_erasure
from erasebot_camera.detection import make_overlay


def frames():
    blank = np.full((160, 240, 3), 245, dtype=np.uint8)
    drawn = blank.copy()
    cv2.line(drawn, (30, 70), (190, 70), (15, 15, 15), 5)
    return blank, drawn


def test_completely_clean():
    blank, drawn = frames()
    result = inspect_erasure(blank, drawn, blank.copy())
    assert result.status == "CLEAN"
    assert result.residual_ratio == 0
    assert result.original_pixels > 100
    assert result.residual_regions == []


def test_partial_residue_and_overlay():
    blank, drawn = frames()
    erased = blank.copy()
    cv2.line(erased, (75, 70), (140, 70), (95, 95, 95), 3)
    result = inspect_erasure(blank, drawn, erased)
    assert result.status == "RESIDUAL"
    assert result.residual_pixels > 20
    assert result.residual_regions[0]["area_px"] > 20
    assert make_overlay(erased, result).shape == erased.shape
    assert "residual_mask" not in result.to_dict()


def test_roi_outside_ink_is_uncertain():
    blank, drawn = frames()
    result = inspect_erasure(blank, drawn, blank, roi=(0, 0, 20, 20))
    assert result.status == "UNCERTAIN"
    assert result.residual_ratio is None


def test_erase_only_part_of_drawing():
    blank, drawn = frames()
    erased = drawn.copy()
    erased[:, 70:] = blank[:, 70:]
    cleaned = inspect_erasure(blank, drawn, erased, roi=(90, 45, 200, 95))
    not_cleaned = inspect_erasure(blank, drawn, erased, roi=(25, 45, 65, 95))
    assert cleaned.status == "CLEAN"
    assert not_cleaned.status == "RESIDUAL"


def test_expected_mask_limits_search():
    blank, drawn = frames()
    expected = np.zeros(blank.shape[:2], dtype=np.uint8)
    expected[62:78, 50:95] = 255
    result = inspect_erasure(blank, drawn, drawn, expected_mask=expected)
    assert result.status == "RESIDUAL"
    assert result.original_pixels < inspect_erasure(blank, drawn, drawn).original_pixels


def test_bad_shapes_and_roi_raise():
    blank, drawn = frames()
    with pytest.raises(ValueError):
        inspect_erasure(blank, drawn[:-1], blank)
    with pytest.raises(ValueError):
        inspect_erasure(blank, drawn, blank, roi=(0, 0, 999, 100))
    with pytest.raises(ValueError):
        inspect_erasure(blank, drawn, blank, expected_mask=np.ones((2, 2)))
    with pytest.raises(ValueError):
        DetectionConfig(clean_ratio_threshold=1.1)


def test_large_exposure_shift_is_uncertain():
    blank, drawn = frames()
    dark_frame = np.full_like(blank, 170)
    result = inspect_erasure(blank, drawn, dark_frame)
    assert result.status == "UNCERTAIN"
    assert "brightness" in result.reason.lower()


def test_file_roundtrip(tmp_path):
    blank, drawn = frames()
    for name, image in (("empty", blank), ("drawn", drawn), ("erased", blank)):
        cv2.imwrite(str(tmp_path / f"{name}.png"), image)
    result = CameraInspector().inspect_files(*(tmp_path / f"{n}.png" for n in ("empty", "drawn", "erased")),
                                             overlay_path=tmp_path / "overlay.png")
    assert result.status == "CLEAN"
    assert (tmp_path / "overlay.png").exists()


def test_large_local_residue_even_when_global_ratio_is_small():
    blank = np.full((200, 200, 3), 240, dtype=np.uint8)
    drawn = blank.copy()
    cv2.rectangle(drawn, (15, 15), (185, 185), (0, 0, 0), -1)
    erased = blank.copy()
    cv2.line(erased, (40, 40), (100, 40), (15, 15, 15), 2)
    result = inspect_erasure(blank, drawn, erased)
    assert result.residual_ratio < 0.025
    assert result.status == "RESIDUAL"


def test_rasterize_known_strokes():
    from erasebot_camera import rasterize_strokes
    strokes = {"strokes": [
        {"points": [{"x": 10, "y": 20}, {"x": 50, "y": 20}]},
        {"points": [[30, 30, 0]]},
    ]}
    prior = rasterize_strokes(strokes, np.eye(3), (80, 100), 3)
    assert prior[20, 25] == 255
    assert prior[30, 30] == 255
    assert prior[5, 5] == 0
    with pytest.raises(ValueError):
        rasterize_strokes(strokes, np.eye(2), (80, 100))


def test_camera_capture_requires_start():
    from erasebot_camera.capture import RealSenseCamera
    with pytest.raises(RuntimeError, match="start"):
        RealSenseCamera().capture()
