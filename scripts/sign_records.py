"""Sign the example's records from signing-plan.json: the owner's signing script.

    DRY_RUN=1 op run --env-file=<env file> -- uv run scripts/sign_records.py publisher
              op run --env-file=<env file> -- uv run scripts/sign_records.py publisher
    DRY_RUN=1 op run --env-file=<env file> -- uv run scripts/sign_records.py corroborator
              op run --env-file=<env file> -- uv run scripts/sign_records.py corroborator

Modes:

- ``publisher`` signs every plan record that has no signed file yet, withdraws every record the
  plan withdraws that has no withdrawal yet, then signs the restatements; then it writes
  host.json's records from the plan, removes served bundles the plan no longer lists, rebuilds
  docs/, sets host-policy.json's signer to the records' one signer, runs ``typedstandards-host
  check`` and ``verify`` (whose output becomes verify-output.txt) and ``node display.mjs``.
- ``corroborator`` signs every plan corroboration that is not served yet, under a second key,
  serves each at docs/attestations/<name>.json with the CLI's stderr kept beside it, writes its
  nodeId into the target's host.json extensions, and rebuilds and checks as above.

Every run works in a temporary copy of the repository. Only when every check passes, and DRY_RUN
is unset (or 0), does it copy the files that differ back into the repository; a run that changes
nothing writes nothing. With DRY_RUN=1 it prints what it would write, the signer's did:key and
the copy's build, check, verify and display results, and leaves the repository byte-identical.

Signing goes through the typedstandards package (sign, withdraw, attest), which runs the CLI with
the environment this process inherited: the CLI reads the seed from it. This script never names,
reads, prints or passes the seed. Exit codes: 0 ok; 1 a refusal, a failed check or a CLI error;
2 a malformed plan or a missing tool; 3 the CLI found no usable seed (typedstandards.SeedError).
"""

from __future__ import annotations

import argparse
import filecmp
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import typedstandards

ROOT = Path(__file__).resolve().parent.parent
PLAN = "signing-plan.json"

#: The reverse-DNS extensions key under which each package signs its role (this host's domain,
#: notebook.typedstandards.org, reversed).
EXTENSION_KEY = "org.typedstandards.notebook"
ROLES = ("analysis", "dashboard-source", "graph-file", "retrieval", "claim", "note")
#: G0 D8: a file of 10 MiB or less is signed inline; a larger one is signed as a manifest.
MAX_INLINE_BYTES = 10 * 1024 * 1024
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PROV = "http://www.w3.org/ns/prov#"

#: What the working copy leaves out, and what a comparison of the two trees ignores.
SKIP = frozenset({".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"})

TOP_KEYS = (
    {"producerProfile", "captureMethod", "publisher", "corroborator", "records", "corroborations"},
    {"$comment"},
)
SIGNER_KEYS = ({"bindingTier", "displayName"}, {"identifier"})
RECORD_KEYS = (
    {"name", "role", "title", "file", "prompt"},
    {"$comment", "summary", "vcsRef", "pins", "dataSources", "restates", "withdraw"},
)
WITHDRAW_KEYS = ({"reason"}, set())
CORROBORATION_KEYS = ({"name", "target", "scope"}, {"$comment", "reasoning"})


class PlanError(Exception):
    """The plan is malformed (exit 2)."""


class Refusal(Exception):
    """The run refuses to go on (exit 1)."""


# --- paths --------------------------------------------------------------------------------------


def signed_path(name: str) -> str:
    return f"records/{name}.signed.json"


def input_path(name: str) -> str:
    return f"records/{name}.input.json"


def withdraw_input_path(name: str) -> str:
    return f"records/{name}.withdraw-input.json"


def withdrawal_path(name: str) -> str:
    return f"records/{name}.withdrawal.json"


def attest_input_path(name: str) -> str:
    return f"records/{name}.attest-input.json"


def corroboration_path(name: str) -> str:
    return f"docs/attestations/{name}.json"


def attest_stderr_path(name: str) -> str:
    return f"docs/attestations/{name}.attest-stderr.txt"


# --- the plan -----------------------------------------------------------------------------------


def _keys(value: Any, keys: tuple[set[str], set[str]], where: str) -> dict[str, Any]:
    required, optional = keys
    if not isinstance(value, dict):
        raise PlanError(f"{where} must be an object")
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required - optional)
    if missing:
        raise PlanError(f"{where} lacks {', '.join(missing)}")
    if unknown:
        raise PlanError(f"{where} has unknown key(s) {', '.join(unknown)}")
    return value


def _string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise PlanError(f"{where} must be a non-empty string")
    return value


def load_plan(root: Path) -> dict[str, Any]:
    try:
        plan = json.loads((root / PLAN).read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise PlanError(f"cannot read {PLAN}: {err}") from err
    _keys(plan, TOP_KEYS, PLAN)
    _string(plan["producerProfile"], f"{PLAN}: producerProfile")
    _string(plan["captureMethod"], f"{PLAN}: captureMethod")
    for who in ("publisher", "corroborator"):
        _keys(plan[who], SIGNER_KEYS, f"{PLAN}: {who}")
    if not isinstance(plan["records"], list) or not plan["records"]:
        raise PlanError(f"{PLAN}: records must be a non-empty list (host-core serves no empty host)")
    if not isinstance(plan["corroborations"], list):
        raise PlanError(f"{PLAN}: corroborations must be a list")

    names: set[str] = set()
    for i, record in enumerate(plan["records"]):
        where = f"{PLAN}: records[{i}]"
        _keys(record, RECORD_KEYS, where)
        name = _string(record["name"], f"{where}.name")
        if not NAME.match(name) or name in names:
            raise PlanError(f"{where}.name {name!r} must be unique, lowercase letters, digits and '-'")
        names.add(name)
        where = f"{PLAN}: record {name}"
        if record["role"] not in ROLES:
            raise PlanError(f"{where}: role must be one of {', '.join(ROLES)}")
        for key in ("title", "file", "prompt"):
            _string(record[key], f"{where}.{key}")
        if "summary" in record:
            _string(record["summary"], f"{where}.summary")
        if "vcsRef" in record and not isinstance(record["vcsRef"], dict):
            raise PlanError(f"{where}.vcsRef must be an object")
        for key in ("pins", "dataSources"):
            if key in record and not isinstance(record[key], list):
                raise PlanError(f"{where}.{key} must be a list")
        if "withdraw" in record:
            _string(_keys(record["withdraw"], WITHDRAW_KEYS, f"{where}.withdraw")["reason"], f"{where}.withdraw.reason")
    for record in plan["records"]:
        if "restates" in record:
            if record["restates"] not in names or record["restates"] == record["name"]:
                raise PlanError(f"{PLAN}: record {record['name']} restates {record['restates']!r}, not another record")
    seen: set[str] = set()
    for i, corroboration in enumerate(plan["corroborations"]):
        where = f"{PLAN}: corroborations[{i}]"
        _keys(corroboration, CORROBORATION_KEYS, where)
        name = _string(corroboration["name"], f"{where}.name")
        if not NAME.match(name) or name in seen or name in names:
            raise PlanError(f"{where}.name {name!r} must be unique among records and corroborations")
        seen.add(name)
        if corroboration["target"] not in names:
            raise PlanError(f"{where}.target {corroboration['target']!r} is not a record in the plan")
        _string(corroboration["scope"], f"{where}.scope")
    return plan


# --- files --------------------------------------------------------------------------------------


def serialize(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize(value), encoding="utf-8")


def files_of(root: Path) -> Iterator[str]:
    for directory, subdirectories, names in os.walk(root):
        subdirectories[:] = sorted(d for d in subdirectories if d not in SKIP)
        for name in sorted(names):
            if name not in SKIP:
                yield (Path(directory) / name).relative_to(root).as_posix()


def differences(repo: Path, work: Path) -> list[tuple[str, str]]:
    """What the run changed: ("A"|"M"|"D", path) for each file added, modified or deleted."""
    before, after = set(files_of(repo)), set(files_of(work))
    found = [("A", path) for path in after - before]
    found += [("D", path) for path in before - after]
    found += [("M", path) for path in before & after if not filecmp.cmp(repo / path, work / path, shallow=False)]
    return sorted(found, key=lambda item: item[1])


def apply(repo: Path, work: Path, changes: list[tuple[str, str]]) -> None:
    for kind, path in changes:
        target = repo / path
        if kind == "D":
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work / path, target)


# --- signing ------------------------------------------------------------------------------------


def check_state(work: Path, plan: dict[str, Any], mode: str) -> None:
    """Refuse before anything is signed: a signed file that changed, a dropped withdrawal, a
    restatement whose predecessor is not withdrawn, a file too large to sign inline, and, for the
    corroborator, a record or withdrawal the publisher has not signed."""
    records = {r["name"]: r for r in plan["records"]}
    for name, record in records.items():
        file = work / record["file"]
        if not file.is_file():
            raise Refusal(f"record {name}: {record['file']} does not exist")
        if file.stat().st_size > MAX_INLINE_BYTES:
            raise Refusal(f"record {name}: {record['file']} is over 10 MiB; sign a retrieval manifest instead (G0 D8)")
        signed = work / signed_path(name)
        if signed.is_file():
            output = read_json(signed)["package"].get("output")
            try:
                current = file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                current = None
            if output != current:
                raise Refusal(
                    f"record {name}: {record['file']} is not the file {signed_path(name)} signed; a signed record "
                    "cannot change: withdraw it and sign a restatement"
                )
        if (work / withdrawal_path(name)).is_file() and "withdraw" not in record:
            raise Refusal(f"record {name} is withdrawn ({withdrawal_path(name)}), and the plan no longer withdraws it")
        predecessor = record.get("restates")
        if predecessor and not signed.is_file() and "withdraw" not in records[predecessor]:
            raise Refusal(
                f"record {name}: will not sign a restatement before {predecessor} is withdrawn; add a withdraw "
                f"to {predecessor} in the plan"
            )
        if predecessor and not signed.is_file() and "withdraw" in record:
            raise Refusal(f"record {name}: sign a restatement in one run and withdraw it in a later one")
    if mode == "corroborator":
        waiting = [n for n in records if not (work / signed_path(n)).is_file()]
        waiting += [
            f"{n}'s withdrawal"
            for n, r in records.items()
            if "withdraw" in r and not (work / withdrawal_path(n)).is_file()
        ]
        if waiting:
            raise Refusal(f"run the publisher mode first; not signed yet: {', '.join(waiting)}")


def envelope_input(plan: dict[str, Any], record: dict[str, Any], work: Path) -> dict[str, Any]:
    queries = [read_json(work / pin) for pin in record.get("pins", [])]
    extension: dict[str, Any] = {"role": record["role"]}
    value: dict[str, Any] = {
        "type": "content/analysis/v1",
        "producerProfile": plan["producerProfile"],
        "captureMethod": plan["captureMethod"],
        "prompt": record["prompt"],
        "promptVisibility": "full_text",
        "queries": queries,
        "dataSources": record.get("dataSources", []),
        "cost": {"model": "none"},
        "skillMetadata": {},
        "trace": {},
        "signer": dict(plan["publisher"]),
    }
    if "summary" in record:
        value["summary"] = record["summary"]
    if "vcsRef" in record:
        value["vcsRef"] = record["vcsRef"]
    predecessor = record.get("restates")
    if predecessor:
        old = read_json(work / signed_path(predecessor))["envelopeHash"]
        extension["restates"] = old
        old_id = f"urn:{EXTENSION_KEY}:envelope:{old}"
        value["provenance"] = {
            "@context": {"prov": PROV},
            "@graph": [
                {"@id": old_id, "@type": "prov:Entity"},
                {
                    "@id": f"urn:{EXTENSION_KEY}:record:{record['name']}",
                    "@type": "prov:Entity",
                    "prov:wasRevisionOf": {"@id": old_id},
                },
            ],
        }
    value["extensions"] = {EXTENSION_KEY: extension}
    return value


def sign_record(work: Path, plan: dict[str, Any], record: dict[str, Any]) -> str:
    name = record["name"]
    write_json(work / input_path(name), envelope_input(plan, record, work))
    signed = typedstandards.sign(work / input_path(name), output_file=work / record["file"])
    write_json(work / signed_path(name), signed)
    restates = f", restating {record['restates']}" if "restates" in record else ""
    print(f"signed {name} ({record['role']}) from {record['file']}{restates}: envelope hash {signed['envelopeHash']}")
    return signed["package"]["signer"]["identifier"]


def withdraw_record(work: Path, record: dict[str, Any]) -> str:
    name = record["name"]
    target = read_json(work / signed_path(name))
    signer = target["package"]["signer"]
    value = {
        "targetNodeId": target["envelopeHash"],
        "reason": record["withdraw"]["reason"],
        # The record's own identifier: the CLI refuses a seed that is not the record's key.
        "signer": {key: signer[key] for key in ("bindingTier", "displayName", "identifier")},
    }
    write_json(work / withdraw_input_path(name), value)
    node = typedstandards.withdraw(work / withdraw_input_path(name))
    write_json(work / withdrawal_path(name), node)
    print(f"withdrew {name}: nodeId {node['nodeId']}; reason: {record['withdraw']['reason']}")
    return node["node"]["signer"]["identifier"]


class _Kept(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def corroborate(work: Path, plan: dict[str, Any], corroboration: dict[str, Any]) -> str:
    name, target_name = corroboration["name"], corroboration["target"]
    target = read_json(work / signed_path(target_name))
    value: dict[str, Any] = {
        "type": "attestation/corroborates/v1",
        "targetNodeId": target["envelopeHash"],
        "scope": corroboration["scope"],
        "signer": dict(plan["corroborator"]),
    }
    if "reasoning" in corroboration:
        value["reasoning"] = corroboration["reasoning"]
    write_json(work / attest_input_path(name), value)

    # The wrapper logs what the CLI printed on stderr at INFO on the typedstandards logger.
    logger, kept = logging.getLogger("typedstandards"), _Kept()
    level = logger.level
    logger.addHandler(kept)
    logger.setLevel(logging.INFO)
    try:
        node = typedstandards.attest(work / attest_input_path(name))
    finally:
        logger.removeHandler(kept)
        logger.setLevel(level)

    signer = node["node"]["signer"]["identifier"]
    if signer == target["package"]["signer"]["identifier"]:
        raise Refusal(
            f"corroboration {name} was signed under the publisher's key ({signer}); run the corroborator mode "
            "with the corroborator's seed"
        )
    write_json(work / corroboration_path(name), node)
    stderr = [
        "typedstandards attest exited 0: the CLI checked the node offline (verify-core's checkAttestationNode) "
        "before printing it.",
        f"command: typedstandards attest --input {attest_input_path(name)} "
        f"(typedstandards {typedstandards.__version__}, CLI {typedstandards.CLI_VERSION})",
        f"nodeId: {node['nodeId']}",
        f"signer: {signer}",
        f"target: {target_name}, envelope hash {target['envelopeHash']}",
        f"the CLI's stderr, verbatim ({len(kept.lines)} line(s)):",
        *kept.lines,
    ]
    (work / attest_stderr_path(name)).write_text("\n".join(stderr) + "\n", encoding="utf-8")
    print(f"corroborated {target_name} as {name}: nodeId {node['nodeId']}")
    return signer


# --- assembling and checking -------------------------------------------------------------------


def assemble_host(work: Path, plan: dict[str, Any]) -> None:
    """host.json's records, in plan order, from the plan and what has been signed."""
    host = read_json(work / "host.json")
    entries = []
    for record in plan["records"]:
        name = record["name"]
        extensions: dict[str, Any] = {"role": record["role"]}
        if "restates" in record:
            extensions["restates"] = record["restates"]
        corroborations = []
        for corroboration in plan["corroborations"]:
            served = work / corroboration_path(corroboration["name"])
            if corroboration["target"] == name and served.is_file():
                node = read_json(served)
                corroborations.append(
                    {
                        "nodeId": node["nodeId"],
                        "signer": node["node"]["signer"]["identifier"],
                        "attestation": f"attestations/{corroboration['name']}.json",
                    }
                )
        if corroborations:
            extensions["corroborations"] = corroborations
        entries.append(
            {
                "name": name,
                "signed": signed_path(name),
                "attestations": [withdrawal_path(name)] if (work / withdrawal_path(name)).is_file() else [],
                "title": record["title"],
                "extensions": extensions,
            }
        )
    host["records"] = entries
    write_json(work / "host.json", host)
    listed = {record["name"] for record in plan["records"]}
    for bundle in sorted((work / "docs" / "bundles").glob("*.bundle.json")):
        if bundle.name.removesuffix(".bundle.json") not in listed:
            bundle.unlink()
            print(f"removed docs/bundles/{bundle.name}: the plan no longer lists it")


def host_core(work: Path, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(work / "node_modules" / ".bin" / "typedstandards-host"), command],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
    )


def show(result: subprocess.CompletedProcess[str]) -> None:
    for line in (result.stdout + result.stderr).splitlines():
        print(line)


def build_and_check(work: Path) -> bool:
    built = host_core(work, "build")
    show(built)
    if built.returncode != 0:
        print(f"build: exit {built.returncode}")
        return False
    signers = {record["signer"] for record in read_json(work / "docs" / "records.json")["records"]}
    if len(signers) != 1:
        raise Refusal(f"the records are signed by more than one key ({', '.join(sorted(signers))})")
    policy = read_json(work / "host-policy.json")
    policy["signer"] = signers.pop()
    write_json(work / "host-policy.json", policy)

    checked = host_core(work, "check")
    show(checked)
    verified = host_core(work, "verify")
    show(verified)
    if verified.returncode == 0:
        (work / "verify-output.txt").write_text(verified.stdout, encoding="utf-8")
    shown = subprocess.run(["node", "display.mjs"], cwd=work, capture_output=True, text=True, check=False)
    show(shown)
    return checked.returncode == 0 and verified.returncode == 0 and shown.returncode == 0


# --- the run ------------------------------------------------------------------------------------


def run(repo: Path, mode: str, dry_run: bool) -> int:
    plan = load_plan(repo)
    if not (repo / "node_modules" / ".bin" / "typedstandards-host").exists():
        raise PlanError("node_modules/.bin/typedstandards-host is missing; run npm ci first")
    print(
        f"sign_records {mode}: {'DRY_RUN=1, ' if dry_run else ''}working in a temporary copy of the repository; "
        f"typedstandards {typedstandards.__version__}, CLI {typedstandards.CLI_VERSION}"
    )
    with tempfile.TemporaryDirectory(prefix="sign-records-") as temporary:
        work = Path(temporary) / "repo"
        shutil.copytree(repo, work, ignore=lambda _, names: {n for n in names if n in SKIP}, symlinks=True)
        (work / "node_modules").symlink_to((repo / "node_modules").resolve(), target_is_directory=True)
        check_state(work, plan, mode)

        signers: set[str] = set()
        records = plan["records"]
        if mode == "publisher":
            for record in records:
                if "restates" not in record and not (work / signed_path(record["name"])).is_file():
                    signers.add(sign_record(work, plan, record))
            for record in records:
                if "withdraw" in record and not (work / withdrawal_path(record["name"])).is_file():
                    signers.add(withdraw_record(work, record))
            for record in records:
                if "restates" in record and not (work / signed_path(record["name"])).is_file():
                    signers.add(sign_record(work, plan, record))
            waiting = [
                c["name"] for c in plan["corroborations"] if not (work / corroboration_path(c["name"])).is_file()
            ]
            if waiting:
                print(f"corroborations waiting for the corroborator's run: {', '.join(waiting)}")
        else:
            for corroboration in plan["corroborations"]:
                if not (work / corroboration_path(corroboration["name"])).is_file():
                    signers.add(corroborate(work, plan, corroboration))

        if signers:
            for signer in sorted(signers):
                print(f"signer: {signer}")
        else:
            print(
                f"nothing to sign: every {'record' if mode == 'publisher' else 'corroboration'} in the plan is signed"
            )

        assemble_host(work, plan)
        passed = build_and_check(work)
        changes = differences(repo, work)
        if not passed:
            print("a check failed in the copy; nothing written")
            return 1
        if not changes:
            print("nothing written: the repository already holds this run's result")
            return 0
        print("would write:" if dry_run else "writing:")
        for kind, path in changes:
            size = "" if kind == "D" else f" ({(work / path).stat().st_size} bytes)"
            print(f"  {kind} {path}{size}")
        if dry_run:
            print("DRY_RUN=1: nothing written. Run again without DRY_RUN to write these files.")
            return 0
        apply(repo, work, changes)
        print(f"wrote {len(changes)} change(s); review them with git status and git diff, then commit")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("publisher", "corroborator"))
    parser.add_argument("--repo", type=Path, default=ROOT, help="the repository's root (default: this checkout)")
    args = parser.parse_args(argv)
    dry_run = os.environ.get("DRY_RUN", "") not in ("", "0")
    try:
        return run(args.repo.resolve(), args.mode, dry_run)
    except PlanError as err:
        return stop(f"sign_records: {err}", 2)
    except Refusal as err:
        return stop(f"sign_records: refused: {err}; nothing written", 1)
    except typedstandards.SeedError as err:
        return stop(
            f"sign_records: SeedError (exit {err.exit_code}): the CLI found no usable signing seed in the environment "
            f"this run inherited; nothing written. The CLI said: {err.stderr.strip()}",
            3,
        )
    except typedstandards.CliError as err:
        return stop(f"sign_records: {type(err).__name__}: {err}; nothing written", 1)


def stop(message: str, code: int) -> int:
    sys.stdout.flush()  # what the run printed comes before why it stopped
    print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
