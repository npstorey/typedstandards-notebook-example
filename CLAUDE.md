# CLAUDE.md

`typedstandards-notebook-example`: a worked example of signing a notebook's files from Python
with [`typedstandards`](https://pypi.org/project/typedstandards/) (the Python wrapper over
`@typedstandards/cli`), served from GitHub Pages through the Typed Standards host template
(`@typedstandards/host-core`). The repository began as a copy of the host template; the README
says what it adds and what is still to come. It is served at `notebook.typedstandards.org`
(`docs/CNAME`, `host.json` `origin`).

Pins, all exact: `typedstandards` in `pyproject.toml` and `uv.lock`; `@typedstandards/host-core`
0.1.1 and `@typedstandards/cli` 0.2.0 in `package.json` and `package-lock.json`.

## Development loop

The system `python3` may be older than 3.12: run every Python command through `uv`. Node comes
from fnm; host-core needs Node 22 or later, and the workflow runs 24
(`eval "$(fnm env)" && fnm use 24`).

- `npm ci`, then `uv sync --locked`.
- `uv run pytest`: the example's tests. They run offline (an autouse fixture in
  `tests/conftest.py` makes socket connect and bind raise), against a copy of the repository in a
  temporary directory, never the checkout itself.
- `uv run scripts/verify_bundles.py`: `typedstandards.verify` over every bundle
  `docs/records.json` lists.
- `npx typedstandards-host check`, `npx typedstandards-host verify`, `node display.mjs`: the
  template's checks.

## The checks the workflow runs

`.github/workflows/check.yml`, on every push and pull request, holds two jobs, required by name
once the ruleset on `main` exists:

- `check`, on Node 24: `npm ci`; `npx typedstandards-host check`; `npx typedstandards-host verify`
  compared with `verify-output.txt`; `node display.mjs`. These are the template's steps, kept as
  they are.
- `verify-python`, on Node 24 and Python 3.12 through uv: `npm ci`; `uv sync --locked`;
  `uv run scripts/verify_bundles.py`, which fails unless every bundle reads `ok`;
  `uv run pytest`.

Every action is pinned to a full commit SHA, measured with `git ls-remote`, with its tag in a
comment.

## The repository holds no key

- The workflow holds no key of ours and reads no secret. Nothing in this repository signs on a
  runner.
- Signing runs only in the owner's terminal, through `op run`, with `DRY_RUN=1` first:
  `op run --env-file=<file> -- uv run scripts/sign_records.py <publisher|corroborator>`. The env
  file maps `TYPEDSTANDARDS_SIGNING_SEED_B64` to a secret reference and lives outside the
  repository (`*.env` is git-ignored as a backstop).
- `scripts/sign_records.py` signs through `typedstandards.sign`, `withdraw` and `attest`; the CLI
  reads the seed from the environment it inherits. No file under `scripts/` or `tests/` names that
  variable, passes `env=` to a child process, or changes `os.environ`, with one exception:
  `tests/conftest.py` sets a throwaway seed (32 bytes from `secrets`, generated for one test and
  discarded) with `monkeypatch.setenv`, and unsets it with `monkeypatch.delenv`.
  `tests/test_guards.py` enforces this, and fails on planted offenders.
- A test may sign a synthetic record under such a seed, as the wrapper's own tests do. No test
  writes a seed to disk or prints one, and a failing test prints no environment value.
- Both real seeds, the publisher's and the corroborator's, stay in the owner's secret store and
  are kept: a record whose key is gone can never be withdrawn or revised.

## What of an outside project may appear, and where

Only inside this repository; only the outside project's public repository URL, the commit, the
paths and the licence; and only after the owner's word. Until then nothing about any outside
project, dataset, portal resource or place enters any file, commit message or test here: tests
use synthetic content and reserved example domains (`example.org`, `example.com`). Outside this
repository (issues, PRs and commits elsewhere), nothing of it appears at all.

## Secret hygiene

Never load-and-print a credentials store — not even through a redaction filter. Two reads are
permitted: a field-scoped read by key **name** (`grep '^VAR_NAME='`, `jq` over non-secret
fields), or a command the tool itself exposes. Anything else is an owner-gate item. Carry this
into every IMPL spawn prompt verbatim. A security finding on a live public site stays off public
issues and PRs until its fix merges: the PR and its tests state the rule, not a walkthrough; the
details post after the merge.

## Commits, merges, gitleaks, phrasing

- `git commit -s` on every commit; the `Signed-off-by:` email must equal the author email
  exactly. Commits are signed (SSH). Read both at a gate with
  `git log --format='%h %G? %(trailers:key=Signed-off-by,valueonly)'`.
- Work lands by PR to `main` as a merge commit; never push to `main`.
- Before a push, run `gitleaks git --log-opts="main..HEAD" --no-banner` over the outgoing range.
  `.gitleaks.toml` allows only Ed25519 `did:key` identifiers, which are public keys; every
  signed and served file carries one. Do not widen it.
- Neutral phrasing in every tracked file and commit message: no stakeholder, organisation or
  person is named, beyond what the section above allows.

## Regenerate `verify-output.txt`

`verify-output.txt` is `npx typedstandards-host verify`'s output on `docs/`; the `check` job
diffs against it. `scripts/sign_records.py` rewrites it on every run that changes `docs/`. After
any other change that alters it (a host-core upgrade, a new Node major, a hand edit to
`host.json`), regenerate and review it:

```sh
npx typedstandards-host build
npx typedstandards-host check
npx typedstandards-host verify > verify-output.txt
git diff verify-output.txt
```
