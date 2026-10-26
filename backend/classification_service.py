from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any, Optional

import joblib
import pandas as pd


MODEL_PATH = Path(__file__).resolve().parent / "ml" / "artifacts" / "health_classifier.joblib"
_model_lock = Lock()
_artifact: Optional[dict[str, Any]] = None


def _load_artifact() -> dict[str, Any]:
    global _artifact
    with _model_lock:
        if _artifact is None:
            loaded = joblib.load(MODEL_PATH)
            if not isinstance(loaded, dict) or "estimator" not in loaded:
                raise ValueError("The trained-model artifact has an invalid format")
            _artifact = loaded
        return _artifact


def model_info() -> dict[str, Any]:
    return {key: deepcopy(value) for key, value in _load_artifact().items() if key != "estimator"}


def _feature_vector(heart_rate: float, temperature: float, fall: bool, thresholds: dict[str, float]) -> list[float]:
    return [
        float(heart_rate),
        float(temperature),
        float(fall),
        float(heart_rate < thresholds["heart_rate_normal_min"]),
        float(heart_rate > thresholds["heart_rate_normal_max"]),
        float(temperature > thresholds["temperature_warning_high"]),
    ]


def _severity(value: float, warning_low: Optional[float], warning_high: Optional[float], critical_low: Optional[float], critical_high: Optional[float]) -> Optional[str]:
    if critical_low is not None and value < critical_low:
        return "critical"
    if critical_high is not None and value > critical_high:
        return "critical"
    if warning_low is not None and value < warning_low:
        return "warning"
    if warning_high is not None and value > warning_high:
        return "warning"
    return None


def attribute_abnormal_params(heart_rate: float, temperature: float, fall: bool, thresholds: dict[str, float]) -> list[dict[str, Any]]:
    """Explain abnormal inputs without replacing the model's overall label."""
    abnormal: list[dict[str, Any]] = []
    if fall:
        abnormal.append({
            "parameter": "fall_detected",
            "value": True,
            "severity": "critical",
            "reason": "The MPU6050 fall state machine reported a confirmed fall sequence.",
        })
    heart_severity = _severity(
        heart_rate,
        thresholds["heart_rate_normal_min"],
        thresholds["heart_rate_normal_max"],
        thresholds["heart_rate_critical_min"],
        thresholds["heart_rate_critical_max"],
    )
    if heart_severity:
        abnormal.append({
            "parameter": "heart_rate_bpm",
            "value": round(heart_rate, 2),
            "severity": heart_severity,
            "reason": "Heart rate is outside the model training normal range.",
        })
    temperature_severity = _severity(
        temperature,
        35.5,
        thresholds["temperature_warning_high"],
        thresholds["temperature_critical_low"],
        thresholds["temperature_critical_high"],
    )
    if temperature_severity:
        abnormal.append({
            "parameter": "temperature_c",
            "value": round(temperature, 2),
            "severity": temperature_severity,
            "reason": "Temperature is outside the configured expected range.",
        })
    return abnormal


def classify_values(heart_rate: float, temperature: float, fall: bool) -> dict[str, Any]:
    if not 30 <= heart_rate <= 250:
        raise ValueError("heart_rate must be between 30 and 250 BPM")
    if not 30 <= temperature <= 45:
        raise ValueError("temperature must be between 30 and 45 °C")

    artifact = _load_artifact()
    thresholds = artifact["thresholds"]
    estimator = artifact["estimator"]
    frame = pd.DataFrame(
        [_feature_vector(heart_rate, temperature, fall, thresholds)],
        columns=artifact["feature_names"],
    )
    raw_probabilities = estimator.predict_proba(frame)[0]
    probabilities = {
        str(label): float(probability)
        for label, probability in zip(estimator.classes_, raw_probabilities)
    }
    label = max(probabilities, key=probabilities.get)
    confidence = probabilities[label]
    abnormal_params = attribute_abnormal_params(heart_rate, temperature, fall, thresholds)
    return {
        "label": label,
        "classification": label,
        "confidence": round(float(confidence), 6),
        "probabilities": {
            name: round(probabilities.get(name, 0.0), 6)
            for name in ("normal", "warning", "critical")
        },
        "abnormal_params": abnormal_params,
        "source": artifact["selected_model"],
        "model": artifact["selected_model"],
        "model_version": str(artifact.get("version") or artifact.get("trained_at") or "1.0"),
        "features": {
            "heart_rate_bpm": heart_rate,
            "temperature_c": temperature,
            "fall_detected": fall,
        },
    }
