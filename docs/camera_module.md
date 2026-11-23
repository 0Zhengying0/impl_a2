# Camera module — fixed-pose EraseBot Basic

## Scope and assumptions

- RealSense D435 mounted eye-in-hand beside FR3 gripper; whiteboard stays horizontal and fixed.
- Robot controller uses `pylibfranka` and owns `move_to_inspection_pose()`. Camera **never commands the robot**.
- Acquire three BGR images at the **same stationary inspection pose**, with consistent illumination/exposure: `empty`, `drawn`, `erased`.
- Basic detection uses only OpenCV; YOLO/Grounded SAM are **not required**.
- `roi=(x1,y1,x2,y2)` uses **pixels** in the camera image, upper edges exclusive; it can come from Web UI rectangle selection.
- Optional `expected_mask` is a uint8/bool image derived from the old DrawBot `StrokeList` plus calibration; not a blocker for Basic. `rasterize_strokes()` can create this mask once Calibration supplies the board-XY-to-pixel homography.

## Local quick start (no camera or robot required)

From repo root:

```bash
python -m pip install -r requirements-camera.txt
PYTHONPATH=src python -m erasebot_camera.demo --synthetic --out camera_output
python -m pip install pytest
python -m pytest -q tests/test_camera_detection.py
```

`camera_output/` contains generated demo pictures, `result.json`, `overlay.png`, and `residual_mask.png` (when detection was possible). These are **synthetic smoke tests**, not evidence of real-world accuracy.

Run on photos taken from the same inspection pose:

```bash
PYTHONPATH=src python -m erasebot_camera.demo \
  --empty captures/empty.png --drawn captures/drawn.png \
  --erased captures/erased.png --roi 30 40 600 430 --out camera_output
```

If a calibrated trajectory mask is available, add `--expected-mask path/to/mask.png`.

## API

```python
from erasebot_camera import CameraInspector

result = CameraInspector().inspect(empty_bgr, drawn_bgr, erased_bgr,
                                   roi=(30, 40, 600, 430), expected_mask=None)
print(result.status, result.residual_ratio)
print(result.to_dict())       # serializable; excludes NumPy pixel mask
pixel_mask = result.residual_mask
```

`status` is `CLEAN`, `RESIDUAL`, or `UNCERTAIN`; `residual_ratio` is residual-mask pixels / original-ink pixels within the selected ROI, **not** a calibrated physical area or success probability. When `UNCERTAIN`, the ratio is `None`. `residual_regions` entries contain pixel `bbox=[x_min,y_min,x_max,y_max]`, `area_px`, and `centroid_px`. The residual mask uses uint8 0/255.

Prior generation once board-to-pixel homography is supplied by Calibration:

```python
import numpy as np
from erasebot_camera import rasterize_strokes

mask = rasterize_strokes({"strokes": [{"points": [[10, 20], [50, 20]]}]},
                         board_to_pixel=np.eye(3), image_size=(480, 640))
```

The identity matrix is **only an example**; never assume board units are pixels. Adapt stroke field names to the actual prior DrawBot repository before integration.

D435 direct acquisition on lab PC (do not run a ROS camera node simultaneously):

```python
from erasebot_camera.capture import RealSenseCamera

# Controller must move the arm to inspection pose and wait until stationary.
with RealSenseCamera(warmup_frames=30) as camera:
    image = camera.capture("captures/empty.png")
```

Install `pyrealsense2` only on a system connected to a supported D435. The import is lazy, so offline unit tests don't need RealSense or ROS 2. If the team elects to use `/camera/color/image_raw` through ROS 2, pass the converted `cv_bridge` BGR NumPy frame directly into `CameraInspector.inspect` instead of opening the camera twice.

## Data contracts needed from teammates

1. **Trajectory/robot control**: a safe, repeatable inspection pose and a *motion complete + arm stationary* acknowledgment; no joint angles required by Camera. Optional prior drawing StrokeList in board coordinates.
2. **Calibration**: mapping from whiteboard XY (with units and origin) to image pixels. Only necessary for accurately rasterizing StrokeList or for converting `residual_regions` back to board coordinates.
3. **UI/orchestrator**: erasure ROI as camera pixel rectangle, or board XY rectangle converted by Calibration; calls the inspection only after stationary pose acknowledgment.
4. **Camera → UI/Status**: `InspectionResult.to_dict()`, optionally mask/overlay for UI. UI decides whether to re-erase; Camera does not move the robot.

## Actual lab validation still needed

- Confirm the D435 sees the entire drawing without gripper/tool occlusion; otherwise capture multiple registered tiles (not implemented in Basic).
- Keep whiteboard fixed and choose one repeatable inspection pose; verify images overlay accurately, since this implementation **does not perform image registration or hand-eye calibration**.
- Ideally lock RealSense exposure and white balance on the lab computer after warmup. Camera auto-adjustment and specular whiteboard reflection cause false positives; large brightness shifts return `UNCERTAIN`.
- Collect real clean / incomplete / faint-residue photos, tune `DetectionConfig` thresholds and quantify false-clean errors. A weak drawn reference yields `UNCERTAIN` instead of assuming success. A sufficiently large localized residue is marked `RESIDUAL` even if the global residual fraction is small.
- The current residual search is near actual original ink, so heavily displaced wipe smears outside that vicinity are not guaranteed to be found. Add an optional full-ROI stain scan if required after real tests.
- No robot-side or hardware validation has been performed; FR3 safety logic belongs to the controller and lab procedures.
