# Versioning & Branch Model

Custom Ledger supports two Frappe major versions in parallel. Each lives on its own
long-lived branch.

| Branch | Frappe | Python | Role |
| --- | --- | --- | --- |
| `main` | v15 | 3.10–3.14 | Default branch, primary development line |
| `version-16` | v16 | 3.14 | v16-compatible release line |

The application code is identical on both branches — Custom Ledger uses only stable
core Frappe APIs (`frappe.get_doc`, `frappe.db.*`, `frappe.get_meta`,
`frappe.cache`, …) that behave the same in v15 and v16. The **only** differences
between the branches are version-metadata:

- `pyproject.toml` → `requires-python` and the (commented) `frappe~=` pin
- `README.md` → version badges, the Requirements section, and the compatibility table

Keep those files in mind when porting a change — they are the expected conflict
points during a cherry-pick, and the resolution is always "keep each branch's own
version numbers."

## Workflow: shipping a feature or fix to both versions

We develop once and apply the change to both branches with `git cherry-pick`.
`main` is the source of truth; `version-16` follows it.

1. **Branch off `main`** and do the work there:
   ```bash
   git checkout main && git pull
   git checkout -b feat/my-change      # or fix/my-change
   # ...commit...
   ```

2. **Open a PR into `main`** and merge it as usual.

3. **Cherry-pick the merged commit(s) onto `version-16`:**
   ```bash
   git checkout version-16 && git pull
   git checkout -b port/my-change-v16
   git cherry-pick <sha>...<sha>        # the commit(s) that landed on main
   # resolve metadata conflicts if the change touched pyproject.toml / README.md
   ```

4. **Open a second PR into `version-16`** and merge it.

A change is not "done" until it exists on **both** branches.

### Tips

- Cherry-pick a squash-merged PR with its single merge-commit SHA:
  `git cherry-pick <squash-sha>`.
- If a change is genuinely v16-only (uses an API that doesn't exist in v15),
  it lands only on `version-16` — note that in the PR description.
- If a change is genuinely v15-only, it lands only on `main`.
- Conflicts during cherry-pick are almost always the version-metadata files
  above. Keep the target branch's version numbers; take the feature's code.

## When a new Frappe major arrives (e.g. v17)

1. Branch the current top version: `git checkout version-16 && git checkout -b version-17`.
2. Bump `requires-python`, badges, Requirements, and the compatibility table.
3. Add a row here and to each branch's README compatibility table.

## Testing without a local site

There is currently no local v15/v16 bench for manual testing. CI is the most
reliable way to verify both branches actually install and pass their unit tests
against the matching Frappe version. Adding a GitHub Actions workflow per branch
(installing `frappe` `version-15` on `main` and `version-16` on `version-16`,
then running `bench run-tests --app custom_ledger`) is the recommended next step.
