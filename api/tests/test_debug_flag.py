import os
import subprocess
import sys

ROUTES = "from app.main import app; print('/debug/tables' in app.openapi()['paths'])"


def _debug_mounted(**env):
    # A fresh interpreter, because the flag is read once at import time.
    result = subprocess.run(
        [sys.executable, "-c", ROUTES],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip() == "True"


def test_debug_routes_are_off_by_default():
    assert not _debug_mounted(EG_DEBUG="")


def test_debug_routes_mount_when_enabled():
    assert _debug_mounted(EG_DEBUG="true")
