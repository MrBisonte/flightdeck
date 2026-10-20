"""Helpers for the tests that write a flight log or run demo.sh in a copy of the
repository.

A plain module rather than conftest.py, because pytest advises against
importing a conftest file. pytest puts this directory on sys.path, so a test
imports it by name.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def write_log(path: pathlib.Path, records: list[dict]) -> None:
    """Write records the way the sink does: one JSON object per line, LF endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")


def require_tools() -> None:
    """Skip, with the reason, when demo.sh cannot run on this machine."""
    for tool in ("duckdb", "bash"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} is not on PATH")


def copy_tree(work: pathlib.Path, names: tuple[str, ...]) -> pathlib.Path:
    """Copy the named top level entries of the repository into work."""
    for name in names:
        source, target = ROOT / name, work / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    (work / "warehouse").mkdir()
    return work


def run_demo(work: pathlib.Path, *args: str) -> None:
    """Run demo.sh in work. A failure fails the test with demo.sh's own output."""
    done = subprocess.run(
        ["bash", "./demo.sh", *args],
        cwd=work, capture_output=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    assert done.returncode == 0, done.stdout + done.stderr
