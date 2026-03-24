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

<HARD-GATE>

## MANDATORY: Full Design-Before-Code Pipeline

You MUST follow the complete brainstorming → writing-plans → subagent-driven-development pipeline. NO exceptions. NO shortcuts. Do NOT write any implementation code until specs and plans are written and approved.

The workflow is strictly:

1. **Read issues** → understand what needs to change
2. **Invoke `superpowers:brainstorming`** → full design process (clarifying questions, approach proposals, design presentation, spec document, spec review loop, user approval)
3. **Invoke `superpowers:writing-plans`** → full implementation plan (file structure, bite-sized tasks with TDD, plan review loop)
4. **Execute via `superpowers:subagent-driven-development` using Sonnet agents** → one subagent per task, review between tasks

Skipping steps 2 or 3 is FORBIDDEN. You may NOT jump from reading issues directly to coding. The brainstorming skill's full checklist must be completed. The writing-plans skill's full process must be completed. Only after both spec and plan documents are written, reviewed, and approved by the user may you begin implementation.

</HARD-GATE>

## Workflow

### Phase 1: Discover

#### 1.1 Read TODO Tracker
Read `issues/TODO.md`. Unchecked items (`- [ ]`) are the open issues to address.
Follow each link to read the full issue file and understand what needs to change.

#### 1.2 Present Issues to Human
Summarize all unchecked issues from TODO.md. Ask the human which issues to address in this iteration (all, or a subset). Wait for confirmation before proceeding.

### Phase 2: Design (MANDATORY)

#### 2.1 Invoke Brainstorming Skill
```
Skill: superpowers:brainstorming
```
Follow the COMPLETE brainstorming checklist:
- Explore project context
- Ask clarifying questions (one at a time)
- Propose 2-3 approaches with trade-offs
- Present design section by section, get user approval
- Write design spec to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
- Run spec review loop (dispatch spec-document-reviewer subagent)
- User reviews written spec

Do NOT skip any step. Do NOT combine multiple questions into one message.

#### 2.2 Invoke Writing-Plans Skill
```
Skill: superpowers:writing-plans
```
Follow the COMPLETE writing-plans process:
- Map out file structure
- Define bite-sized tasks with TDD (failing test → implement → verify → commit)
- Include exact file paths, complete code, exact commands
- Run plan review loop (dispatch plan-document-reviewer subagent)
- Save plan to `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`
- User approves plan

### Phase 3: Implement

#### 3.1 Snapshot Current Version
```bash
VERSION=$(cat VERSION | tr -d '[:space:]')
git checkout main && git pull
git tag "v${VERSION}-stable"
git push origin "v${VERSION}-stable"
```

#### 3.2 Create Feature Branch
```bash
git checkout -b procyon/issue-NNN-short-description
```
Branch name references the primary issue number.

#### 3.3 Execute via Subagent-Driven Development
```
Skill: superpowers:subagent-driven-development
```
- Dispatch one **Sonnet** subagent per task from the plan
- Review between tasks
- Each subagent follows TDD: write failing test → implement → verify pass → commit
- Do NOT modify skill files, install.sh, or CLAUDE.md without human approval

#### 3.4 Test
```bash
python3 -m pytest tests/test_procyon.py -v
```
ALL tests must pass. If any fail, fix or revert.

### Phase 4: Ship

#### 4.1 Push and Create PR
```bash
git push -u origin procyon/issue-NNN-short-description
gh pr create --title "short title" --body "## Summary
- what changed

Closes #NNN"
```

#### 4.2 Report to Human
Tell the human:
- What changed and why
- Link to the PR
- Test results
- Wait for "merge" instruction

#### 4.3 Merge (on human approval)
```bash
gh pr merge --merge
git checkout main && git pull
```

#### 4.4 Bump Version + Tag
```bash
# Bump patch version (or minor for features)
echo "0.X.X" > VERSION
git add VERSION
git commit -m "chore: bump version to 0.X.X"
git tag v0.X.X
git push && git push --tags
```

#### 4.5 Close Issues
For each resolved issue:
1. Edit the issue file: change `status: open` to `status: resolved`
2. Edit `issues/TODO.md`: change `- [ ]` to `- [x]` for each resolved item
Commit and push.

#### 4.6 Deploy
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
