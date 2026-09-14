# GitHub branch protection setup

Production is **`main`**. The development / QA (soak) line is **`testing`**. There is no third long-lived branch.

Ruleset JSON for import lives in [rulesets/main.json](rulesets/main.json), [rulesets/testing.json](rulesets/testing.json), and [rulesets/allowed-branch-names.json](rulesets/allowed-branch-names.json). GitHub does not apply those files automatically; they must be imported in the UI or posted with the API.

## Create `testing` on GitHub first

The local repo may already have `testing`. Create the **remote** branch from current `main` **before** (or while) enabling the testing ruleset, or the first push can be rejected because PRs are required:

1. GitHub → **Code** → branch dropdown → **View all branches** → **New branch**
2. Name: `testing`, source: `main`
3. Or, after this workflow is on GitHub: `git push -u origin testing` (only if the testing ruleset is not yet active)

Do not force-push. Do not change the repository default branch; keep **`main`**.

## Apply via API (`gh`)

These rulesets were applied on this repo (active, no bypass):

- [Protect main](https://github.com/karthickme/windows_backup/rules/23175663)
- [Protect testing](https://github.com/karthickme/windows_backup/rules/23175667)
- [Allowed branch names](https://github.com/karthickme/windows_backup/rules/23176026)

Re-create (if deleted) from the repository root with `repo` scope:

```powershell
gh api repos/karthickme/windows_backup/rulesets --method POST --input .github/rulesets/main.json
gh api repos/karthickme/windows_backup/rulesets --method POST --input .github/rulesets/testing.json
gh api repos/karthickme/windows_backup/rulesets --method POST --input .github/rulesets/allowed-branch-names.json
```

Update: `gh api repos/karthickme/windows_backup/rulesets/23175663 --method PUT --input .github/rulesets/main.json`

Update allowed names: `gh api repos/karthickme/windows_backup/rulesets/23176026 --method PUT --input .github/rulesets/allowed-branch-names.json`

List: `gh api repos/karthickme/windows_backup/rulesets`

If a ruleset name already exists, PATCH by id instead of POST.

If GitHub rejects `integration_id`, drop that field and keep `"context": "test"` / `"protect-main"`. Those names must match the **job `name:`** in `.github/workflows/ci.yml` (`test`) and `.github/workflows/protect-main.yml` (`protect-main`). Checks appear in the branch ruleset picker only after the workflow has run at least once.

## Apply in the GitHub UI

**Settings → Rules → Rulesets → New ruleset → Import a ruleset** and select `main.json`, then `testing.json`, then `allowed-branch-names.json`.

Or create manually:

### Ruleset: Protect main

- Enforcement: Active
- Target branches: `main`
- Restrict deletions: on
- Block force pushes: on
- Require a pull request before merging: on
  - Required approvals: 0 (pytest is the gate; add reviewers if you want)
  - Dismiss stale reviews: on (optional)
- Require status checks to pass:
  - `test`
  - `protect-main`
  - Require branches to be up to date: on
- Bypass list: empty (admins included)

GitHub cannot reliably limit merge sources to `testing` only. That is enforced by the `protect-main` workflow (head must be `testing` or `hotfix/*`).

### Ruleset: Protect testing

- Same as main, but target `testing`
- Required status check: **`test` only** (not `pack`, not `protect-main`)
- Allow creating the branch if GitHub offers “do not enforce on create”

### Ruleset: Allowed branch names

If `gh api` POST fails, create this in the UI without changing Protect main / Protect testing:

1. **Settings → Rules → Rulesets → New ruleset → New branch ruleset**
2. Name: `Allowed branch names`
3. Enforcement: **Active**
4. Bypass list: empty (same as Protect main / Protect testing)
5. Target branches:
   - Include: **All branches** (`~ALL`)
   - Exclude by name or pattern:
     - `refs/heads/main`
     - `refs/heads/testing`
     - `refs/heads/feature/**`
     - `refs/heads/fix/**`
     - `refs/heads/deps/**`
     - `refs/heads/hotfix/**`
6. Restrictions: enable **Restrict creations** (do not add deletion, force-push, or PR rules here)

This only blocks creating branches whose names are not in that list. Existing Protect main / Protect testing rulesets stay as they are.

## Automatically delete head branches

Enable **Settings → General → Pull Requests → Automatically delete head branches** (`delete_branch_on_merge`). Feature, fix, Dependabot, and hotfix branches are removed after merge. **`main` and `testing` stay**: those rulesets restrict deletions, and GitHub does not delete the default branch.

```powershell
gh api repos/karthickme/windows_backup --method PATCH -f delete_branch_on_merge=true
```

Dependabot auto-merge also passes `--delete-branch`. Do not enable this if you still need a merged `hotfix/*` branch as the source of a follow-up PR into `testing` — merge into `testing` first, or leave the GitHub merge checkbox **Delete branch** unchecked for that PR.

## Default pull request base

The repository default branch stays **`main`**, so the GitHub “New pull request” screen still defaults the **base** to `main`. Switch the base to **`testing`** for features, fixes, and Dependabot. The pull request template reminds you. PRs whose base is `main` and whose head is not `testing` or `hotfix/*` fail `protect-main`.

## Hotfix exception

`hotfix/*` → `main` is allowed by `protect-main.yml`. After merge, also PR or merge into `testing` so QA does not regress.
