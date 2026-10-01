#!/usr/bin/env python3
"""Record available site information; allocation and GPU compatibility remain explicit."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess


def probe():
    values = {"python": platform.python_version(), "platform": platform.platform(), "commands": {}}
    for name, command in {
        "partitions": ["sinfo", "-o", "%P %G %m %l"],
        "allocation": ["scontrol", "show", "config"],
        "gpu": ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv"],
    }.items():
        if shutil.which(command[0]) is None:
            values["commands"][name] = {"status": "unavailable"}
            continue
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        values["commands"][name] = {
            "status": "succeeded" if result.returncode == 0 else "failed",
            "stdout": result.stdout, "stderr": result.stderr,
        }
    return values


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(probe(), indent=2) + "\n")
