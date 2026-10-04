# typedstandards-host-template

A GitHub template repository for serving signed [Typed Standards](https://typedstandards.org)
records from GitHub Pages under your own `did:key`. Copy it with "Use this template",
replace the example record with your own, and its workflow checks on every push that
what Pages serves is what [`@typedstandards/host-core`](https://www.npmjs.com/package/@typedstandards/host-core)
builds, and that every record verifies.

[![Verify this record with Typed Standards](https://typedstandards.org/badge/typed-standards-verify.svg)](<https://typedstandards.org/verify?url=https%3A%2F%2Fhost-template.typedstandards.org%2Fbundles%2Ffirst-note.bundle.json>)

- **What it pins.** `@typedstandards/host-core` 0.1.1, exactly, and
  [`@typedstandards/cli`](https://www.npmjs.com/package/@typedstandards/cli) 0.2.0,
  exactly, for signing. `package-lock.json` resolves both from the npm registry.
- **What it serves.** One example record: `records/first-note.md`, a short Markdown
  note signed under `raw-bytes/v1`.
- **What it holds.** No key. Signing runs in your own terminal. The workflow only
  builds, checks and verifies, so it needs no secret.

## Layout

| Path | What |
|---|---|
| `host.json` | The host manifest: the origin, the visibility, the registry and the records. host-core reads it. |
| `records/` | What you sign and what signing printed: the note, the input to `sign`, and `sign`'s output. Kept out of `docs/`. |
| `host-policy.json` | The display policy: which records a page shows, and as what. |
| `docs/` | What Pages serves. `bundles/`, `.well-known/typed-publisher.json` and `records.json` are `typedstandards-host build`'s output. `.nojekyll`, `CNAME` and `index.html` are written by hand; `CNAME` names this template's domain. |
| `verify-output.txt` | The golden: `typedstandards-host verify`'s output on `docs/`. |
| `display.mjs` | Reads every record through `host-policy.json` with host-core's `displayOf`, and exits 1 when one is refused. |
| `.github/workflows/check.yml` | The workflow. |
| `.gitleaks.toml` | Tells [gitleaks](https://github.com/gitleaks/gitleaks) that an Ed25519 `did:key` identifier is a public key, not a secret. Without it, gitleaks reads every `did:key` in the signed and served files as an API key. |

## What the workflow checks

On every push and pull request, on Node 24:

1. `npm ci` installs the exact versions `package-lock.json` pins.
2. `npx typedstandards-host check` rebuilds `docs/` in memory from `host.json` and
   `records/`, and compares it with the committed `docs/` byte for byte.
3. `npx typedstandards-host verify` verifies every served record offline, with the
   network blocked, and its output must equal `verify-output.txt`.
4. `node display.mjs` reads every record through `host-policy.json`, and none may be
   refused.

**Why Node 24, and not an exact version.** The workflow pins the major version, 24.
The first line of `verify`'s output names no Node version and no core version:

```
typedstandards-host verify: records.json lists 1 record, each verified offline by @typedstandards/verify-core with the network blocked
```

so the golden stays equal across Node 24 patches. `verify-output.txt` was written on
Node 24.21.0. A change of Node major, or of host-core version, is a reason to
[regenerate the golden](#regenerate-the-golden) and review its diff.

## What the records prove

This describes what `typedstandards-host verify` checks offline, over the served
bundles (`verify-output.txt`).

- **Attested:** checkable by anyone from the served bundle. The row names the check.
- **Asserted:** stated inside the signed bytes, resting on the signer's word. No check establishes it.
- **Host's statement:** served by the host, unsigned. A verifier reads it, and it shows
  what the host says, not who holds the key.
- **Not covered:** nothing in this repository addresses it.

| Property | Status | Why |
|---|---|---|
| The bytes of the signed file | Attested (#3, #4, #1) | The record carries the file's exact UTF-8 bytes inline, under `raw-bytes/v1` (#3). #4 recomputes `contentHash.sha256` from those bytes, and #1 recomputes the envelope hash. The digest is the file's ordinary SHA-256, so `shasum -a 256 records/first-note.md` checks it without any Typed Standards code. |
| The signature over the record | Attested (#2) | Ed25519ph over the envelope-hash hex string. |
| The identifier is the key's | Attested (#14, #6) | #14 reads `key_derived_match`: the `did:key` identifier is derived from the public key that signed. #6 reads `ok`: the signature's `kid` equals `metadata.signingKeyId`. |
| Whether a record is withdrawn | Attested (#10), for what the bundle carries | A withdrawal is a signed attestation carried in the unsigned bundle. `verify` checks each one's signature and signer, and that the status they give equals the one `records.json` states. A host could leave a withdrawal out, and the record's own signature cannot show that it was not withdrawn. |
| The served files are what host-core builds | Checked by `check`, not by a verifier | `check` rebuilds `docs/` from `host.json` and `records/` and compares byte for byte. The bundle's view fields that are not copied from the package (the title, the visibility, `trustRegistryUrl` and the registry copy) are the host's. `verify` checks that every copied field equals the package's. |
| The key is active | Host's statement | `.well-known/typed-publisher.json` lists the key as active from the first record's `createdAt`. `verify` reads it as the file a verifier fetches from `trustRegistryUrl`, and #5 reads `active`. That shows which host publishes the statement, not who holds the key. The registry is this template's own statement about its example key. It is not a Typed Standards record, and not an endorsement by the Typed Standards specification or by typedstandards.org, although this host is a subdomain of it. |
| Who holds the key | Not covered | The signer is a pseudonymous `did:key`. Its `displayName` names this template, not a person. The example record's key was generated for its one signature and deleted after it. |
| Revocation of the key | Not covered | A `did:key` has no rotation. host-core 0.1.1 serves the key as active, and `host.json` has no field to mark it revoked. Anyone who holds a leaked seed can sign as the identifier. |
| Capture method and producer profile | Asserted (#15) | #15 reads `ok`: `script-run` is a value the `scripted-recomputation` profile allows. The label is signed, so changing it breaks #1, but no check establishes it. |
| The display policy | Host's statement | `host-policy.json` is this host's rule for what a page shows. It is not signed, and no verifier reads it. |
| When the record existed | Not covered | #7 does not apply: no RFC 3161 token was requested. `createdAt` is the signer's own claim. |
| Inclusion in a transparency log | Not covered | #8 does not apply: no transparency-log entry was submitted. |
| That any statement in the file is correct | Not covered | A signature shows the bytes are unchanged since signing, not that they are true. |

A bundle carries no `lifecycle` summary in host-core 0.1.1. A record's status is in
`records.json`, in the display policy's reading, and in the verifier's own reading of
the carried attestations.

## The served URLs

Pages serves `docs/` from `main`, at the custom domain `docs/CNAME` names, over
HTTPS. With `origin` set as in `host.json`:

| URL | What |
|---|---|
| `https://host-template.typedstandards.org/` | `docs/index.html` |
| `https://host-template.typedstandards.org/bundles/first-note.bundle.json` | The example record's bundle |
| `https://host-template.typedstandards.org/records.json` | The index, version 1 |
| `https://host-template.typedstandards.org/.well-known/typed-publisher.json` | The key registry, the bundle's `trustRegistryUrl` |

The verifier link for the example record:

```
https://typedstandards.org/verify?url=https%3A%2F%2Fhost-template.typedstandards.org%2Fbundles%2Ffirst-note.bundle.json
```

### Serve it over HTTPS

The browser verifier runs on an HTTPS page, so it can fetch the bundle and the
registry only over HTTPS: a browser blocks an `http` fetch, or a redirect to `http`,
from an HTTPS page. In the repository's Pages settings, set the custom domain and
turn on **Enforce HTTPS**. Once Pages has deployed, check that `origin` answers over
HTTPS without a redirect:

```sh
curl -sI "https://host-template.typedstandards.org/records.json"   # expect HTTP 200, and no location header
```

### A site with a path prefix

This template's site has its own domain, so `origin` has no path. A copy served as
a project site with no custom domain is served under a path,
`https://<owner>.github.io/<repository>/`. `origin` then carries that path, with no
trailing `/`, and host-core puts every served URL under it, the registry included:
`<origin>/.well-known/typed-publisher.json`. A verifier finds the registry by the
URL each bundle names in `trustRegistryUrl`, not at the host's root.

If the account's user site (`<owner>.github.io`) has a custom domain, GitHub serves
the account's project sites under that domain instead, and the `github.io` URL
redirects there, possibly over `http`. Set `origin` to the URL Pages actually serves
over HTTPS, and check it with the `curl` above.

### Cross-origin reads

The browser verifier at typedstandards.org fetches the bundle and the registry from
another origin, so it needs the host to send `Access-Control-Allow-Origin`. On
2026-09-29, with `Origin: https://typedstandards.org`, this template's site answered
`HTTP/2 200` with `access-control-allow-origin: *` for four paths: the bundle, the
registry, `records.json` and `/`. The same day, the verifier at typedstandards.org,
given the bundle's URL, read "Verified", with the key active in the registry it
fetched. That is what was checked; a copy checks its own site once Pages has
deployed it:

```sh
curl -sI -H 'Origin: https://typedstandards.org' \
  "<origin>/bundles/<name>.bundle.json" \
  | grep -i '^access-control-allow-origin'
```

`docs/.nojekyll` stops Pages running Jekyll, which would leave `.well-known/` out of
the site.

## The badge snippet

`npx typedstandards-host links` prints each record's verifier link and badge
snippets, in the site's own percent-encoded form. The example record's HTML:

```html
<a href="https://typedstandards.org/verify?url=https%3A%2F%2Fhost-template.typedstandards.org%2Fbundles%2Ffirst-note.bundle.json">
  <img src="https://typedstandards.org/badge/typed-standards-verify.svg" alt="Verify this record with Typed Standards" width="248" height="30" />
</a>
```

and its Markdown:

```md
[![Verify this record with Typed Standards](https://typedstandards.org/badge/typed-standards-verify.svg)](<https://typedstandards.org/verify?url=https%3A%2F%2Fhost-template.typedstandards.org%2Fbundles%2Ffirst-note.bundle.json>)
```

The badge is a call to verify, not a verdict. `docs/index.html` links to the
verifier with text and shows no badge image, because the image is served by another
host and the page loads nothing from any other host.

## What a copy changes

1. **`docs/CNAME`, before you enable Pages.** Delete it, or replace its one line with
   your own domain. It names this template's domain, and GitHub Pages reads it as
   the site's custom domain, so a copy that keeps it would try to claim this
   template's domain instead of serving yours.
2. **`origin`** in `host.json`: the URL your Pages site is served at over HTTPS (see
   [a site with a path prefix](#a-site-with-a-path-prefix)). The registry's and the
   index's `$comment` strings are yours too: the registry's says whose statement it
   is.
3. **The record.** Remove the example record and sign your own (below). `build`
   deletes nothing, so the example's bundle is removed by hand; `check` reports a
   served bundle that `host.json` no longer lists.
4. **The policy.** `signer` in `host-policy.json` becomes your `did:key`, and the
   rules name your records' statuses and roles.
5. **`docs/index.html`**, by hand, and the URLs and badge in this README.
6. **The golden**, `verify-output.txt`, [regenerated](#regenerate-the-golden).
7. **Pages**, in the repository's settings: deploy from a branch, `main`, `/docs`;
   your custom domain, if any; and Enforce HTTPS.

## Sign your first record

In a copy of this template, on Node 24. The commands run from the repository's root.

```sh
npm ci
```

### 1. Make a key, and keep it out of the repository

The CLI reads the signing seed from one environment variable,
`TYPEDSTANDARDS_SIGNING_SEED_B64`: the base64 of 32 random bytes. It never prints the
seed and never writes it. Keep the seed in a secret store, as the
[CLI's README](https://www.npmjs.com/package/@typedstandards/cli) shows with
`op run`. At the least, keep it in a file only you can read, outside every
repository:

```sh
export KEY_FILE="$HOME/.typedstandards/signing-seed.b64"
mkdir -p "$(dirname "$KEY_FILE")"
test -e "$KEY_FILE" || ( umask 077 && openssl rand -base64 32 > "$KEY_FILE" )
```

Never commit the seed, print it, or add it to this repository's secrets: the
workflow signs nothing. The seed is the only way to sign, or withdraw, under your
`did:key`, so keep a backup. A `did:key` cannot be rotated.

### 2. Replace the example record

```sh
git rm -q docs/CNAME   # or write your own domain into it
git rm -q records/first-note.md records/first-note.signed.json docs/bundles/first-note.bundle.json
git mv records/first-note.input.json records/my-record.input.json
printf '# My record\n\nThe text I am signing.\n' > records/my-record.md
```

Edit `records/my-record.input.json`: set `signer.displayName` to the name you sign
under, and `prompt` to what the record is. The input is produce-core's envelope
input, which the [CLI's README](https://www.npmjs.com/package/@typedstandards/cli)
describes under `sign`.

### 3. Sign

```sh
TYPEDSTANDARDS_SIGNING_SEED_B64="$(cat "$KEY_FILE")" npx typedstandards sign \
  --input records/my-record.input.json --output-file records/my-record.md \
  > records/my-record.signed.json
```

`sign` verifies its own result offline before it prints. The file's bytes are signed
inline under `raw-bytes/v1`, so the file must be UTF-8.

### 4. Point `host.json` and the policy at your record

In `host.json`, set `origin`, and replace the example's entry in `records`:

```json
{ "name": "my-record", "signed": "records/my-record.signed.json", "attestations": [], "title": "My record", "extensions": { "role": "note" } }
```

In `host-policy.json`, set `signer` to your `did:key`, which this prints:

```sh
node -p 'require("./records/my-record.signed.json").package.signer.identifier'
```

### 5. Build, check, verify, and print the links

```sh
npx typedstandards-host build
npx typedstandards-host check
npx typedstandards-host verify > verify-output.txt
node display.mjs
npx typedstandards-host links
```

`build` writes `docs/`. `check` compares it with a fresh build. `verify` writes the
new golden; review it with `git diff verify-output.txt`. `links` prints the verifier
link and badge snippets for this README and `docs/index.html`. Commit, push, and the
workflow runs the same checks.

### 6. Withdraw a record

A signed record cannot be changed. A correction is a withdrawal plus a new record.
The withdrawal is signed with the same key:

```sh
node -e '
const s = require("./records/my-record.signed.json");
const input = { targetNodeId: s.envelopeHash, reason: "Replaced by a corrected record.", signer: { bindingTier: s.package.signer.bindingTier, displayName: s.package.signer.displayName } };
require("node:fs").writeFileSync("records/my-record.withdraw-input.json", JSON.stringify(input, null, 2) + "\n");
'
TYPEDSTANDARDS_SIGNING_SEED_B64="$(cat "$KEY_FILE")" npx typedstandards withdraw \
  --input records/my-record.withdraw-input.json > records/my-record.withdrawal.json
```

Add it to the record's `attestations` in `host.json`:

```json
"attestations": ["records/my-record.withdrawal.json"]
```

and run step 5 again. The record still verifies, `records.json` lists it as
`withdrawn` with the reason, and the policy's `withdrawn` rule displays it.

## The display policy, and a policy kept as YAML

`host-policy.json` is JSON with `$comment` strings. host-core reads JSON only. A
policy kept as YAML is converted first, with any YAML-to-JSON tool. With the
[`yaml`](https://www.npmjs.com/package/yaml) package's command:

```sh
npx --yes yaml@2.9.1 --json --single --strict --indent 2 < host-policy.yaml > host-policy.json
```

This YAML converts, byte for byte, to the committed `host-policy.json`:

```yaml
$comment: >-
  The display policy: which records a page shows, and as what. It is this host's
  own rule, not signed and not verified. Every rule names its statuses, so a status
  no rule names is refused. A copy of the template changes signer to its own did:key.
signer: did:key:z6Mks7BK2kyVhoPY3ayt6ALKeZY5eCbu64XyQuje9gTUxiUB
type: content/analysis/v1
display:
  - $comment: An active note is shown as current.
    status: active
    extensions:
      role: [note]
    as: current
  - $comment: A withdrawn record stays listed, marked withdrawn.
    status: withdrawn
    as: withdrawn
unmatched: refuse
```

A record's roles are host-specific, so they go under the record's `extensions` in
`host.json`, and a rule names the values it admits. A record is displayed by the
first rule it matches, and refused when its status is not `active`, `withdrawn` or
`superseded`, when `signer` or `type` does not name it, or when no rule matches.
`superseded` is displayed only when a rule names it.

## Visibility is host-wide

`visibility` in `host.json` is every record's disclosure state: host-core 0.1.1 has
no per-record visibility. It is never defaulted. Records that need different
visibilities need separate hosts.

## Regenerate the golden

`verify-output.txt` is `typedstandards-host verify`'s output on `docs/`. After any
change that alters it (a record added or withdrawn, a host-core upgrade, a new Node
major), regenerate it and review the diff:

```sh
npx typedstandards-host build
npx typedstandards-host check
npx typedstandards-host verify > verify-output.txt
git diff verify-output.txt
```

To upgrade host-core, pin the new version exactly, then regenerate:

```sh
npm install --save-exact @typedstandards/host-core@<version>
```

## License

MIT
