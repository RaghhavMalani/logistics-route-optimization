"""Verify the operating-system singleton across independent Python processes."""
import subprocess
import sys
from pathlib import Path

from scripts.run_backend_host import exclusive_host


def test_only_one_host_can_own_the_durable_state(tmp_path):
    root = Path(__file__).resolve().parents[1]
    child = """
import sys
from pathlib import Path
from scripts.run_backend_host import exclusive_host,AlreadyRunning
try:
    with exclusive_host(Path(sys.argv[1])):
        print('acquired')
except AlreadyRunning:
    raise SystemExit(42)
"""
    def attempt():
        return subprocess.run([sys.executable, "-c", child, str(tmp_path)], cwd=root,
            capture_output=True, text=True, timeout=20)
    with exclusive_host(tmp_path):
        result = attempt()
        assert result.returncode == 42, result.stderr
    # A retained lock file must not prevent recovery after the owner's exit.
    recovered = attempt()
    assert recovered.returncode == 0 and recovered.stdout.strip() == "acquired", recovered.stderr
