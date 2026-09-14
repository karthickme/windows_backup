## Summary

<!-- What changed and why. -->

## Target branch

**Default: `testing`** (development / QA). GitHub’s form still lists `main` as base because that is the default branch — switch it.

- [ ] This PR targets **`testing`** (features, fixes, Dependabot)
- [ ] Promotion: head is **`testing`**, base is **`main`**
- [ ] Hotfix: head is **`hotfix/*`**, base is **`main`**, and a follow-up into **`testing`** is planned

PRs into **`main`** must come from **`testing`** or **`hotfix/*`**. The `protect-main` check fails anything else. Do not open routine feature PRs against `main`.

Merged **head** branches (`feature/*`, `fix/*`, `deps/*`, `hotfix/*`) are deleted automatically. **`testing` is not deleted** when promoting to `main`. Uncheck **Delete branch** on merge if you still need the head (for example a hotfix that must also PR into `testing`).

## Checklist

- [ ] Tests added or updated where it makes sense
- [ ] `test` (pytest on windows-latest) is expected to pass
- [ ] No secrets in YAML, logs, or this PR
