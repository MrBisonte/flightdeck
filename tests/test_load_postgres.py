"""The one branch in the load step that has no database behind it.

The container name and the port are both pinned in `docker-compose.yml`, so a
second checkout cannot start its own PostgreSQL. Its `compose up` fails on the
name. The step used to raise `CalledProcessError` with the compose output
captured and discarded, so an operator saw a traceback and no cause.

These tests pin the two outcomes that replaced it: a healthy container gets
adopted without calling compose, and a compose failure carries its own output
plus a hint that names a command which exists.
"""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def loader():
    """The load step, imported by path because its name starts with a digit."""
    path = ROOT / "pipeline" / "30_load_postgres.py"
    spec = importlib.util.spec_from_file_location("flightdeck_loader", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_run(script, calls):
    """A subprocess.run that answers from `script`, keyed on the command word."""
    def run(cmd, **kwargs):
        calls.append(cmd)
        key = cmd[1]                      # "inspect" or "compose"
        returncode, stdout, stderr = script[key]
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)
    return run


def test_a_healthy_container_is_adopted(loader, monkeypatch):
    calls = []
    monkeypatch.setattr(loader.subprocess, "run",
                        fake_run({"inspect": (0, "healthy\n", "")}, calls))
    loader.start_postgres()
    assert [c[1] for c in calls] == ["inspect"], calls


def test_a_compose_failure_carries_its_own_output(loader, monkeypatch):
    calls = []
    conflict = ('Error response from daemon: Conflict. The container name '
                '"/flightdeck-pg" is already in use')
    monkeypatch.setattr(loader.subprocess, "run", fake_run({
        "inspect": (1, "", "No such object"),
        "compose": (1, "", conflict),
    }, calls))
    with pytest.raises(loader.LoadError) as raised:
        loader.start_postgres()
    message = str(raised.value)
    assert "already in use" in message
    assert "docker rm -f flightdeck-pg" in message


def test_the_container_name_matches_the_compose_file(loader):
    """One name, two files. A rename in either one breaks the adoption."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert f"container_name: {loader.CONTAINER}" in compose
