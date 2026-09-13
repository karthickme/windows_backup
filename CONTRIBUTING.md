# Contributing

## Git strategy (`main` + `testing`)

This repo uses two long-lived branches. Feature work lands on **testing** first (development / QA / soak). **main** is production. There is no third long-lived `development` branch.

```
feature/*  ──PR──►  testing  ──►  GitHub pre-release (beta exe)
fix/*      ──PR──►     │
deps/*     ──PR──►     │
                       └──PR──►  main  ──►  GitHub Release (stable exe)
hotfix/* ──PR──► main ─┴── also PR/merge into testing
```

Branch protection is documented in [.github/SETUP.md](.github/SETUP.md) and encoded in [.github/rulesets/](.github/rulesets/). SemVer for the exe still comes from [GitVersion.yml](GitVersion.yml) (GitHub Flow on `main` / tags).

### `main` (production)

- Production-ready code only.
- A **stable** GitHub Release (Windows zip, `prerelease: false`, marked latest) is created on push/merge to `main`. The tag is GitVersion **MajorMinorPatch** with no suffix, for example `0.1.0`.
- Direct pushes, force pushes, and deletions are blocked. Merge **only** via pull request.
- Head branch must be **`testing`** or **`hotfix/*`** (`protect-main` check). Classic GitHub protection cannot always restrict “only from testing”; the workflow plus a ruleset cover that.
- Required status checks: **`test`** (pytest on `windows-latest`) and **`protect-main`**. PyInstaller (`pack`) runs after merge (push to `main`); it is not a merge gate.

### `testing` (development / QA)

- Integration and soak branch. Merge feature, fix, and Dependabot PRs here first.
- Require a pull request; required status check **`test`** (pytest). That is the merge-to-testing gate. Push to `testing` also runs pytest.
- After merge, CI packs the Windows exe and creates/updates a **beta GitHub pre-release** (`prerelease: true`, not latest). Tag is **MajorMinorPatch** + `-beta` (for example `0.1.0-beta`), not `0.1.0-beta.1`. A later merge to `testing` moves that tag and replaces the zip; if GitHub forbids moving the tag, CI falls back to `0.1.0-beta.N`.
- When `testing` is stable, open a PR **testing → main** to promote to a stable release.

### Branch names

Only these names may be created (enforced by the **Allowed branch names** ruleset):

- `main` (already exists; do not create extra production branches)
- `testing`
- `feature/*`
- `fix/*`
- `deps/*`
- `hotfix/*`

Nested names under those prefixes (for example `feature/foo/bar`) are allowed. Other names are rejected.

### Feature branches

Create from **`testing`**, not from `main`, unless you are doing a hotfix.

| Prefix | Use |
| --- | --- |
| `feature/*` | New work |
| `fix/*` | Non-urgent bug fixes |
| `deps/*` | Dependency updates (Dependabot) |

PR target: **`testing`**, unless it is a hotfix or a promotion of `testing` itself.

GitHub still defaults the PR **base** to `main` (repository default branch). Switch the base to `testing` for routine work. See the pull request template.

### Hotfixes

1. Branch from **`main`** (`hotfix/…`).
2. Open a PR into **`main`**. `protect-main` allows `hotfix/*`. **`test`** must pass.
3. Also merge the same change into **`testing`** (second PR, or merge `main` back into `testing`) so QA does not regress.

### Pull request flow

1. `feature/*` / `fix/*` / `deps/*` → `testing` (pytest required) → **beta / pre-release**
2. Soak / QA on `testing` (download the pre-release exe, not the latest stable)
3. `testing` → `main` when stable (pytest + `protect-main` required) → **stable release**
4. Optional: manual tags still publish; a hyphen (for example `0.1.0-beta`) is beta, otherwise stable (for example `0.1.0`)

Never commit directly to `main`. Avoid committing directly to `testing` as well; use a PR.

Production users should only download GitHub Releases that are **not** marked as pre-release.

### Dependabot

[`.github/dependabot.yml`](.github/dependabot.yml) sets `target-branch: testing` for pip and GitHub Actions so updates soak in QA before production.

### CI

- Job **`test`**: pytest on `windows-latest` for pull requests to `testing` and `main`, and for pushes to `testing` and `main` (required check name remains **`test`**).
- Job **`pack`**: GitVersion + PyInstaller + zip; runs on push to `testing` (beta tag `0.1.0-beta`), push to `main`/`master` (stable tag `0.1.0`), manual version tags, and optional `workflow_dispatch`. Not required to merge into `testing`. Uses `contents: write` to create the GitHub Release and retarget the reusable beta tag. There is no `release: published` trigger, so assets are not attached twice.
- Workflow **`protect-main`**: PRs targeting `main` must come from `testing` or `hotfix/*`.
