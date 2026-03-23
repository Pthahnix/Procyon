---
name: procyon-iterate
description: >
  Use when instructed by a human to iterate on Procyon.
  Reads issues/, plans upgrades, develops on a branch, runs tests, creates PR.
  ONLY triggered by explicit human command.
---

# Procyon — Iteration Upgrade SOP

## Prerequisites
- Human has explicitly instructed you to iterate on Procyon
- You are in the PROCYON project directory

## Workflow

### 1. Read Open Issues
```bash
grep -l "status: open" issues/*.md
```
Read each open issue file to understand what needs to change.

### 2. Snapshot Current Version
```bash
VERSION=$(cat VERSION | tr -d '[:space:]')
git checkout main && git pull
git tag "v${VERSION}-stable"
git push origin "v${VERSION}-stable"
```

### 3. Create Feature Branch
```bash
git checkout -b procyon/issue-NNN-short-description
```
Branch name references the primary issue number.

### 4. Develop
- Modify `procyon.py` and/or `tests/test_procyon.py`
- Follow TDD: write failing test → implement → verify pass
- Do NOT modify skill files, install.sh, or CLAUDE.md without human approval

### 5. Test
```bash
python3 -m pytest tests/test_procyon.py -v
```
ALL tests must pass. If any fail, fix or revert.

### 6. Commit and Push
```bash
git add procyon.py tests/test_procyon.py
git commit -m "fix/feat: description (closes #NNN)"
git push -u origin procyon/issue-NNN-short-description
```

### 7. Create PR
```bash
gh pr create --title "short title" --body "## Summary\n- what changed\n\nCloses #NNN"
```

### 8. Report to Human
Tell the human:
- What changed and why
- Link to the PR
- Test results
- Wait for "merge" instruction

### 9. Merge (on human approval)
```bash
gh pr merge --merge
git checkout main && git pull
```

### 10. Bump Version + Tag
```bash
# Bump patch version (or minor for features)
echo "0.1.1" > VERSION
git add VERSION
git commit -m "chore: bump version to 0.1.1"
git tag v0.1.1
git push && git push --tags
```

### 11. Close Issues
Edit each resolved issue file: change `status: open` to `status: resolved`.
Commit and push.

### 12. Deploy
Sync updated procyon.py to server if needed.

## Rollback (if something breaks after merge)
```bash
git checkout main
git checkout v{PREVIOUS_VERSION}-stable -- procyon.py
python3 -m pytest tests/test_procyon.py -v  # verify old version works
git commit -m "revert: rollback procyon.py to v{PREVIOUS_VERSION}"
git push
```
File an issue explaining what went wrong.
