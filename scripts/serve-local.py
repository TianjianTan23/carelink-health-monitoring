#!/usr/bin/env python3
"""Run the local coursework API over HTTP; no certificates or device keys."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
import uvicorn

load_dotenv(os.environ.get("CARELINK_ENV_FILE", ROOT / ".env"), interpolate=False)

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host=os.environ.get("CARELINK_BIND_HOST", "0.0.0.0"),
                port=int(os.environ.get("CARELINK_PORT", "8000")),
                access_log=False, proxy_headers=False)
