"""Export preprocessing for the project's trusted local training checkpoint."""
from pathlib import Path
import hashlib
import json


def export_metadata(directory: Path) -> None:
    import torch
    # This command is for our locally trained checkpoint only, never uploads.
    checkpoint = torch.load(directory / "fall_cnn_checkpoint.pt", map_location="cpu", weights_only=False)
    metadata = {name: checkpoint[name] for name in
                ("threshold", "sample_rate_hz", "window_samples", "channels")}
    metadata["channel_mean"] = checkpoint["channel_mean"].tolist()
    metadata["channel_std"] = checkpoint["channel_std"].tolist()
    metadata["model_sha256"] = hashlib.sha256((directory / "fall_cnn_scripted.pt").read_bytes()).hexdigest()
    (directory / "fall_inference.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    export_metadata(Path(__file__).resolve().parent / "fall_artifacts")
