"""Static scanners for the example's rule that its code holds no key (no tests of their own).

Over every Python file under scripts/ and tests/:

- no file names the CLI's seed variable, in code, a string or a comment, except tests/conftest.py,
  and there only as the first argument of ``monkeypatch.setenv`` or ``monkeypatch.delenv``;
- no call passes ``env=`` (a child process gets the inherited environment, unchanged);
- nothing changes ``os.environ``: no item set or deleted, no mutating method, no ``putenv`` or
  ``unsetenv``, no exec or spawn call that takes an environment.

Each scanner takes a root directory and returns one line per offence, so a test can drive it over
the repository and over a tree of planted offenders. The variable's name is built here rather than
written out, so this file does not name it.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

SEED_VARIABLE = "_".join(("TYPEDSTANDARDS", "SIGNING", "SEED", "B64"))

#: The one file that may name the variable, relative to the scanned root.
SEED_FIXTURE = "tests/conftest.py"
SEED_SETTERS = frozenset({"setenv", "delenv"})

ENV_CALLS = frozenset(
    {
        "putenv",
        "unsetenv",
        "execve",
        "execle",
        "execlpe",
        "execvpe",
        "spawnve",
        "spawnle",
        "spawnlpe",
        "spawnvpe",
        "posix_spawn",
        "posix_spawnp",
    }
)
ENVIRON_MUTATORS = frozenset({"update", "pop", "popitem", "setdefault", "clear", "__setitem__", "__delitem__"})
SCANNED = ("scripts", "tests")


def python_files(root: Path) -> Iterator[Path]:
    for directory in SCANNED:
        base = root / directory
        if base.is_dir():
            yield from sorted(path for path in base.rglob("*.py") if "__pycache__" not in path.parts)


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _is_environ(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
        isinstance(node, ast.Name) and node.id == "environ"
    )


def _allowed_seed_constants(tree: ast.AST) -> set[int]:
    """The ids of string constants that are the first argument of monkeypatch.setenv/delenv."""
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in SEED_SETTERS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "monkeypatch"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == SEED_VARIABLE
        ):
            allowed.add(id(node.args[0]))
    return allowed


def seed_references(root: Path) -> list[str]:
    """Every line naming the seed variable, outside the fixture's setenv and delenv calls."""
    found: list[str] = []
    for path in python_files(root):
        where = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        allowed = _allowed_seed_constants(tree) if where == SEED_FIXTURE else set()
        allowed_lines: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and SEED_VARIABLE in node.value:
                if id(node) in allowed:
                    allowed_lines.add(node.lineno)
                else:
                    found.append(f"{where}:{node.lineno}: a string holds the seed variable's name")
        for number, line in enumerate(text.splitlines(), 1):
            if SEED_VARIABLE in line and number not in allowed_lines:
                entry = f"{where}:{number}: names the seed variable"
                if not any(f.startswith(f"{where}:{number}:") for f in found):
                    found.append(entry)
    return found


def env_overrides(root: Path) -> list[str]:
    """Every call that passes ``env=``, and every change to the process environment."""
    found: list[str] = []
    for path in python_files(root):
        where = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "env":
                        found.append(f"{where}:{node.lineno}: a call passes env=")
                    elif (
                        keyword.arg is None
                        and isinstance(keyword.value, ast.Dict)
                        and any(isinstance(k, ast.Constant) and k.value == "env" for k in keyword.value.keys)
                    ):
                        found.append(f"{where}:{node.lineno}: a call passes env= through **")
                name = _call_name(node)
                if name in ENV_CALLS:
                    found.append(f"{where}:{node.lineno}: calls {name}")
                if name in ENVIRON_MUTATORS and isinstance(node.func, ast.Attribute) and _is_environ(node.func.value):
                    found.append(f"{where}:{node.lineno}: changes os.environ ({name})")
            targets: list[ast.AST] = []
            if isinstance(node, (ast.Assign, ast.Delete)):
                targets = list(node.targets)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Subscript) and _is_environ(target.value):
                    found.append(f"{where}:{node.lineno}: changes os.environ (item)")
                elif isinstance(target, ast.Attribute) and target.attr == "environ":
                    found.append(f"{where}:{node.lineno}: replaces os.environ")
    return found
