from __future__ import annotations

import argparse
import copy
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


SEED = 42
SAMPLE_RATE_HZ = 200
WINDOW_SECONDS = 2.0
WINDOW_SAMPLES = int(SAMPLE_RATE_HZ * WINDOW_SECONDS)
INFERENCE_STRIDE_SAMPLES = SAMPLE_RATE_HZ  # one prediction per second
PRE_IMPACT_SAMPLES = int(0.75 * SAMPLE_RATE_HZ)
TRAIN_FALL_JITTERS = (-50, 0, 50)
MAX_TRAIN_ADL_WINDOWS_PER_FILE = 4

# SisFall conversion factors from the supplied README.
ADXL345_G_PER_BIT = (2.0 * 16.0) / (2**13)
ITG3200_DPS_PER_BIT = (2.0 * 2000.0) / (2**16)

VALIDATION_SUBJECTS = {
    "SA03",
    "SA09",
    "SA18",
    "SA23",
    "SE02",
    "SE14",
}
TEST_SUBJECTS = {
    "SA05",
    "SA12",
    "SA20",
    "SE04",
    "SE06",
    "SE11",
}


@dataclass(frozen=True)
class WindowInfo:
    subject: str
    recording: str
    start_sample: int
    recording_samples: int
    label: int


class FallCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(6, 32, kernel_size=9, padding=4),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 64, kernel_size=7, padding=3),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(64, 96, kernel_size=5, padding=2),
            nn.BatchNorm1d(96),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(96, 48),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(48, 2),
        )

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        return self.classifier(self.features(values))


def set_reproducible_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def clean_last_column(value: Any) -> float:
    if isinstance(value, bytes):
        value = value.decode("ascii")
    return float(str(value).strip().rstrip(";"))


def load_recording(path: Path) -> tuple[np.ndarray, int]:
    dropped_rows = 0
    try:
        raw = np.loadtxt(
            path,
            delimiter=",",
            dtype=np.float32,
            converters={8: clean_last_column},
        )
    except ValueError:
        # A small number of supplied files contain whitespace-only lines. Keep
        # valid nine-column sensor rows and record every rejected source row.
        with path.open("r", encoding="ascii") as handle:
            lines = handle.readlines()
        valid_lines = [line for line in lines if line.count(",") == 8]
        dropped_rows = len(lines) - len(valid_lines)
        raw = np.loadtxt(
            valid_lines,
            delimiter=",",
            dtype=np.float32,
            converters={8: clean_last_column},
        )
    if raw.ndim != 2 or raw.shape[1] != 9:
        raise ValueError(f"Expected 9 columns in {path}, got {raw.shape}")

    # Match the six MPU6050 channels and discard the second accelerometer.
    values = np.empty((raw.shape[0], 6), dtype=np.float32)
    values[:, :3] = raw[:, :3] * ADXL345_G_PER_BIT
    values[:, 3:] = raw[:, 3:6] * ITG3200_DPS_PER_BIT
    return values, dropped_rows


def fit_window(values: np.ndarray, requested_start: int) -> tuple[np.ndarray, int]:
    if len(values) < WINDOW_SAMPLES:
        missing = WINDOW_SAMPLES - len(values)
        values = np.pad(values, ((0, missing), (0, 0)), mode="edge")
    start = int(np.clip(requested_start, 0, len(values) - WINDOW_SAMPLES))
    window = values[start : start + WINDOW_SAMPLES]
    return np.ascontiguousarray(window.T, dtype=np.float32), start


def impact_peak(values: np.ndarray) -> int:
    acceleration_magnitude = np.linalg.norm(values[:, :3], axis=1)
    smoothing_kernel = np.ones(5, dtype=np.float32) / 5.0
    smoothed = np.convolve(acceleration_magnitude, smoothing_kernel, mode="same")
    return int(np.argmax(smoothed))


def evenly_spaced_starts(length: int, count: int) -> list[int]:
    maximum_start = max(0, length - WINDOW_SAMPLES)
    if count <= 1 or maximum_start == 0:
        return [0]
    return np.linspace(0, maximum_start, num=count, dtype=int).tolist()


def adl_starts(length: int, split: str) -> list[int]:
    if split == "train":
        possible = max(1, ((length - WINDOW_SAMPLES) // INFERENCE_STRIDE_SAMPLES) + 1)
        return evenly_spaced_starts(
            length,
            min(MAX_TRAIN_ADL_WINDOWS_PER_FILE, possible),
        )
    maximum_start = max(0, length - WINDOW_SAMPLES)
    starts = list(range(0, maximum_start + 1, INFERENCE_STRIDE_SAMPLES))
    if starts[-1] != maximum_start:
        starts.append(maximum_start)
    return starts


def subject_split(subject: str) -> str:
    if subject in VALIDATION_SUBJECTS:
        return "validation"
    if subject in TEST_SUBJECTS:
        return "test"
    return "train"


def build_windows(
    dataset_dir: Path,
) -> tuple[
    dict[str, np.ndarray],
    dict[str, np.ndarray],
    dict[str, list[WindowInfo]],
    dict[str, Any],
]:
    windows: dict[str, list[np.ndarray]] = defaultdict(list)
    labels: dict[str, list[int]] = defaultdict(list)
    metadata: dict[str, list[WindowInfo]] = defaultdict(list)
    recording_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"adl": 0, "fall": 0}
    )
    subjects: dict[str, set[str]] = defaultdict(set)
    dropped_source_rows = 0

    paths = sorted(
        path
        for path in dataset_dir.glob("*/*.txt")
        if path.name.startswith(("D", "F"))
    )
    if not paths:
        raise FileNotFoundError(f"No SisFall recordings found under {dataset_dir}")

    for index, path in enumerate(paths, start=1):
        subject = path.parent.name
        split = subject_split(subject)
        is_fall = path.name.startswith("F")
        values, dropped_rows = load_recording(path)
        dropped_source_rows += dropped_rows
        subjects[split].add(subject)
        recording_counts[split]["fall" if is_fall else "adl"] += 1

        if is_fall:
            peak = impact_peak(values)
            jitters = TRAIN_FALL_JITTERS if split == "train" else (0,)
            starts = [peak - PRE_IMPACT_SAMPLES + jitter for jitter in jitters]
        else:
            starts = adl_starts(len(values), split)

        for requested_start in starts:
            window, actual_start = fit_window(values, requested_start)
            windows[split].append(window)
            labels[split].append(int(is_fall))
            metadata[split].append(
                WindowInfo(
                    subject=subject,
                    recording=path.name,
                    start_sample=actual_start,
                    recording_samples=len(values),
                    label=int(is_fall),
                )
            )

        if index % 500 == 0 or index == len(paths):
            print(f"Prepared {index}/{len(paths)} recordings", flush=True)

    arrays = {
        split: np.stack(windows[split]).astype(np.float32, copy=False)
        for split in ("train", "validation", "test")
    }
    label_arrays = {
        split: np.asarray(labels[split], dtype=np.int64)
        for split in ("train", "validation", "test")
    }
    audit = {
        "recording_count": len(paths),
        "dropped_malformed_source_rows": dropped_source_rows,
        "subjects": {
            split: sorted(subjects[split])
            for split in ("train", "validation", "test")
        },
        "recordings": {
            split: recording_counts[split]
            for split in ("train", "validation", "test")
        },
        "windows": {
            split: {
                "total": int(len(label_arrays[split])),
                "adl": int(np.sum(label_arrays[split] == 0)),
                "fall": int(np.sum(label_arrays[split] == 1)),
            }
            for split in ("train", "validation", "test")
        },
    }
    return arrays, label_arrays, metadata, audit


def make_loader(
    values: np.ndarray,
    labels: np.ndarray,
    batch_size: int,
    shuffle: bool,
) -> DataLoader:
    generator = torch.Generator().manual_seed(SEED)
    dataset = TensorDataset(torch.from_numpy(values), torch.from_numpy(labels))
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=0,
        generator=generator,
    )


@torch.no_grad()
def predict_probabilities(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    probabilities: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for batch_values, batch_labels in loader:
        logits = model(batch_values.to(device))
        probabilities.append(torch.softmax(logits, dim=1)[:, 1].cpu().numpy())
        labels.append(batch_labels.numpy())
    return np.concatenate(probabilities), np.concatenate(labels)


def select_threshold(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    rows: list[dict[str, float]] = []
    for threshold in np.linspace(0.05, 0.95, 91):
        predicted = probabilities >= threshold
        rows.append(
            {
                "threshold": float(threshold),
                "precision": float(
                    precision_score(labels, predicted, zero_division=0)
                ),
                "recall": float(recall_score(labels, predicted, zero_division=0)),
                "f1": float(f1_score(labels, predicted, zero_division=0)),
            }
        )
    safety_candidates = [row for row in rows if row["recall"] >= 0.95]
    candidates = safety_candidates or rows
    return max(candidates, key=lambda row: (row["f1"], row["precision"]))


def binary_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    predicted = (probabilities >= threshold).astype(np.int64)
    matrix = confusion_matrix(labels, predicted, labels=[0, 1])
    true_negative, false_positive, false_negative, true_positive = matrix.ravel()
    specificity = true_negative / max(1, true_negative + false_positive)
    result: dict[str, Any] = {
        "threshold": float(threshold),
        "samples": int(len(labels)),
        "accuracy": float(accuracy_score(labels, predicted)),
        "precision": float(precision_score(labels, predicted, zero_division=0)),
        "fall_recall": float(recall_score(labels, predicted, zero_division=0)),
        "specificity": float(specificity),
        "f1": float(f1_score(labels, predicted, zero_division=0)),
        "confusion_matrix": matrix.tolist(),
    }
    if len(np.unique(labels)) == 2:
        result["roc_auc"] = float(roc_auc_score(labels, probabilities))
        result["pr_auc"] = float(average_precision_score(labels, probabilities))
    else:
        result["roc_auc"] = None
        result["pr_auc"] = None
    return result


def false_alarm_summary(
    metadata: list[WindowInfo],
    predictions: np.ndarray,
) -> dict[str, float | int]:
    starts_by_recording: dict[tuple[str, str], list[int]] = defaultdict(list)
    durations: dict[tuple[str, str], int] = {}
    if len(metadata) != len(predictions):
        raise ValueError("Metadata and prediction lengths differ")
    for info, predicted in zip(metadata, predictions):
        if info.label != 0:
            continue
        key = (info.subject, info.recording)
        durations[key] = info.recording_samples
        if predicted:
            starts_by_recording[key].append(info.start_sample)

    episodes = 0
    for starts in starts_by_recording.values():
        previous: int | None = None
        for start in sorted(starts):
            if previous is None or start - previous > WINDOW_SAMPLES:
                episodes += 1
            previous = start

    hours = sum(durations.values()) / SAMPLE_RATE_HZ / 3600.0
    return {
        "adl_hours": float(hours),
        "false_alarm_episodes": int(episodes),
        "false_alarm_episodes_per_hour": float(episodes / max(hours, 1e-9)),
    }


def subject_metrics(
    metadata: list[WindowInfo],
    labels: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    subjects = sorted({info.subject for info in metadata})
    for subject in subjects:
        mask = np.asarray([info.subject == subject for info in metadata])
        result[subject] = binary_metrics(labels[mask], probabilities[mask], threshold)
    return result


def plot_confusion_matrix(matrix: list[list[int]], output_path: Path) -> None:
    values = np.asarray(matrix)
    figure, axis = plt.subplots(figsize=(5.5, 4.5))
    image = axis.imshow(values, cmap="Blues")
    figure.colorbar(image, ax=axis)
    axis.set_xticks([0, 1], labels=["ADL", "Fall"])
    axis.set_yticks([0, 1], labels=["ADL", "Fall"])
    axis.set_xlabel("Predicted")
    axis.set_ylabel("Actual")
    axis.set_title("Subject-independent fall CNN test set")
    for row in range(2):
        for column in range(2):
            axis.text(column, row, str(values[row, column]), ha="center", va="center")
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def plot_training_history(history: list[dict[str, float]], output_path: Path) -> None:
    epochs = [int(row["epoch"]) for row in history]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].plot(epochs, [row["train_loss"] for row in history], label="Training")
    axes[0].plot(epochs, [row["validation_loss"] for row in history], label="Validation")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Loss")
    axes[0].legend()
    axes[1].plot(epochs, [row["validation_pr_auc"] for row in history])
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Validation PR-AUC")
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def train_model(
    model: FallCNN,
    train_loader: DataLoader,
    validation_loader: DataLoader,
    train_labels: np.ndarray,
    device: torch.device,
    epochs: int,
) -> tuple[FallCNN, list[dict[str, float]]]:
    class_counts = np.bincount(train_labels, minlength=2).astype(np.float32)
    class_weights = class_counts.sum() / (2.0 * np.maximum(class_counts, 1.0))
    loss_function = nn.CrossEntropyLoss(
        weight=torch.tensor(class_weights, dtype=torch.float32, device=device)
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)

    best_state = copy.deepcopy(model.state_dict())
    best_pr_auc = -1.0
    epochs_without_improvement = 0
    history: list[dict[str, float]] = []

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        total_items = 0
        for batch_values, batch_labels in train_loader:
            batch_values = batch_values.to(device)
            batch_labels = batch_labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(batch_values)
            loss = loss_function(logits, batch_labels)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(batch_labels)
            total_items += len(batch_labels)

        validation_probabilities, validation_labels = predict_probabilities(
            model, validation_loader, device
        )
        validation_pr_auc = float(
            average_precision_score(validation_labels, validation_probabilities)
        )

        model.eval()
        validation_loss_total = 0.0
        validation_items = 0
        with torch.no_grad():
            for batch_values, batch_labels in validation_loader:
                batch_values = batch_values.to(device)
                batch_labels = batch_labels.to(device)
                loss = loss_function(model(batch_values), batch_labels)
                validation_loss_total += float(loss.item()) * len(batch_labels)
                validation_items += len(batch_labels)

        row = {
            "epoch": float(epoch),
            "train_loss": total_loss / total_items,
            "validation_loss": validation_loss_total / validation_items,
            "validation_pr_auc": validation_pr_auc,
        }
        history.append(row)
        print(
            f"Epoch {epoch:02d}: train_loss={row['train_loss']:.4f} "
            f"validation_loss={row['validation_loss']:.4f} "
            f"validation_pr_auc={validation_pr_auc:.4f}",
            flush=True,
        )

        if validation_pr_auc > best_pr_auc + 1e-4:
            best_pr_auc = validation_pr_auc
            best_state = copy.deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= 4:
                print("Early stopping after four epochs without improvement", flush=True)
                break

    model.load_state_dict(best_state)
    return model, history


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a subject-independent SisFall 1D CNN."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path.home() / "Desktop" / "SisFall_dataset",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "fall_artifacts",
    )
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()

    set_reproducible_seed(SEED)
    torch.set_num_threads(min(8, max(1, torch.get_num_threads())))
    device = torch.device("cpu")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading SisFall from {args.dataset.resolve()}", flush=True)
    arrays, labels, metadata, audit = build_windows(args.dataset.resolve())

    channel_mean = arrays["train"].mean(axis=(0, 2), dtype=np.float64).astype(np.float32)
    channel_std = arrays["train"].std(axis=(0, 2), dtype=np.float64).astype(np.float32)
    channel_std = np.maximum(channel_std, 1e-6)
    for split in ("train", "validation", "test"):
        arrays[split] = (
            (arrays[split] - channel_mean[None, :, None])
            / channel_std[None, :, None]
        ).astype(np.float32, copy=False)

    train_loader = make_loader(
        arrays["train"], labels["train"], args.batch_size, shuffle=True
    )
    validation_loader = make_loader(
        arrays["validation"], labels["validation"], args.batch_size, shuffle=False
    )
    test_loader = make_loader(
        arrays["test"], labels["test"], args.batch_size, shuffle=False
    )

    model = FallCNN().to(device)
    model, history = train_model(
        model,
        train_loader,
        validation_loader,
        labels["train"],
        device,
        args.epochs,
    )

    validation_probabilities, validation_labels = predict_probabilities(
        model, validation_loader, device
    )
    threshold_result = select_threshold(validation_labels, validation_probabilities)
    threshold = threshold_result["threshold"]
    test_probabilities, test_labels = predict_probabilities(model, test_loader, device)
    test_results = binary_metrics(test_labels, test_probabilities, threshold)
    test_predictions = test_probabilities >= threshold
    test_results["false_alarms"] = false_alarm_summary(
        metadata["test"], test_predictions
    )
    test_results["by_subject"] = subject_metrics(
        metadata["test"], test_labels, test_probabilities, threshold
    )

    evaluation = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(args.dataset.resolve()),
        "method": {
            "model": "1D convolutional neural network",
            "channels": ["accel_x_g", "accel_y_g", "accel_z_g", "gyro_x_dps", "gyro_y_dps", "gyro_z_dps"],
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "window_seconds": WINDOW_SECONDS,
            "window_samples": WINDOW_SAMPLES,
            "fall_window": "impact-centred using maximum smoothed acceleration magnitude",
            "split": "subject-independent",
            "seed": SEED,
        },
        "audit": audit,
        "validation_threshold_selection": threshold_result,
        "validation": binary_metrics(
            validation_labels, validation_probabilities, threshold
        ),
        "test": test_results,
        "limitations": [
            "SE06 is the only elderly participant with fall recordings.",
            "The README supplies recording-level labels but no exact fall-event timestamps; impact-centred windows are inferred from acceleration magnitude.",
            "The source sensors differ from the MPU6050, so physical-unit conversion and real-device validation are required.",
        ],
    }

    checkpoint = {
        "state_dict": model.cpu().state_dict(),
        "channel_mean": channel_mean,
        "channel_std": channel_std,
        "threshold": threshold,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "window_samples": WINDOW_SAMPLES,
        "channels": evaluation["method"]["channels"],
        "model_class": "FallCNN",
    }
    torch.save(checkpoint, output_dir / "fall_cnn_checkpoint.pt")
    scripted = torch.jit.trace(model.eval(), torch.zeros(1, 6, WINDOW_SAMPLES))
    scripted.save(str(output_dir / "fall_cnn_scripted.pt"))
    from export_fall_metadata import export_metadata
    export_metadata(output_dir)

    with (output_dir / "fall_evaluation.json").open("w", encoding="utf-8") as handle:
        json.dump(evaluation, handle, indent=2)
    with (output_dir / "fall_training_history.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(history, handle, indent=2)
    plot_confusion_matrix(
        test_results["confusion_matrix"], output_dir / "fall_confusion_matrix.png"
    )
    plot_training_history(history, output_dir / "fall_training_history.png")

    print(json.dumps({"threshold": threshold, "test": test_results}, indent=2))
    print(f"Saved fall model and evaluation to {output_dir}", flush=True)


if __name__ == "__main__":
    main()
