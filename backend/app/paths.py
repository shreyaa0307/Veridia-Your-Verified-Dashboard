"""Portable project path constants anchored to the backend package layout."""

from __future__ import annotations

import os
from pathlib import Path

# backend/app/paths.py -> parents[1] == backend/
BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parent

DATA_DIR = BACKEND_ROOT / "data"
ENV_FILE = BACKEND_ROOT / ".env.local"

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", BACKEND_ROOT / "uploads"))
DASHBOARD_DIR = Path(os.environ.get("DASHBOARD_DIR", BACKEND_ROOT / "generated_dashboards"))
CHROMA_DIR = Path(os.environ.get("CHROMA_DIR", BACKEND_ROOT / "chroma_db"))
R_OUTPUT_DIR = Path(os.environ.get("R_OUTPUT_DIR", BACKEND_ROOT / "generated_visualization"))

TEMPLATES_FILE = SERVICES_DIR / "rag1_example_viz.json"


def load_project_env() -> None:
    """Load environment variables from .env.local and .env files."""
    from dotenv import load_dotenv

    for env_path in (
        ENV_FILE,
        BACKEND_ROOT / ".env",
        REPO_ROOT / ".env.local",
        REPO_ROOT / ".env",
    ):
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)



def ensure_runtime_dirs() -> None:
    """Create upload, dashboard, and vector-store directories if missing."""
    for directory in (UPLOAD_DIR, DASHBOARD_DIR, CHROMA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
