from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any

import joblib
import pandas as pd


MODEL_PATH = (
    Path(__file__).resolve().parent
    / "ml"
    / "artifacts"
    / "health_classifier.joblib"
)
_model_lock = Lock()
_artifact: dict[str, Any] | None = None


def _load_artifact() -> dict[str, Any]:
    global _artifact
    with _model_lock:
        if _artifact is None:
            if not MODEL_PATH.exists():
                raise FileNotFoundError(
                    "Trained model not found. Run: python ml/train_models.py"
                )
            loaded = joblib.load(MODEL_PATH)
            if not isinstance(loaded, dict) or "estimator" not in loaded:
                raise ValueError("The trained-model artifact has an invalid format")
            _artifact = loaded
        return _artifact


def model_info() -> dict[str, Any]:
    artifact = _load_artifact()
    return {
        key: deepcopy(value)
        for key, value in artifact.items()
        if key != "estimator"
    }


def _feature_vector(
    heart_rate: float,
    temperature: float,
    fall: bool,
    thresholds: dict[str, float],
) -> list[float]:
    return [
        float(heart_rate),
        float(temperature),
        float(bool(fall)),
        float(heart_rate < thresholds["heart_rate_normal_min"]),
        float(heart_rate > thresholds["heart_rate_normal_max"]),
        float(temperature > thresholds["temperature_warning_high"]),
    ]


def _actions(level: str) -> dict[str, Any]:
    if level == "critical":
        return {
            "buzzer": True,
            "caregiver_alert": True,
            "lcd_status": "CRITICAL",
            "message": "Check the patient immediately.",
        }
    if level == "warning":
        return {
            "buzzer": True,
            "caregiver_alert": True,
            "lcd_status": "WARNING",
            "message": "Repeat the measurement and monitor the patient.",
        }
    if level == "normal":
        return {
            "buzzer": False,
            "caregiver_alert": False,
            "lcd_status": "NORMAL",
            "message": "Continue routine monitoring.",
        }
    return {
        "buzzer": False,
        "caregiver_alert": False,
        "lcd_status": "WAIT",
        "message": "Waiting for complete valid sensor data.",
    }


def classify_values(
    heart_rate: float,
    temperature: float,
    fall: bool,
) -> dict[str, Any]:
    if not 30 <= heart_rate <= 250:
        raise ValueError("heart_rate must be between 30 and 250 BPM")
    if not 30 <= temperature <= 45:
        raise ValueError("temperature must be between 30 and 45 °C")

    artifact = _load_artifact()
    thresholds = artifact["thresholds"]
    vector = _feature_vector(heart_rate, temperature, fall, thresholds)
    estimator = artifact["estimator"]
    model_input = pd.DataFrame([vector], columns=artifact["feature_names"])
    probabilities_raw = estimator.predict_proba(model_input)[0]
    probabilities = {
        str(label): float(probability)
        for label, probability in zip(estimator.classes_, probabilities_raw)
    }
    model_classification = max(probabilities, key=probabilities.get)
    final_classification = model_classification
    confidence = probabilities[model_classification]
    source = artifact["selected_model"]
    reasons: list[str] = []

    # Deterministic safety overrides remain active if the ML model is uncertain.
    # These are transparent guardrails for the educational prototype.
    if fall:
        final_classification = "critical"
        confidence = 1.0
        source = f"{source}+fall_safety_rule"
        reasons.append("Fall sequence confirmed by the MPU6050 state machine.")
    if (
        heart_rate < thresholds["heart_rate_critical_min"]
        or heart_rate > thresholds["heart_rate_critical_max"]
    ):
        final_classification = "critical"
        confidence = 1.0
        source = f"{source}+heart_rate_safety_rule"
        reasons.append("Heart rate is outside the critical safety range.")
    if (
        temperature < thresholds["temperature_critical_low"]
        or temperature > thresholds["temperature_critical_high"]
    ):
        final_classification = "critical"
        confidence = 1.0
        source = f"{source}+temperature_safety_rule"
        reasons.append("Temperature is outside the critical safety range.")

    if not reasons:
        if final_classification == "warning":
            reasons.append("One measurable vital sign is outside its training range.")
        elif final_classification == "critical":
            reasons.append("Multiple measurable conditions indicate a critical state.")
        else:
            reasons.append("All three measurable conditions are classified as normal.")

    return {
        "classification": final_classification,
        "confidence": round(float(confidence), 6),
        "probabilities": {
            label: round(probabilities.get(label, 0.0), 6)
            for label in artifact["labels"]
        },
        "model_classification": model_classification,
        "source": source,
        "model": artifact["selected_model"],
        "features": {
            "heart_rate_bpm": float(heart_rate),
            "body_temperature_c": float(temperature),
            "fall_detected": bool(fall),
        },
        "reasons": reasons,
        "actions": _actions(final_classification),
    }


def classify_sensor_payload(reading: dict[str, Any]) -> dict[str, Any]:
    fall_value = reading.get("fall_detected", reading.get("alarm", False))
    fall = bool(fall_value) if isinstance(fall_value, (bool, int)) else False
    heart_rate = reading.get("heart_rate_bpm")
    temperature = reading.get("object_temp_c")

    # A confirmed fall is critical regardless of whether the optical sensors
    # have produced valid values. This keeps the response independent of those
    # sensors and of network/model availability.
    if fall:
        return {
            "classification": "critical",
            "confidence": 1.0,
            "probabilities": {"normal": 0.0, "warning": 0.0, "critical": 1.0},
            "model_classification": None,
            "source": "fall_safety_rule",
            "model": model_info()["selected_model"],
            "features": {
                "heart_rate_bpm": None,
                "body_temperature_c": temperature,
                "fall_detected": True,
            },
            "reasons": ["Fall confirmed while one or more vital signs are unavailable."],
            "actions": _actions("critical"),
        }

    missing: list[str] = []
    invalid: list[str] = []
    if not isinstance(heart_rate, (int, float)) or isinstance(heart_rate, bool):
        missing.append("heart_rate_bpm")
    elif not 30 <= float(heart_rate) <= 250:
        invalid.append("heart_rate_bpm")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        missing.append("object_temp_c")
    elif not 30 <= float(temperature) <= 45:
        invalid.append("object_temp_c")

    if missing or invalid:
        reasons = []
        if missing:
            reasons.append(f"Missing data: {', '.join(missing)}.")
        if invalid:
            reasons.append(f"Invalid measurement range: {', '.join(invalid)}.")
        return {
            "classification": "unavailable",
            "confidence": 0.0,
            "probabilities": {"normal": 0.0, "warning": 0.0, "critical": 0.0},
            "model_classification": None,
            "source": "input_validation",
            "model": model_info()["selected_model"],
            "features": {
                "heart_rate_bpm": heart_rate,
                "body_temperature_c": temperature,
                "fall_detected": fall,
            },
            "reasons": reasons,
            "actions": _actions("unavailable"),
        }

    return classify_values(float(heart_rate), float(temperature), fall)


def combine_cnn_result(base: dict[str, Any], cnn: dict[str, Any]) -> dict[str, Any]:
    """CNN suspicion raises warning; it never overwrites a critical decision."""
    result = deepcopy(base)
    result["cnn_fall"] = cnn
    result["base_classification"] = base["classification"]
    result["probabilities_source"] = base["source"]
    result["confidence_kind"] = (
        "rule_indicator" if "safety_rule" in base["source"] else "health_model_probability"
    )
    if cnn["status"] == "ready" and cnn["suspected_fall"]:
        reason = "CNN detected a motion pattern consistent with a possible fall."
        if base["classification"] == "normal":
            result["reasons"] = []
        result["reasons"].append(reason)
        result["source"] += "+sisfall_cnn"
        if base["classification"] != "critical":
            result["classification"] = "warning"
            result["confidence"] = cnn["fall_probability"]
            result["confidence_kind"] = "cnn_fall_score"
            result["actions"] = _actions("warning")
            result["actions"]["message"] = "Possible fall detected. Check the person and confirm their condition."
    return result
