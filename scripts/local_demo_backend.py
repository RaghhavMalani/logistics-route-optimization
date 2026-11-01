"""Dedicated loopback QA launcher; opt out of background throttling before imports."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.portwatch_os.hostperf import opt_out_of_power_throttling

print("Local QA process throttling:", opt_out_of_power_throttling(), flush=True)
sys.argv = ["uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8817", "--workers", "1"]
runpy.run_module("uvicorn", run_name="__main__")
