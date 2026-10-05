"""The example's code holds no key: nothing under scripts/ or tests/ names the seed variable (but
conftest's setenv and delenv calls), passes env= to a child process, or changes os.environ.

Each scanner also runs over a tree of planted offenders, so a guard that can no longer fail fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import ROOT
from guards import SEED_VARIABLE, env_overrides, python_files, seed_references


def test_the_scan_covers_both_scripts_and_the_conftest() -> None:
    scanned = {path.relative_to(ROOT).as_posix() for path in python_files(ROOT)}
    assert {"scripts/sign_records.py", "scripts/verify_bundles.py", "tests/conftest.py"} <= scanned


def test_nothing_names_the_seed_variable() -> None:
    assert seed_references(ROOT) == []


def test_nothing_passes_or_changes_the_environment() -> None:
    assert env_overrides(ROOT) == []


SEED_OFFENDERS = {
    "scripts/reads_seed.py": f"import os\nseed = os.environ.get('{SEED_VARIABLE}')\n",
    "scripts/comment_seed.py": f"# the CLI reads {SEED_VARIABLE}\n",
    "tests/test_prints_seed.py": f"import os\nprint(os.environ['{SEED_VARIABLE}'])\n",
    "tests/test_sets_seed.py": f"def test_x(monkeypatch):\n    monkeypatch.setenv('{SEED_VARIABLE}', 'x')\n",
    # conftest may name it only as setenv/delenv's first argument.
    "tests/conftest.py": f"import os\nSEED = '{SEED_VARIABLE}'\nvalue = os.environ.get(SEED)\n",
}
ENV_OFFENDERS = {
    "scripts/env_kw.py": "import subprocess\nsubprocess.run(['node'], env={'A': 'b'})\n",
    "scripts/env_star.py": "import subprocess\nsubprocess.run(['node'], **{'env': {}})\n",
    "scripts/env_set.py": "import os\nos.environ['X'] = 'y'\n",
    "scripts/env_del.py": "import os\ndel os.environ['X']\n",
    "scripts/env_update.py": "import os\nos.environ.update(X='y')\n",
    "scripts/env_pop.py": "import os\nos.environ.pop('X')\n",
    "scripts/env_putenv.py": "import os\nos.putenv('X', 'y')\n",
    "scripts/env_execve.py": "import os\nos.execve('/bin/true', ['true'], {})\n",
    "tests/test_env.py": "import subprocess\nsubprocess.run(['node'], env={})\n",
}


def plant(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize("relative", sorted(SEED_OFFENDERS))
def test_each_seed_offender_is_flagged(tmp_path: Path, relative: str) -> None:
    plant(tmp_path, {relative: SEED_OFFENDERS[relative]})
    assert [line for line in seed_references(tmp_path) if line.startswith(relative)]


@pytest.mark.parametrize("relative", sorted(ENV_OFFENDERS))
def test_each_environment_offender_is_flagged(tmp_path: Path, relative: str) -> None:
    plant(tmp_path, {relative: ENV_OFFENDERS[relative]})
    assert [line for line in env_overrides(tmp_path) if line.startswith(relative)]


def test_the_fixture_may_set_and_unset_a_throwaway_seed(tmp_path: Path) -> None:
    plant(
        tmp_path,
        {
            "tests/conftest.py": (
                "def use(monkeypatch):\n"
                f"    monkeypatch.setenv('{SEED_VARIABLE}', 'x')\n"
                f"    monkeypatch.delenv('{SEED_VARIABLE}', raising=False)\n"
            )
        },
    )
    assert seed_references(tmp_path) == []
