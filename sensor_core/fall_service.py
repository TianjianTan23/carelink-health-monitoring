"""Inference for the saved SisFall CNN. Inputs are physical units, not ADC bits."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np

ARTIFACT_DIR = Path(__file__).resolve().parent / "ml" / "fall_artifacts"
CHANNELS = ["accel_x_g", "accel_y_g", "accel_z_g",
            "gyro_x_dps", "gyro_y_dps", "gyro_z_dps"]
_lock = Lock()
_loaded = None
logger = logging.getLogger(__name__)


def _load_model():
    global _loaded
    if _loaded is None:
        import torch
        metadata = json.loads((ARTIFACT_DIR / "fall_inference.json").read_text())
        model_path = ARTIFACT_DIR / "fall_cnn_scripted.pt"
        if hashlib.sha256(model_path.read_bytes()).hexdigest() != metadata["model_sha256"]:
            raise ValueError("CNN model and preprocessing metadata do not match")
        mean = np.asarray(metadata["channel_mean"], dtype=np.float32)
        std = np.asarray(metadata["channel_std"], dtype=np.float32)
        if (metadata["channels"] != CHANNELS or metadata["sample_rate_hz"] != 200
                or metadata["window_samples"] != 400 or mean.shape != (6,)
                or std.shape != (6,) or not np.isfinite(mean).all()
                or not np.isfinite(std).all() or np.any(std <= 0)
                or not 0 < metadata["threshold"] < 1):
            raise ValueError("Invalid CNN preprocessing metadata")
        torch.set_num_threads(min(4, torch.get_num_threads()))
        model = torch.jit.load(str(model_path), map_location="cpu").eval()
        _loaded = (torch, model, metadata, mean, std)
    return _loaded


def _numeric_array(value: Any, name: str) -> np.ndarray:
    # Reject JSON strings and booleans instead of coercing them to measurements.
    array = np.asarray(value)
    if array.dtype.kind not in "iuf" or not np.isfinite(array).all():
        raise ValueError(f"{name} must contain finite numbers")
    def contains_bool(item):
        return isinstance(item, bool) or (isinstance(item, list) and any(contains_bool(x) for x in item))
    if contains_bool(value):
        raise ValueError(f"{name} cannot contain booleans")
    return array.astype(np.float64)


def fall_model_info() -> dict[str, Any]:
    try:
        with _lock:
            _, _, metadata, _, _ = _load_model()
        return {"status": "ready", "model": "sisfall_1d_cnn", "warning_threshold": metadata["threshold"],
                "channels": CHANNELS, "sample_rate_hz": 200, "window_samples": 400}
    except Exception:
        logger.exception("Fall CNN could not be loaded")
        return {"status": "unavailable", "model": "sisfall_1d_cnn",
                "reason": "Check PyTorch and local model artifacts."}


def prepare_motion_window(window: Any, uptime_ms: Any = None) -> np.ndarray:
    if not isinstance(window, dict):
        raise ValueError("motion_window must be an object")
    if window.get("sample_rate_hz") != 200 or window.get("channels") != CHANNELS:
        raise ValueError("Expected 200 Hz and the documented six-channel order")
    if window.get("units") != {"acceleration": "g", "angular_velocity": "deg/s"}:
        raise ValueError("Expected acceleration in g and angular velocity in deg/s")
    rows = window.get("samples")
    if not isinstance(rows, list) or not 400 <= len(rows) <= 480:
        raise ValueError("Expected 400 to 480 time-ordered six-axis samples")
    values = _numeric_array(rows, "samples")
    times = _numeric_array(window.get("timestamps_ms"), "timestamps_ms")
    if values.shape != (len(rows), 6) or times.shape != (len(rows),):
        raise ValueError("Sample or timestamp dimensions are invalid")
    intervals = np.diff(times)
    if np.any(times < 0) or np.any(intervals <= 0) or np.any(intervals > 15):
        raise ValueError("Timestamps must increase with no gap above 15 ms")
    rate = 1000 * (len(times) - 1) / (times[-1] - times[0])
    if not 180 <= rate <= 220 or times[-1] - times[0] < 1995:
        raise ValueError("Window must cover 1,995 ms at approximately 200 Hz")
    if uptime_ms is not None:
        age = _numeric_array(uptime_ms, "uptime_ms")
        if age.ndim != 0 or not 0 <= float(age) - times[-1] <= 250:
            raise ValueError("Motion window is stale relative to device uptime")
    if np.any(np.abs(values[:, :3]) > 16.1) or np.any(np.abs(values[:, 3:]) > 2001):
        raise ValueError("Motion measurements exceed the configured sensor ranges")
    # Align real timestamps to a 5 ms grid; never invent missing long segments.
    grid = times[-1] - np.arange(399, -1, -1) * 5.0
    return np.stack([np.interp(grid, times, values[:, i]) for i in range(6)]).astype(np.float32)


def infer_fall_window(window: Any, uptime_ms: Any = None) -> dict[str, Any]:
    result = {"model": "sisfall_1d_cnn", "status": "waiting_for_window",
              "fall_probability": None, "suspected_fall": False, "threshold": None}
    if window is None:
        result["reason"] = "Waiting for a complete two-second motion window."
        return result
    try:
        values = prepare_motion_window(window, uptime_ms)
    except (ValueError, TypeError, OverflowError) as error:
        return {**result, "status": "invalid_window", "reason": str(error)}
    try:
        with _lock:
            torch, model, metadata, mean, std = _load_model()
            normalized = (values - mean[:, None]) / std[:, None]
            with torch.inference_mode():
                logits = model(torch.from_numpy(normalized[None, :, :]))
                score = float(torch.softmax(logits, dim=1)[0, 1].item())
            if not np.isfinite(score):
                raise ValueError("Non-finite CNN output")
            threshold = float(metadata["threshold"])
        return {**result, "status": "ready", "fall_probability": score,
                "threshold": threshold, "suspected_fall": score >= threshold,
                "window_samples": 400, "sample_rate_hz": 200}
    except Exception:
        logger.exception("Fall CNN inference unavailable")
        return {**result, "status": "unavailable",
                "reason": "CNN unavailable; check PyTorch and local model artifacts."}
