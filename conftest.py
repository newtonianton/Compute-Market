"""Ensure the repo root is on sys.path for bare `pytest` runs."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
