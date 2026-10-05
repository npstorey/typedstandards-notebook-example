# typedstandards-notebook-example

A worked example of signing a notebook's files from Python with
[`typedstandards`](https://pypi.org/project/typedstandards/), the Python wrapper over
[`@typedstandards/cli`](https://www.npmjs.com/package/@typedstandards/cli), and serving the
signed records from GitHub Pages through the
[host template](https://github.com/npstorey/typedstandards-host-template) and
[`@typedstandards/host-core`](https://www.npmjs.com/package/@typedstandards/host-core). It is
served at `https://notebook.typedstandards.org`.

<!-- P3b: the verifier badge for the notebook record goes here (`npx typedstandards-host links`). -->

**Status.** The scaffold is in place: the signing script, the Python verify job, the display
policy and this README's structure. The example's own records are not signed yet. Until they
are, the site's one record is the host template's placeholder note, `records/first-note.md`,
signed under the template's throwaway key, because host-core serves no host with zero records.
The sections marked *to come* are filled when the records are signed.

## What it is, and what it is not

It is:

- **A file-by-file record of an analysis.** Each file is one record: an analysis notebook, a
  dashboard source and a graph file at a pinned commit of an outside project's public repository,
  each signed with `vcsRef` naming that repository, commit and path; a snapshot of each input the
  notebook retrieved, signed with its retrieval pin; and small claim files, one per claim that
  needs its own identity. Every record is `content/analysis/v1` under the
  `scripted-recomputation` producer profile, its file's exact bytes signed inline under
  `raw-bytes/v1`.
- **A lifecycle, shown once each way.** One claim is withdrawn with its reason and restated by a
  new record that names it; one claim is corroborated under a second key.
- **Signed in the owner's terminal, checked on every push.** The workflow holds no key.

It is not:

- **A verdict that the analysis is right.** A signature shows that the bytes are unchanged since
  signing and who signed them, not that any statement in them is true.
- **A statement by the outside project.** The records are this example's statements about the
  outside project's public files. Its own judgments stay where it made them; the records map to
  them and never duplicate them.
- **A Python producer or verifier.** `typedstandards` runs the CLI, which does all of the format's
  work. The scripts here arrange inputs and read results.

## Layout

| Path | What |
|---|---|
| `signing-plan.json` | What `scripts/sign_records.py` signs: the records, the withdrawals, the restatements, the corroborations ([the signing plan](#the-signing-plan)). |
| `records/` | What signing reads and prints, kept out of `docs/`: each record's input (`<name>.input.json`), `sign`'s output (`<name>.signed.json`), and a withdrawal's input and output (`<name>.withdraw-input.json`, `<name>.withdrawal.json`), plus each corroboration's input (`<name>.attest-input.json`). The files signed may live elsewhere in the repository; the plan names each one's path. |
| `host.json` | The host manifest host-core reads. `scripts/sign_records.py` writes its `records` from the plan; `origin`, `visibility` and the comments are written by hand. |
| `host-policy.json` | The display policy: which records a page shows, and as what. |
| `docs/` | What Pages serves. `bundles/`, `.well-known/typed-publisher.json` and `records.json` are `typedstandards-host build`'s output; `attestations/` holds the corroborations and what `attest` printed on stderr; `.nojekyll`, `CNAME` and `index.html` are written by hand. |
| `verify-output.txt` | The golden: `typedstandards-host verify`'s output on `docs/`. |
| `display.mjs` | Reads every record through `host-policy.json` with host-core's `displayOf`, and exits 1 when one is refused. |
| `scripts/sign_records.py` | The owner's signing script ([below](#how-the-owner-signs)). |
| `scripts/verify_bundles.py` | `typedstandards.verify` over every bundle `docs/records.json` lists. |
| `tests/` | The example's tests: the domain, the verify script, the signing script on a synthetic plan with throwaway seeds, and the guard that keeps the seed out of the code. |
| `pyproject.toml`, `uv.lock`, `.python-version` | The Python project: not a package, Python 3.12 or later, `typedstandards` pinned exactly. |
| `package.json`, `package-lock.json` | host-core 0.1.1 and the CLI 0.2.0, pinned exactly. |
| `.github/workflows/check.yml` | The workflow. |
| `.gitleaks.toml` | Tells gitleaks that an Ed25519 `did:key` identifier is a public key, not a secret. |
| `CLAUDE.md` | The repository's rules, for people and agents working in it. |

## What the workflow checks

On every push and pull request, two jobs, each holding no key and reading no secret:

**`check`**, on Node 24, the host template's steps unchanged:

1. `npm ci` installs the exact versions `package-lock.json` pins.
2. `npx typedstandards-host check` rebuilds `docs/` in memory from `host.json` and `records/`,
   and compares it with the committed `docs/` byte for byte.
3. `npx typedstandards-host verify` verifies every served record offline, with the network
   blocked, and its output must equal `verify-output.txt`.
4. `node display.mjs` reads every record through `host-policy.json`, and none may be refused.

**`verify-python`**, on Node 24 and Python 3.12:

1. `npm ci`, then `uv sync --locked`, which installs the exact `typedstandards` `uv.lock` pins.
2. `uv run scripts/verify_bundles.py` runs `typedstandards.verify` over every bundle
   `docs/records.json` lists, prints one line per bundle, and exits non-zero unless each reads
   `ok` with the status the index states.
3. `uv run pytest` runs the example's tests. They sign synthetic records under seeds they generate
   and discard, in a temporary copy of the repository.

The workflow pins Node's major version, 24, for the template's reason: the first line of
`verify`'s output names no Node version, so the golden stays equal across Node 24 patches.

`typedstandards` 0.1.0's `verify` sends a served bundle to the CLI on standard input, and fails
with `EAGAIN` on one larger than about 64 KB
([typedstandards-python#6](https://github.com/npstorey/typedstandards-python/issues/6)). The
placeholder's bundle is about 4 KB. The pin moves to the release that fixes it before the
example's records, some of them larger, are served.

## How the owner signs

Signing runs only in the owner's terminal, never on a runner. `scripts/sign_records.py` signs
through `typedstandards.sign`, `withdraw` and `attest`; the CLI they run reads the signing seed
from the environment it inherits. The script never names, reads, prints or passes the seed.

### Two keys, both kept

The publisher's key signs the records and the withdrawal. The corroborator's key signs the
corroboration, and must be a different key. Each is a seed, the base64 of 32 random bytes, kept
in a secret store. An env file outside the repository maps the CLI's variable to the store's
reference, never to a value:

```sh
# ~/.config/typedstandards/notebook-publisher.env
TYPEDSTANDARDS_SIGNING_SEED_B64=op://<vault>/<publisher item>/<field>
```

```sh
# ~/.config/typedstandards/notebook-corroborator.env
TYPEDSTANDARDS_SIGNING_SEED_B64=op://<vault>/<corroborator item>/<field>
```

Keep both seeds. A `did:key` cannot be rotated, and a record whose key is gone can never be
withdrawn or revised: the CLI signs a withdrawal only under the record's own key.

### The two modes, dry run first

From the repository's root, on Node 24, after `npm ci`:

```sh
DRY_RUN=1 op run --env-file="$HOME/.config/typedstandards/notebook-publisher.env" -- uv run scripts/sign_records.py publisher
op run --env-file="$HOME/.config/typedstandards/notebook-publisher.env" -- uv run scripts/sign_records.py publisher

DRY_RUN=1 op run --env-file="$HOME/.config/typedstandards/notebook-corroborator.env" -- uv run scripts/sign_records.py corroborator
op run --env-file="$HOME/.config/typedstandards/notebook-corroborator.env" -- uv run scripts/sign_records.py corroborator
```

- **`publisher`** signs every plan record that has no `records/<name>.signed.json` yet, then
  withdraws every record the plan withdraws that has no withdrawal yet, then signs the
  restatements.
- **`corroborator`** signs every plan corroboration not yet served, under the second key, and
  refuses one signed under the publisher's key. It runs after the publisher's run: it refuses
  while any record or withdrawal is unsigned.

Every run then writes `host.json`'s records from the plan, removes any served bundle the plan no
longer lists, rebuilds `docs/` (`typedstandards-host build`), sets `host-policy.json`'s `signer`
to the records' one `did:key`, and runs `typedstandards-host check`, `typedstandards-host
verify` (whose output becomes `verify-output.txt`) and `node display.mjs`.

**Every run works in a temporary copy of the repository.** Only when every check passes, and
`DRY_RUN` is unset, does it copy the files that differ back, listing each one. A run with nothing
to sign writes nothing. With `DRY_RUN=1` it prints what it would write, the signer's `did:key`,
and the copy's build, check, verify and display output, and leaves the repository byte-identical.
A dry run's signatures are discarded with the copy, so the live run signs afresh.

It refuses, writing nothing:

- a record whose file is no longer the file it signed (a signed record cannot change: withdraw it
  and sign a restatement);
- a restatement whose predecessor the plan does not withdraw;
- a file over 10 MiB (sign a retrieval manifest instead);
- records signed by more than one key (host-core serves one signer per registry);
- a corroboration signed under the publisher's key.

Exit codes: 0 ok; 1 a refusal, a failed check or a CLI error; 2 a malformed plan, or no
`node_modules` (run `npm ci`); 3 the CLI found no usable seed (`typedstandards.SeedError`),
for example when the run was not started under `op run`. No message prints the seed.

After a live run, review `git status` and `git diff`, update `docs/index.html` and this README by
hand, and commit.

### The signing plan

`signing-plan.json` is the one input. Top-level fields:

| Field | What |
|---|---|
| `producerProfile` | Signed in every record: `scripted-recomputation/notebook-example`. |
| `captureMethod` | Signed in every record: `script-run`. |
| `publisher`, `corroborator` | The `signer` each key signs under: `bindingTier` (`pseudonymous`), `displayName`, and optionally `identifier`, the key's `did:key`. With `identifier` set, the CLI refuses a seed that is not that key. |
| `records` | The records, in the order host-core serves them. |
| `corroborations` | The corroborations. |

A record:

| Field | What |
|---|---|
| `name` | Lowercase letters, digits and `-`; unique. Names the bundle (`bundles/<name>.bundle.json`) and the files under `records/`. |
| `role` | One of `analysis`, `dashboard-source`, `graph-file`, `retrieval`, `claim` (and `note`, the placeholder's). |
| `title` | The bundle's `subjectTitle`. |
| `file` | The path of the file signed inline, relative to the repository's root: UTF-8, 10 MiB or less. |
| `prompt` | The record's prompt, signed in full. |
| `summary` | Optional: a short summary, signed. |
| `vcsRef` | Optional: `{repoUrl, commitSha, path, ref?}`, signed as given: the file's source revision. |
| `pins` | Optional: the paths of retrieval entries that `typedstandards.pin(url, save=<file>)` wrote (`<file>.pin.json`); each becomes an entry of the record's `queries[]`. |
| `dataSources` | Optional: entries for the record's `dataSources[]`, signed as given. |
| `restates` | Optional: the name of the record this one restates. That record must be withdrawn in the same plan. |
| `withdraw` | Optional: `{reason}`. The publisher's run withdraws the record with this reason. Once signed, a withdrawal stays in the plan. |

A corroboration: `name` (unique among records and corroborations), `target` (a record's name),
`scope` (what is corroborated) and optionally `reasoning`.

**Where the role goes.** Each record's package signs its role under the reverse-DNS extensions
key `org.typedstandards.notebook` (this host's domain, reversed):
`"extensions": {"org.typedstandards.notebook": {"role": "claim"}}`. That is the signer's
assertion; no check reads it. `typedstandards.show(record, role_path=("org.typedstandards.notebook",
"role"))` renders it. The same role goes in `host.json` under the record's `extensions.role`,
which host-core copies into `records.json` and the display policy reads; that copy is the host's
statement.

**How a restatement names its predecessor.** The restatement's package signs the withdrawn
record's envelope hash twice: under `extensions` (`"restates": "<envelope hash>"`), and in its
`provenance` graph (PROV-O), where the restatement is `prov:wasRevisionOf` the node
`urn:org.typedstandards.notebook:envelope:<envelope hash>`. `host.json` names the predecessor by
record name under `extensions.restates`.

**Retrieval records.** The snapshot `pin` saved is the record's file, signed inline, so the
bundle carries its bytes and host-core's offline `verify` passes. A snapshot over 10 MiB, or one
whose terms do not allow a copy, is signed as a small manifest instead (its URL, SHA-256, byte
length and retrieval time), with the snapshot not committed; the manifest's digest is then a
signed assertion no check recomputes.

## The pinned files

*To come.*

<!-- P3b: the outside project's public repository URL, the pinned commit and its licence (only
     with the owner's word), and one row per signed file: its path at the commit, its role, the
     record's name, and the file's SHA-256, which a reader recomputes from the repository at that
     commit with `shasum -a 256 <path>`. -->

## The mapping

*To come.*

<!-- P3b: the mapping table: each of the outside project's own judgments, where it made it, and
     the record that maps to it, without restating its verdict. -->

## The records

*To come.*

<!-- P3b: one row per record: name, role, title, status (active or withdrawn, with the reason),
     and its bundle. -->

## The corroboration

*To come.*

<!-- P3b: the corroboration's target, its nodeId, its signer's did:key (not the publisher's), and
     the paths docs/attestations/<name>.json and docs/attestations/<name>.attest-stderr.txt. -->

The corroboration is signed with `attest` under the corroborator's key. `attest` checks the node
offline before it prints it (`checkAttestationNode`), and the signing script keeps what it
printed on stderr beside the node. It is served as a file beside the bundles, at
`docs/attestations/<name>.json`, and its `nodeId` is in the target record's `extensions` in
`host.json` and `records.json`. It is not carried in the target's bundle, because CLI 0.2.0 and
host-core 0.1.1 carry no claim-to-claim node in a view
([typedstandards#122](https://github.com/npstorey/typedstandards/issues/122)), and CLI 0.2.0
cannot verify an attestation on its own after signing
([typedstandards#120](https://github.com/npstorey/typedstandards/issues/120)). So neither
`typedstandards-host verify` nor the browser verifier reads it.

## Rerunning a pin against a moved source

*To come.*

<!-- P3b: the date, the URL, the digest the record signed, and the digest a rerun of
     typedstandards.pin read from the live source after it moved: a different digest, read as a
     different retrieval, not as a broken record. -->

## The served URLs and the badge

*To come.*

<!-- P3b: the table of served URLs under https://notebook.typedstandards.org (each bundle,
     records.json, .well-known/typed-publisher.json), the verifier link and badge snippets from
     `npx typedstandards-host links`, and the cross-origin check:
     curl -sI -H 'Origin: https://typedstandards.org' "<url>" | grep -i '^access-control-allow-origin' -->

## What the records prove

This describes what the checks establish over the served bundles, and what rests on a signer's
word.

- **Attested:** checkable by anyone from the served bundle. The row names the check.
- **Asserted:** stated inside the signed bytes, resting on the signer's word. No check
  establishes it.
- **Checked at signing:** checked by the CLI when it signed, and not checkable from what is
  served.
- **Host's statement:** served by the host, unsigned. It shows what the host says, not who holds
  the key.
- **Not covered:** nothing in this repository addresses it.

| Property | Status | Why |
|---|---|---|
| The bytes of each signed file | Attested (#3, #4, #1) | The record carries the file's exact UTF-8 bytes inline, under `raw-bytes/v1` (#3). #4 recomputes `contentHash.sha256` from those bytes, and #1 recomputes the envelope hash. The digest is the file's ordinary SHA-256, so `shasum -a 256 <file>` checks it without any Typed Standards code. |
| The signature over each record | Attested (#2) | Ed25519ph over the envelope-hash hex string. |
| The identifier is the key's | Attested (#14, #6) | #14 reads `key_derived_match`: the `did:key` is derived from the public key that signed. #6: the signature's `kid` equals `metadata.signingKeyId`. |
| A record is withdrawn, with its reason | Attested (#10), for what the bundle carries | The withdrawal is a signed attestation carried in the record's bundle; `verify` checks its signature and signer, and that the status it gives equals the one `records.json` states. A host could leave a withdrawal out, and the record's own signature cannot show that it was not withdrawn. |
| A restatement names the record it restates | Asserted | The restatement's package signs the withdrawn record's envelope hash under `extensions` and in `provenance`. No check follows the link. |
| A record's role | Asserted; the index's copy is the host's statement | Signed under `extensions["org.typedstandards.notebook"].role`; no check reads it. `host.json` and `records.json` repeat it for the display policy. |
| The source revision (`vcsRef`) | Asserted; not fetched | The repository URL, commit and path are signed as given. No check fetches the repository or compares the file at that commit. The pin table lets a reader recompute each file's SHA-256 from the repository at that commit. |
| The retrieval pins | Asserted | Each `queries[]` entry (URL, SHA-256, byte length, HTTP status, retrieval time, and a portal's `rowsUpdatedAt` where it gave one) is a signed assertion. No check fetches the URL or recomputes the digest (spec §8.7.5 item 7). An inline snapshot's bytes are attested as the record's output (#4); the claim that the URL served them rests on the signer's word. |
| The corroboration | Checked at signing; its `nodeId` in the index is the host's statement | `attest` checked the node's integrity and signature before printing it; the script keeps its stderr. It is served beside the bundle and not carried in it ([#122](https://github.com/npstorey/typedstandards/issues/122)); CLI 0.2.0 has no standalone check for it ([#120](https://github.com/npstorey/typedstandards/issues/120)). Its signer is a second pseudonymous `did:key`; that two keys signed does not show that two people did. |
| The served files are what host-core builds | Checked by `check`, not by a verifier | `check` rebuilds `docs/` from `host.json` and `records/` and compares byte for byte. The bundle's view fields that are not copied from the package (the title, the visibility, `trustRegistryUrl` and the registry copy) are the host's. `verify` checks that every copied field equals the package's. |
| The key is active | Host's statement | `.well-known/typed-publisher.json` lists the key as active from the first record's `createdAt`, and #5 reads `active`. That shows which host publishes the statement, not who holds the key. It is this example's statement, not a Typed Standards record, and not an endorsement by the specification or by typedstandards.org, although this host is a subdomain of it. |
| Who holds the keys | Not covered | The signers are pseudonymous `did:key`s. A `displayName` is self-described. |
| Revocation of a key | Not covered | A `did:key` has no rotation, and `host.json` has no field to mark a key revoked. Anyone who holds a leaked seed can sign as its identifier. |
| Capture method and producer profile | Asserted (#15) | #15 reads `ok`: `script-run` is a value the `scripted-recomputation` profile allows. The label is signed, but no check establishes it. |
| The display policy | Host's statement | `host-policy.json` is this host's rule for what a page shows. It is not signed, and no verifier reads it. |
| When a record existed | Not covered | #7 does not apply: no RFC 3161 token was requested. `createdAt` is the signer's own claim. |
| Inclusion in a transparency log | Not covered | #8 does not apply: no transparency-log entry was submitted. |
| That any statement in a file is correct | Not covered | A signature shows the bytes are unchanged since signing, not that they are true. |

## Visibility is host-wide

`visibility` in `host.json` is every record's disclosure state: host-core 0.1.1 has no
per-record visibility. It is `public`.

## Regenerate the golden

`verify-output.txt` is `typedstandards-host verify`'s output on `docs/`. The signing script
rewrites it on every run that changes `docs/`. After any other change that alters it (a
host-core upgrade, a new Node major, a hand edit to `host.json`), regenerate it and review the
diff:

```sh
npx typedstandards-host build
npx typedstandards-host check
npx typedstandards-host verify > verify-output.txt
git diff verify-output.txt
```

## License

MIT
