from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import cv2
import mediapipe as mp
import numpy as np

from .config import Settings


ACTION_LABELS: Dict[str, str] = {
    "blink": "眨眼",
    "mouth_open": "张嘴",
    "shake_head": "左右转头",
    "nod_head": "上下点头",
    "smile": "微笑",
}


def random_actions(
    min_count: int = 1,
    max_count: int = 3,
    weights: Optional[Dict[str, float]] = None,
    reduced_actions: Optional[Iterable[str]] = None,
    reduction_factor: float = 0.5,
) -> List[str]:
    max_count = max(1, min(max_count, len(ACTION_LABELS)))
    min_count = max(1, min(min_count, max_count))
    count = min_count + secrets.randbelow(max_count - min_count + 1)
    available = list(ACTION_LABELS.keys())
    selected: List[str] = []
    reduced_set = set(reduced_actions or [])
    normalized_weights = weights or {}
    factor = min(max(float(reduction_factor), 0.05), 1.0)

    while available and len(selected) < count:
        weighted = []
        total = 0.0
        for action in available:
            weight = max(float(normalized_weights.get(action, 1.0)), 0.05)
            if action in reduced_set:
                weight = max(weight * factor, 0.05)
            weighted.append((action, weight))
            total += weight
        pick = secrets.randbelow(max(1, int(total * 1000))) / 1000.0
        cursor = 0.0
        chosen = weighted[-1][0]
        for action, weight in weighted:
            cursor += weight
            if pick < cursor:
                chosen = action
                break
        selected.append(chosen)
        available.remove(chosen)
    return selected


@dataclass
class FrameMetrics:
    ear: float
    mar: float
    mouth_width_ratio: float
    yaw: float
    pitch: float


def verify_liveness_actions(
    frames_by_action: Dict[str, List[np.ndarray]],
    expected_actions: Iterable[str],
    settings: Settings,
) -> List[dict]:
    results: List[dict] = []
    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as face_mesh:
        for action in expected_actions:
            frames = frames_by_action.get(action, [])
            metrics = [_extract_metrics(frame, face_mesh) for frame in frames]
            metrics = [item for item in metrics if item is not None]
            result = _judge_action(action, metrics, settings)
            result["label"] = ACTION_LABELS[action]
            result["face_frames"] = len(metrics)
            result["total_frames"] = len(frames)
            face_frame_ratio = len(metrics) / max(len(frames), 1)
            if result["passed"] and face_frame_ratio < settings.min_face_frame_ratio:
                result["passed"] = False
                result["detail"] += f"，有效人脸帧占比不足 {face_frame_ratio:.0%}"
            results.append(result)
    return results


def _judge_action(action: str, metrics: List[FrameMetrics], settings: Settings) -> dict:
    if len(metrics) < settings.min_frames_per_action:
        return {
            "action": action,
            "passed": False,
            "score": 0.0,
            "detail": f"有效人脸帧不足：{len(metrics)}/{settings.min_frames_per_action}",
        }

    ears = np.array([m.ear for m in metrics], dtype=np.float32)
    mars = np.array([m.mar for m in metrics], dtype=np.float32)
    smiles = np.array([m.mouth_width_ratio for m in metrics], dtype=np.float32)
    yaws = np.array([m.yaw for m in metrics], dtype=np.float32)
    pitches = np.array([m.pitch for m in metrics], dtype=np.float32)

    if action == "blink":
        return _judge_blink_action(action, ears, settings)

    if action == "mouth_open":
        min_mar = float(np.min(mars))
        max_mar = float(np.max(mars))
        mar_delta = max_mar - min_mar
        passed = (
            max_mar > settings.mouth_mar_threshold
            and mar_delta > settings.mouth_mar_delta_threshold
        )
        return {
            "action": action,
            "passed": passed,
            "score": round(max_mar, 4),
            "detail": f"MAR min={min_mar:.3f}, max={max_mar:.3f}, delta={mar_delta:.3f}",
        }

    if action == "shake_head":
        return _judge_head_axis_action(
            action,
            yaws,
            pitches,
            settings.shake_yaw_range_threshold,
            "yaw",
            "pitch",
            settings,
        )

    if action == "nod_head":
        return _judge_head_axis_action(
            action,
            pitches,
            yaws,
            settings.nod_pitch_range_threshold,
            "pitch",
            "yaw",
            settings,
        )

    if action == "smile":
        # The first frames are the neutral reference.  A smile must widen the
        # mouth after the prompt; a generic max/min swing is too easy to pass
        # by simply moving the face or pursing the lips.
        edge_count = max(1, int(np.ceil(len(smiles) * 0.2)))
        baseline = float(np.median(smiles[:edge_count]))
        peak_index = int(np.argmax(smiles))
        peak = float(smiles[peak_index])
        smile_delta = peak - baseline
        mar_delta = float(np.max(mars) - np.min(mars))
        passed = (
            peak_index >= edge_count
            and smile_delta + 1e-4 >= settings.smile_delta_threshold
        )
        return {
            "action": action,
            "passed": passed,
            "score": round(smile_delta, 4),
            "detail": (
                f"mouth width ratio baseline={baseline:.3f}, peak={peak:.3f}, "
                f"delta={smile_delta:.3f}, peak_frame={peak_index}, "
                f"MAR delta={mar_delta:.3f}"
            ),
        }

    return {"action": action, "passed": False, "score": 0.0, "detail": "未知动作"}


def _judge_head_axis_action(
    action: str,
    primary_values: np.ndarray,
    cross_values: np.ndarray,
    threshold: float,
    primary_name: str,
    cross_name: str,
    settings: Settings,
) -> dict:
    """Require dominant motion on the requested axis, regardless of travel order."""
    # solvePnP can express the same near-front pose on either side of 180
    # degrees.  Treating those raw Euler angles as a linear series turns a
    # small movement such as 179 -> -179 into a fake 358 degree movement.
    primary = _smooth_series(_normalize_head_pose_series(primary_values))
    cross = _smooth_series(_normalize_head_pose_series(cross_values))
    edge_count = max(1, int(np.ceil(len(primary) * 0.2)))
    baseline = float(np.median(np.concatenate([primary[:edge_count], primary[-edge_count:]])))
    primary_min = float(np.min(primary))
    primary_max = float(np.max(primary))
    primary_range = primary_max - primary_min
    cross_range = float(np.max(cross) - np.min(cross))
    lower_excursion = baseline - primary_min
    upper_excursion = primary_max - baseline
    # A nod naturally has a smaller measurable pitch range than a left-right
    # turn on laptop cameras. Accept either travel order (left -> right or
    # right -> left, and likewise for up/down).
    min_side_excursion = 1.5 if action == "nod_head" else 2.0
    side_threshold = max(min_side_excursion, threshold * 0.30)
    # People naturally move a little on the other axis while turning or
    # nodding.  The old 55% ratio rejected normal left/right turns whenever
    # the chin rose or fell slightly.  Keep an absolute tolerance for that
    # natural movement, but require the requested axis to remain dominant so
    # a nod cannot be accepted as a head shake (and vice versa).
    cross_axis_limit = max(
        settings.head_axis_cross_tolerance_degrees,
        primary_range * settings.head_axis_cross_range_ratio,
    )
    cross_axis_ok = cross_range <= cross_axis_limit
    passed = (
        primary_range > threshold
        and max(lower_excursion, upper_excursion) >= side_threshold
        and cross_axis_ok
    )
    return {
        "action": action,
        "passed": bool(passed),
        "score": round(primary_range, 4),
        "detail": (
            f"{primary_name} range={primary_range:.1f} deg, "
            f"{cross_name} range={cross_range:.1f} deg, "
            f"side_excursion={lower_excursion:.1f}/{upper_excursion:.1f} deg, "
            f"axis_isolated={cross_axis_ok}, repeated_motion=allowed, direction_order=any, "
            f"cross_limit={cross_axis_limit:.1f} deg"
        ),
    }


def _normalize_head_pose_series(values: np.ndarray) -> np.ndarray:
    """Return a stable signed head-pose series in the [-90, 90] range.

    OpenCV's Euler decomposition has equivalent representations that differ
    by 180 degrees.  Folding the alternate representation back to the
    front-facing range prevents a wraparound from being treated as motion.
    Isolated landmark/PnP spikes are replaced only when both adjacent frames
    agree, so genuine continuous head movement is preserved.
    """
    raw = np.asarray(values, dtype=np.float32)
    normalized = np.remainder(raw + 180.0, 360.0) - 180.0
    canonical = normalized.copy()
    canonical[canonical > 90.0] = 180.0 - canonical[canonical > 90.0]
    canonical[canonical < -90.0] = -180.0 - canonical[canonical < -90.0]

    if len(canonical) < 3:
        return canonical.astype(np.float32)

    stabilized = canonical.copy()
    max_isolated_jump = 35.0
    for index in range(1, len(canonical) - 1):
        neighbor_center = float((canonical[index - 1] + canonical[index + 1]) / 2.0)
        neighbors_are_stable = abs(float(canonical[index - 1] - canonical[index + 1])) <= max_isolated_jump
        if neighbors_are_stable and abs(float(canonical[index] - neighbor_center)) > max_isolated_jump:
            stabilized[index] = neighbor_center
    return stabilized.astype(np.float32)


def _judge_blink_action(action: str, ears: np.ndarray, settings: Settings) -> dict:
    smoothed = _smooth_series(ears)
    edge_count = max(1, int(np.ceil(len(smoothed) * 0.2)))
    edge_values = np.concatenate([smoothed[:edge_count], smoothed[-edge_count:]])
    baseline = float(np.median(edge_values))
    trough_index = int(np.argmin(smoothed))
    trough = float(smoothed[trough_index])
    drop = baseline - trough
    # Require a clear close-and-reopen cycle.  Small landmark jitter or a
    # capture that ends while the eyes are closing must not count as a blink.
    drop_threshold = max(0.045, baseline * 0.18)
    baseline_threshold = settings.blink_ear_threshold
    relaxed_baseline_threshold = max(0.14, settings.blink_ear_threshold * 0.7)

    before_peak = float(np.max(smoothed[:trough_index])) if trough_index > 0 else 0.0
    after_peak = float(np.max(smoothed[trough_index + 1:])) if trough_index + 1 < len(smoothed) else 0.0
    closed_threshold = baseline - drop_threshold * 0.55
    closed_ratio = float(np.mean(smoothed <= closed_threshold))
    recovery_ok = after_peak >= baseline * 0.82
    baseline_ok = baseline >= baseline_threshold or (
        baseline >= relaxed_baseline_threshold
        and drop >= drop_threshold * 1.3
        and before_peak >= baseline * 0.85
        and recovery_ok
    )
    passed = (
        baseline_ok
        and drop >= drop_threshold
        and before_peak >= baseline * 0.85
        and recovery_ok
        and edge_count <= trough_index < len(smoothed) - edge_count
        and closed_ratio <= 0.55
    )
    return {
        "action": action,
        "passed": bool(passed),
        "score": round(float(max(drop, 0.0)), 4),
        "detail": (
            f"EAR baseline={baseline:.3f}, trough={trough:.3f}, "
            f"drop={drop:.3f}/{drop_threshold:.3f}, "
            f"baseline_min={relaxed_baseline_threshold:.3f}, "
            f"recovery={after_peak:.3f}, closed_ratio={closed_ratio:.0%}"
        ),
    }


def _smooth_series(values: np.ndarray) -> np.ndarray:
    if len(values) < 3:
        return values.astype(np.float32)
    padded = np.pad(values.astype(np.float32), (1, 1), mode="edge")
    kernel = np.array([0.25, 0.5, 0.25], dtype=np.float32)
    return np.convolve(padded, kernel, mode="valid").astype(np.float32)


def _extract_metrics(bgr: np.ndarray, face_mesh) -> Optional[FrameMetrics]:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    result = face_mesh.process(rgb)
    if not result.multi_face_landmarks:
        return None

    h, w = bgr.shape[:2]
    landmarks = result.multi_face_landmarks[0].landmark

    left_ear = _eye_aspect_ratio(landmarks, [33, 160, 158, 133, 153, 144], w, h)
    right_ear = _eye_aspect_ratio(landmarks, [362, 385, 387, 263, 373, 380], w, h)
    ear = (left_ear + right_ear) / 2.0

    mouth_vertical = _distance(landmarks[13], landmarks[14], w, h)
    mouth_horizontal = _distance(landmarks[61], landmarks[291], w, h)
    mar = mouth_vertical / max(mouth_horizontal, 1e-6)

    xs = np.array([pt.x for pt in landmarks], dtype=np.float32)
    face_width = float(np.max(xs) - np.min(xs))
    mouth_width_ratio = float((landmarks[291].x - landmarks[61].x) / max(face_width, 1e-6))

    pitch, yaw = _estimate_head_pose(landmarks, w, h)
    return FrameMetrics(
        ear=float(ear),
        mar=float(mar),
        mouth_width_ratio=mouth_width_ratio,
        yaw=float(yaw),
        pitch=float(pitch),
    )


def _eye_aspect_ratio(landmarks, idx: List[int], width: int, height: int) -> float:
    p1, p2, p3, p4, p5, p6 = [landmarks[i] for i in idx]
    vertical = _distance(p2, p6, width, height) + _distance(p3, p5, width, height)
    horizontal = 2.0 * _distance(p1, p4, width, height)
    return vertical / max(horizontal, 1e-6)


def _distance(a, b, width: int, height: int) -> float:
    ax, ay = a.x * width, a.y * height
    bx, by = b.x * width, b.y * height
    return float(np.hypot(ax - bx, ay - by))


def _estimate_head_pose(landmarks, width: int, height: int) -> Tuple[float, float]:
    image_points = np.array(
        [
            (landmarks[1].x * width, landmarks[1].y * height),
            (landmarks[152].x * width, landmarks[152].y * height),
            (landmarks[33].x * width, landmarks[33].y * height),
            (landmarks[263].x * width, landmarks[263].y * height),
            (landmarks[61].x * width, landmarks[61].y * height),
            (landmarks[291].x * width, landmarks[291].y * height),
        ],
        dtype=np.float64,
    )
    model_points = np.array(
        [
            (0.0, 0.0, 0.0),
            (0.0, -63.6, -12.5),
            (-43.3, 32.7, -26.0),
            (43.3, 32.7, -26.0),
            (-28.9, -28.9, -24.1),
            (28.9, -28.9, -24.1),
        ],
        dtype=np.float64,
    )
    focal_length = float(width)
    camera_matrix = np.array(
        [[focal_length, 0, width / 2], [0, focal_length, height / 2], [0, 0, 1]],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((4, 1), dtype=np.float64)
    ok, rotation_vector, _ = cv2.solvePnP(
        model_points,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return 0.0, 0.0
    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    angles, *_ = cv2.RQDecomp3x3(rotation_matrix)
    pitch = float(angles[0])
    yaw = float(angles[1])
    return pitch, yaw
