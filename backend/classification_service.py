"""CareLink adapter around the project's single LR + CNN implementation."""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from sensor_core.classification_service import classify_values as health_values, classify_sensor_payload, combine_cnn_result, model_info
from sensor_core.fall_service import infer_fall_window, fall_model_info

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



def predict_snapshot(heart, temperature, fall, motion_window=None, uptime_ms=None):
    base = classify_sensor_payload({"heart_rate_bpm": heart, "object_temp_c": temperature, "fall_detected": fall})
    if fall is None and base["classification"] != "critical":
        base.update(classification="unavailable", confidence=0.0, source="input_validation")
        base["reasons"] = ["Fall state is unavailable."]
    decision = combine_cnn_result(base, infer_fall_window(motion_window, uptime_ms))
    abnormal = []
    thresholds = model_info()["thresholds"]
    # Explain each available input even if another channel has missing data.
    if heart is not None and 30 <= heart <= 250:
        abnormal += [a for a in attribute_abnormal_params(heart, 36.5, False, thresholds) if a["parameter"] == "heart_rate_bpm"]
    if temperature is not None and 30 <= temperature <= 45:
        abnormal += [a for a in attribute_abnormal_params(75, temperature, False, thresholds) if a["parameter"] == "temperature_c"]
    if fall:
        abnormal.append({"parameter":"fall_detected", "value":True, "severity":"critical", "reason":"Hardware state machine reported a confirmed fall sequence."})
    if decision["cnn_fall"]["suspected_fall"]:
        abnormal.append({"parameter":"cnn_suspected_fall", "value":decision["cnn_fall"]["fall_probability"], "severity":"warning", "reason":"CNN detected a possible fall; check the person."})
    return {**decision, "label": None if decision["classification"] == "unavailable" else decision["classification"],
            "model_version": str(model_info().get("trained_at") or "1.0"), "abnormal_params": abnormal}


def classify_values(heart_rate: float, temperature: float, fall: bool) -> dict[str, Any]:
    health_values(heart_rate, temperature, fall)  # validate explicit /classify requests
    return predict_snapshot(heart_rate, temperature, fall)
