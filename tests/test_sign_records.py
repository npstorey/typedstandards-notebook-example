"""scripts/sign_records.py on a synthetic plan, signed with throwaway seeds in a copy of the repository.

The plan's files, names and URLs are synthetic (example.org, example.com). Each seed is set by
conftest's ``use_fresh_seed``, used for one test and discarded.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import sign_records
from conftest import SKIP

import typedstandards

CSV = b"id,value\n1,10\n2,20\n"
NOTEBOOK = {
    "cells": [
        {"cell_type": "markdown", "id": "intro", "metadata": {}, "source": ["# A synthetic notebook\n"]},
        {
            "cell_type": "code",
            "execution_count": None,
            "id": "count",
            "metadata": {},
            "outputs": [],
            "source": ["rows = 2\n"],
        },
    ],
    "metadata": {},
    "nbformat": 4,
    "nbformat_minor": 5,
}
NAMES = ["analysis", "table", "claim-1", "claim-1-restated"]


def write_synthetic_plan(repo: Path) -> dict[str, Any]:
    work = repo / "work"
    work.mkdir()
    (work / "analysis.ipynb").write_text(json.dumps(NOTEBOOK, indent=1) + "\n", encoding="utf-8")
    typedstandards.pin(
        "https://data.example.org/table.csv",
        save=work / "table.csv",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=CSV)),
    )
    (work / "claim-1.md").write_text("# A claim\n\nThe table has three rows.\n", encoding="utf-8")
    (work / "claim-1-restated.md").write_text("# A claim, restated\n\nThe table has two rows.\n", encoding="utf-8")
    plan = {
        "$comment": "A synthetic plan for the tests.",
        "producerProfile": "scripted-recomputation/notebook-example",
        "captureMethod": "script-run",
        "publisher": {"bindingTier": "pseudonymous", "displayName": "Synthetic publisher"},
        "corroborator": {"bindingTier": "pseudonymous", "displayName": "Synthetic corroborator"},
        "records": [
            {
                "name": "analysis",
                "role": "analysis",
                "title": "A synthetic notebook",
                "file": "work/analysis.ipynb",
                "prompt": "Sign the notebook as a file read at the pinned commit.",
                "vcsRef": {
                    "repoUrl": "https://git.example.com/example/analysis",
                    "commitSha": "0123456789abcdef0123456789abcdef01234567",
                    "path": "analysis.ipynb",
                },
            },
            {
                "name": "table",
                "role": "retrieval",
                "title": "A synthetic snapshot",
                "file": "work/table.csv",
                "prompt": "Sign the snapshot pin fetched.",
                "pins": ["work/table.csv.pin.json"],
            },
            {
                "name": "claim-1",
                "role": "claim",
                "title": "A claim",
                "file": "work/claim-1.md",
                "prompt": "Sign the claim.",
                "withdraw": {"reason": "The count was wrong: the table has two rows. Restated as claim-1-restated."},
            },
            {
                "name": "claim-1-restated",
                "role": "claim",
                "title": "A claim, restated",
                "file": "work/claim-1-restated.md",
                "prompt": "Sign the restated claim.",
                "restates": "claim-1",
            },
        ],
        "corroborations": [
            {
                "name": "claim-1-restated-corroboration",
                "target": "claim-1-restated",
                "scope": "the restated row count",
                "reasoning": "Recounted from the snapshot.",
            }
        ],
    }
    (repo / "signing-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP for part in relative.parts) or path.is_dir():
            continue
        digest.update(relative.as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def run(repo: Path, mode: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = sign_records.main([mode, "--repo", str(repo)])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def host(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(repo / "node_modules" / ".bin" / "typedstandards-host"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def read(repo: Path, relative: str) -> Any:
    return json.loads((repo / relative).read_text(encoding="utf-8"))


def test_the_committed_plan_has_nothing_to_sign(repo: Path, no_seed: None, capsys: pytest.CaptureFixture[str]) -> None:
    """A run on the repository as committed signs nothing and writes nothing, with no seed set."""
    before = tree_digest(repo)
    code, out = run(repo, "publisher", capsys)
    assert code == 0, out
    assert tree_digest(repo) == before
    assert "nothing to sign" in out


def test_dry_run_leaves_the_repository_byte_identical(
    repo: Path, use_fresh_seed: Callable[[], None], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_synthetic_plan(repo)
    use_fresh_seed()
    monkeypatch.setenv("DRY_RUN", "1")
    before = tree_digest(repo)
    code, out = run(repo, "publisher", capsys)
    assert code == 0, out
    assert tree_digest(repo) == before
    for name in NAMES:
        assert re.search(rf"^signed {re.escape(name)} ", out, re.M), name
    assert re.search(r"^signer: did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$", out, re.M)
    assert re.search(r"^check: all \d+ served files equal a fresh build$", out, re.M)
    assert re.search(r"^result: all checks passed$", out, re.M)
    assert "would write" in out and "records/claim-1.withdrawal.json" in out
    assert "DRY_RUN=1: nothing written" in out


def test_live_run_signs_rebuilds_and_passes_check_and_verify(
    repo: Path, use_fresh_seed: Callable[[], None], capsys: pytest.CaptureFixture[str]
) -> None:
    write_synthetic_plan(repo)
    use_fresh_seed()
    code, out = run(repo, "publisher", capsys)
    assert code == 0, out
    for name in NAMES:
        assert (repo / "records" / f"{name}.signed.json").is_file(), name

    signed = {name: read(repo, f"records/{name}.signed.json") for name in NAMES}
    assert len({s["package"]["signer"]["identifier"] for s in signed.values()}) == 1
    assert signed["analysis"]["package"]["vcsRef"]["commitSha"] == "0123456789abcdef0123456789abcdef01234567"
    assert signed["table"]["package"]["queries"][0]["arguments"]["url"] == "https://data.example.org/table.csv"
    assert signed["claim-1"]["package"]["extensions"] == {"org.typedstandards.notebook": {"role": "claim"}}
    restated = signed["claim-1-restated"]["package"]
    assert restated["extensions"]["org.typedstandards.notebook"]["restates"] == signed["claim-1"]["envelopeHash"]
    assert signed["claim-1"]["envelopeHash"] in json.dumps(restated["provenance"])

    index = {r["name"]: r for r in read(repo, "docs/records.json")["records"]}
    assert list(index) == NAMES
    assert index["claim-1"]["status"] == "withdrawn"
    assert index["claim-1"]["withdrawn"]["reason"].startswith("The count was wrong")
    assert {index[n]["status"] for n in NAMES if n != "claim-1"} == {"active"}
    assert index["analysis"]["extensions"]["role"] == "analysis"
    assert not (repo / "docs" / "bundles" / "first-note.bundle.json").exists()
    assert read(repo, "host-policy.json")["signer"] == signed["analysis"]["package"]["signer"]["identifier"]

    checked = host(repo, "check")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    verified = host(repo, "verify")
    assert verified.returncode == 0, verified.stdout
    assert verified.stdout == (repo / "verify-output.txt").read_text(encoding="utf-8")
    shown = subprocess.run(["node", "display.mjs"], cwd=repo, capture_output=True, text=True, check=False)
    assert shown.returncode == 0, shown.stdout


def test_second_live_run_writes_nothing(
    repo: Path, use_fresh_seed: Callable[[], None], capsys: pytest.CaptureFixture[str]
) -> None:
    write_synthetic_plan(repo)
    use_fresh_seed()
    assert run(repo, "publisher", capsys)[0] == 0
    before = tree_digest(repo)
    code, out = run(repo, "publisher", capsys)
    assert code == 0, out
    assert tree_digest(repo) == before
    assert "nothing to sign" in out and "nothing written" in out


def test_corroborator_signs_under_a_second_key(
    repo: Path, use_fresh_seed: Callable[[], None], capsys: pytest.CaptureFixture[str]
) -> None:
    write_synthetic_plan(repo)
    use_fresh_seed()
    code, out = run(repo, "publisher", capsys)
    assert code == 0 and (repo / "records" / "claim-1-restated.signed.json").is_file(), out
    use_fresh_seed()
    code, out = run(repo, "corroborator", capsys)
    assert code == 0, out
    assert (repo / "docs" / "attestations" / "claim-1-restated-corroboration.json").is_file()

    target = read(repo, "records/claim-1-restated.signed.json")
    node = read(repo, "docs/attestations/claim-1-restated-corroboration.json")
    assert node["node"]["type"] == "attestation/corroborates/v1"
    assert node["node"]["targetNodeId"] == target["envelopeHash"]
    assert node["node"]["signer"]["identifier"].startswith("did:key:z6Mk")
    assert node["node"]["signer"]["identifier"] != target["package"]["signer"]["identifier"]
    kept = (repo / "docs" / "attestations" / "claim-1-restated-corroboration.attest-stderr.txt").read_text()
    assert "typedstandards attest exited 0" in kept

    entry = next(r for r in read(repo, "host.json")["records"] if r["name"] == "claim-1-restated")
    assert entry["extensions"]["corroborations"][0]["nodeId"] == node["nodeId"]
    served = next(r for r in read(repo, "docs/records.json")["records"] if r["name"] == "claim-1-restated")
    assert served["extensions"]["corroborations"][0]["nodeId"] == node["nodeId"]
    assert host(repo, "check").returncode == 0
    assert host(repo, "verify").stdout == (repo / "verify-output.txt").read_text(encoding="utf-8")

    before = tree_digest(repo)
    code, out = run(repo, "corroborator", capsys)
    assert code == 0 and tree_digest(repo) == before, out


def test_corroborator_refuses_the_publishers_key(
    repo: Path, use_fresh_seed: Callable[[], None], capsys: pytest.CaptureFixture[str]
) -> None:
    write_synthetic_plan(repo)
    use_fresh_seed()
    assert run(repo, "publisher", capsys)[0] == 0
    before = tree_digest(repo)
    code, out = run(repo, "corroborator", capsys)  # the same seed is still set
    assert code != 0
    assert "the publisher's key" in out
    assert tree_digest(repo) == before


def test_unset_seed_exits_through_seed_error(
    repo: Path, no_seed: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_synthetic_plan(repo)
    sentinel = secrets.token_hex(16)
    monkeypatch.setenv("SIGN_RECORDS_TEST_SENTINEL", sentinel)
    before = tree_digest(repo)
    code, out = run(repo, "publisher", capsys)
    assert code == 3
    assert "SeedError" in out
    assert sentinel not in out
    assert tree_digest(repo) == before


def test_a_restatement_before_its_predecessor_is_withdrawn_is_refused(
    repo: Path, use_fresh_seed: Callable[[], None], capsys: pytest.CaptureFixture[str]
) -> None:
    plan = write_synthetic_plan(repo)
    del plan["records"][2]["withdraw"]
    (repo / "signing-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    use_fresh_seed()
    before = tree_digest(repo)
    code, out = run(repo, "publisher", capsys)
    assert code != 0
    assert "claim-1-restated" in out and "before claim-1 is withdrawn" in out
    assert tree_digest(repo) == before


def test_a_plan_with_an_unknown_key_is_refused(repo: Path, no_seed: None, capsys: pytest.CaptureFixture[str]) -> None:
    plan = write_synthetic_plan(repo)
    plan["records"][0]["colour"] = "blue"
    (repo / "signing-plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    code, out = run(repo, "publisher", capsys)
    assert code == 2
    assert "colour" in out
