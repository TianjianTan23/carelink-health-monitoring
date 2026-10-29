from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    ConfusionMatrixDisplay,
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "data" / "synthetic_patient_healthcare.csv"
DEFAULT_OUTPUT = ROOT / "artifacts"
LABELS = ["normal", "warning", "critical"]
RAW_FEATURES = ["heart_rate", "temperature", "fall"]
ENGINEERED_FEATURES = [
    "heart_rate",
    "temperature",
    "fall",
    "heart_rate_low",
    "heart_rate_high",
    "temperature_high",
]
THRESHOLDS = {
    "heart_rate_normal_min": 60.0,
    "heart_rate_normal_max": 100.0,
    "heart_rate_critical_min": 45.0,
    "heart_rate_critical_max": 130.0,
    "temperature_warning_high": 37.5,
    "temperature_critical_low": 34.0,
    "temperature_critical_high": 39.0,
}


def _normalise_text(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def prepare_dataset(dataset_path: Path) -> tuple[pd.DataFrame, pd.Series, dict[str, Any]]:
    frame = pd.read_csv(dataset_path)
    required = {
        "Heart Rate (bpm)",
        "Body Temperature (°C)",
        "Fall Detection",
        "Heart Rate Alert",
        "Temperature Alert",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(missing)}")

    prepared = pd.DataFrame(
        {
            "heart_rate": pd.to_numeric(frame["Heart Rate (bpm)"], errors="coerce"),
            "temperature": pd.to_numeric(
                frame["Body Temperature (°C)"], errors="coerce"
            ),
            "fall": _normalise_text(frame["Fall Detection"]).eq("YES").astype(int),
        }
    )
    heart_abnormal = _normalise_text(frame["Heart Rate Alert"]).eq("ABNORMAL")
    temperature_abnormal = _normalise_text(frame["Temperature Alert"]).eq(
        "ABNORMAL"
    )

    valid = (
        prepared["heart_rate"].between(30, 250)
        & prepared["temperature"].between(30, 45)
        & prepared.notna().all(axis=1)
    )
    prepared = prepared.loc[valid].reset_index(drop=True)
    heart_abnormal = heart_abnormal.loc[valid].reset_index(drop=True)
    temperature_abnormal = temperature_abnormal.loc[valid].reset_index(drop=True)

    # Labels use only conditions observable by the deployed hardware. Using
    # SpO2 or blood-pressure alerts here would make the target impossible to
    # infer from the three available sensors.
    critical = prepared["fall"].eq(1) | (heart_abnormal & temperature_abnormal)
    warning = heart_abnormal | temperature_abnormal
    labels = pd.Series(
        np.select(
            [critical, warning],
            ["critical", "warning"],
            default="normal",
        ),
        name="label",
    )

    audit = {
        "source_rows": int(len(frame)),
        "training_rows": int(len(prepared)),
        "dropped_invalid_rows": int((~valid).sum()),
        "label_distribution": {
            label: int((labels == label).sum()) for label in LABELS
        },
    }
    return prepared, labels, audit


def engineer_features(raw: pd.DataFrame) -> pd.DataFrame:
    result = raw[RAW_FEATURES].copy()
    result["heart_rate_low"] = (
        result["heart_rate"] < THRESHOLDS["heart_rate_normal_min"]
    ).astype(int)
    result["heart_rate_high"] = (
        result["heart_rate"] > THRESHOLDS["heart_rate_normal_max"]
    ).astype(int)
    result["temperature_high"] = (
        result["temperature"] > THRESHOLDS["temperature_warning_high"]
    ).astype(int)
    return result[ENGINEERED_FEATURES]


def evaluate_model(
    name: str,
    estimator: Any,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    output_dir: Path,
) -> dict[str, Any]:
    estimator.fit(x_train, y_train)
    predicted = estimator.predict(x_test)
    matrix = confusion_matrix(y_test, predicted, labels=LABELS)
    critical_recall = recall_score(
        y_test,
        predicted,
        labels=["critical"],
        average="macro",
        zero_division=0,
    )
    normal_mask = y_test.eq("normal").to_numpy()
    false_warning_rate = float(
        np.mean(predicted[normal_mask] != "normal") if normal_mask.any() else 0.0
    )

    display = ConfusionMatrixDisplay(matrix, display_labels=LABELS)
    display.plot(cmap="Blues", values_format="d", colorbar=False)
    plt.title(name.replace("_", " ").title())
    plt.tight_layout()
    plt.savefig(output_dir / f"confusion_matrix_{name}.png", dpi=180)
    plt.close()

    return {
        "accuracy": float(accuracy_score(y_test, predicted)),
        "precision_macro": float(
            precision_score(y_test, predicted, average="macro", zero_division=0)
        ),
        "recall_macro": float(
            recall_score(y_test, predicted, average="macro", zero_division=0)
        ),
        "f1_macro": float(
            f1_score(y_test, predicted, average="macro", zero_division=0)
        ),
        "critical_recall": float(critical_recall),
        "missed_critical_rate": float(1.0 - critical_recall),
        "false_warning_rate": false_warning_rate,
        "confusion_matrix": matrix.tolist(),
        "per_class": classification_report(
            y_test,
            predicted,
            labels=LABELS,
            output_dict=True,
            zero_division=0,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train and compare the IOT308TC three-sensor classifiers."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    raw, labels, audit = prepare_dataset(args.dataset.resolve())
    x_train_raw, x_test_raw, y_train, y_test = train_test_split(
        raw,
        labels,
        test_size=0.2,
        stratify=labels,
        random_state=42,
    )
    x_train_engineered = engineer_features(x_train_raw)
    x_test_engineered = engineer_features(x_test_raw)

    initial_lr = Pipeline(
        [
            ("scale", StandardScaler()),
            ("classifier", LogisticRegression(max_iter=2000, random_state=42)),
        ]
    )
    improved_lr = Pipeline(
        [
            ("scale", StandardScaler()),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    improved_rf = RandomForestClassifier(
        n_estimators=250,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )

    results: dict[str, dict[str, Any]] = {}
    results["initial_logistic_regression"] = evaluate_model(
        "initial_logistic_regression",
        initial_lr,
        x_train_raw,
        x_test_raw,
        y_train,
        y_test,
        output_dir,
    )
    candidates = {
        "logistic_regression": improved_lr,
        "random_forest": improved_rf,
    }
    for name, estimator in candidates.items():
        results[name] = evaluate_model(
            name,
            estimator,
            x_train_engineered,
            x_test_engineered,
            y_train,
            y_test,
            output_dir,
        )

    selected_name = max(
        candidates,
        key=lambda name: (
            results[name]["critical_recall"],
            results[name]["f1_macro"],
            results[name]["accuracy"],
        ),
    )
    deployed = clone(candidates[selected_name])
    full_engineered = engineer_features(raw)
    deployed.fit(full_engineered, labels)

    dataset_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    trained_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "estimator": deployed,
        "selected_model": selected_name,
        "feature_names": ENGINEERED_FEATURES,
        "labels": LABELS,
        "thresholds": THRESHOLDS,
        "trained_at": trained_at,
        "training_rows": audit["training_rows"],
        "dataset_sha256": dataset_hash,
    }
    joblib.dump(artifact, output_dir / "health_classifier.joblib")

    report = {
        "purpose": "Educational prototype; not for diagnosis or clinical decisions.",
        "dataset": {
            "path": str(args.dataset.resolve()),
            "sha256": dataset_hash,
            **audit,
        },
        "label_engineering": {
            "normal": "No heart-rate alert, no temperature alert, and no fall.",
            "warning": "Exactly one measurable vital-sign alert and no fall.",
            "critical": "Fall detected, or both heart rate and temperature are abnormal.",
            "excluded_from_features_and_labels": [
                "SpO2 Level",
                "Blood Pressure",
            ],
        },
        "split": {"test_size": 0.2, "random_state": 42, "stratified": True},
        "models": results,
        "selected_model": selected_name,
        "selection_rule": "Highest critical recall, then macro F1, then accuracy.",
        "feature_names": ENGINEERED_FEATURES,
        "thresholds": THRESHOLDS,
        "trained_at": trained_at,
    }
    (output_dir / "evaluation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "model_metadata.json").write_text(
        json.dumps(
            {key: value for key, value in artifact.items() if key != "estimator"},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    names = ["initial_logistic_regression", "logistic_regression", "random_forest"]
    x = np.arange(len(names))
    width = 0.22
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for offset, metric in enumerate(["accuracy", "f1_macro", "critical_recall"]):
        ax.bar(
            x + (offset - 1) * width,
            [results[name][metric] for name in names],
            width,
            label=metric.replace("_", " ").title(),
        )
    ax.set_xticks(x, [name.replace("_", "\n") for name in names])
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score")
    ax.set_title("Classifier Comparison")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "model_comparison.png", dpi=180)
    plt.close(fig)

    print(json.dumps({"selected_model": selected_name, "models": results}, indent=2))


if __name__ == "__main__":
    main()
