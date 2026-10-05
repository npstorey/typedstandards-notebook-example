"""Fixtures for the example's tests: no network, throwaway seeds, and a copy of the repository.

This is the one file under scripts/ and tests/ allowed to name the CLI's seed variable, and only
as the first argument of ``monkeypatch.setenv`` or ``monkeypatch.delenv`` (tests/guards.py
enforces it). A seed set here is 32 bytes from ``secrets``, generated for one test and discarded
with it; no test reads it back or prints it.
"""

from __future__ import annotations

import base64
import secrets
import shutil
import socket
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: What a copy of the repository leaves out: git's metadata, installed trees and caches.
SKIP = frozenset({".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"})


class NetworkBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs offline: opening a connection or binding a port raises NetworkBlocked.
    Child processes (the CLI, host-core) are outside this guard; neither opens one."""

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise NetworkBlocked("a test opened a network connection or bound a port")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket.socket, "bind", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def use_fresh_seed(monkeypatch: pytest.MonkeyPatch) -> Callable[[], None]:
    """Set a new throwaway seed in the environment the CLI inherits, each time it is called."""

    def use() -> None:
        monkeypatch.setenv("TYPEDSTANDARDS_SIGNING_SEED_B64", base64.b64encode(secrets.token_bytes(32)).decode())

    return use


@pytest.fixture
def no_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make sure the seed's variable is unset."""
    monkeypatch.delenv("TYPEDSTANDARDS_SIGNING_SEED_B64", raising=False)


def copy_tree(source: Path, target: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name in SKIP}

    shutil.copytree(source, target, ignore=ignore, symlinks=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A copy of this repository's working tree, with node_modules linked from the checkout."""
    target = tmp_path / "repo"
    copy_tree(ROOT, target)
    if (ROOT / "node_modules").is_dir():
        (target / "node_modules").symlink_to(ROOT / "node_modules", target_is_directory=True)
    return target
