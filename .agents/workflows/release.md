---
description: Create a new release and increment version numbers
---

# Release Workflow

This workflow ensures that you correctly update **all** relevant version identifiers when releasing a new feature or hotfix. Use this workflow whenever you mention a new version number (e.g. "v2.11.2") to the user or in your commits.

## Steps to follow for EVERY version bump

1. **Update `VERSION` File**
   Update the exact semantic version (e.g., `2.11.2`) in the `VERSION` file located in the repository root.

2. **Update `config.yaml`**
   Update the `version: "..."` property inside `azubi_werkzeug/config.yaml`. This ensures that add-on supervisors load the correct image tag/version.

3. **Update `CHANGELOG.md`**
   Add a new block with the new version number at the top of the changelog following the current format (e.g. `## [2.11.2] - 2026-03-07`). Document all changes clearly.

4. **Verify Application Code (If applicable)**
   Check if there are hardcoded version strings inside the application that need alignment. Currently `app.py` loads the version dynamically, but ensure fallback versions (e.g., `0.0.0-unknown`) remain unchanged to explicitly signal missing values.

5. **Commit the Process**
   If you bumped the version, commit those three files with an explicit message: `git commit -m "chore(release): bump version to x.y.z"`
