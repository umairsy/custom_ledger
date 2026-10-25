# Versioning & Branch Model

Custom Ledger supports Frappe v15 and v16 in parallel. Development happens on
`main`; two long-lived release branches track each supported Frappe major.

| Branch | Frappe | Python | Role |
| --- | --- | --- | --- |
| `main` | v15 & v16 | 3.10–3.14 | Primary development line. Broad Python range so it installs on both versions. |
| `version-15` | v15 | 3.10–3.14 | Frappe v15 release line. |
| `version-16` | v16 | 3.10–3.14 | Frappe v16 release line. |

The application code is identical on all branches — Custom Ledger uses only stable
core Frappe APIs (`frappe.get_doc`, `frappe.db.*`, `frappe.get_meta`,
`frappe.cache`, …) that behave the same in v15 and v16. The **only** differences
between the branches are version-metadata:

- `pyproject.toml` → `requires-python` and the (commented) `frappe~=` pin
- `README.md` → version badges, the Requirements section, and the compatibility table
- `.github/workflows/ci.yml` → the `FRAPPE_BRANCH` the tests run against

Keep those files in mind when porting a change — they are the expected conflict
points during a cherry-pick, and the resolution is always "keep each branch's own
version numbers."

## Workflow: shipping a feature or fix to all branches

We develop once and apply the change to both release branches with `git cherry-pick`.
`main` is the source of truth; `version-15` and `version-16` follow it.

1. **Branch off `main`** and do the work there:
   ```bash
   git checkout main && git pull
   git checkout -b feat/my-change      # or fix/my-change
   # ...commit...
   ```

2. **Open a PR into `main`** and merge it as usual.

3. **Cherry-pick the merged commit(s) onto each release branch:**
   ```bash
   for b in version-15 version-16; do
     git checkout "$b" && git pull
     git checkout -b "port/my-change-$b"
     git cherry-pick <sha>...<sha>      # the commit(s) that landed on main
     # resolve metadata conflicts if the change touched pyproject.toml / README.md
   done
   ```

4. **Open a PR into each release branch** and merge it.

A change is not "done" until it exists on **all three** branches.

### Tips

- Cherry-pick a squash-merged PR with its single merge-commit SHA:
  `git cherry-pick <squash-sha>`.
- If a change is genuinely v16-only (uses an API that doesn't exist in v15),
  it lands only on `version-16` — note that in the PR description.
- If a change is genuinely v15-only, it lands only on `version-15`.
- Conflicts during cherry-pick are almost always the version-metadata files
  above. Keep the target branch's version numbers; take the feature's code.

## When a new Frappe major arrives (e.g. v17)

1. Branch the current top version: `git checkout version-16 && git checkout -b version-17`.
2. Bump `requires-python`, badges, Requirements, and the compatibility table.
3. Add a row here and to each branch's README compatibility table.

## Testing without a local site

CI is the most reliable way to verify each branch actually installs and passes its
unit tests against the matching Frappe version. The
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) workflow does this: it
runs the Frappe semgrep rules and boots a real bench (Frappe branch set by the
`FRAPPE_BRANCH` env — `version-16` on `main`/`version-16`, `version-15` on
`version-15`) before running `bench run-tests --app custom_ledger`.
