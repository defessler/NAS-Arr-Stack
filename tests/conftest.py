"""Shared fixtures and helpers for NAS-Arr-Stack tests."""

import importlib.util
import sys
from pathlib import Path

NAS_DIR = Path(__file__).parent.parent / 'nas'


def load_module(name, filename):
    """Import a Python script that has a hyphenated filename."""
    path = NAS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # Prevent the module from polluting sys.modules under its real path
    spec.loader.exec_module(mod)
    return mod
