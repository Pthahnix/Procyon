---
name: procyon
description: >
  Master entry point for all Procyon operations.
  Routes to procyon-usage (daily operations) or procyon-iterate (development).
---

# Procyon — Process Guardian

Procyon is a process protection tool for long-running ML workloads. This skill routes you to the correct sub-skill based on your intent.

## Which skill do you need?

### Daily Operations → `procyon-usage`

Use when you need to **launch, monitor, or manage training processes**.

```
Skill: procyon-usage
```

Covers: `procyon status`, `procyon run`, `procyon register`, `procyon unregister`, `procyon issue`

### GPU Monitoring → `procyon-gpu`

Use when you need to **check GPU usage, VRAM, or find free GPUs**.

```
Skill: procyon-gpu
```

Covers: `procyon gpu`, `procyon gpu --pretty`, `procyon gpu --user USER`

### Development & Iteration → `procyon-iterate`

Use when a **human explicitly instructs you to improve Procyon itself**.

```
Skill: procyon-iterate
```

Covers: reading open issues, designing fixes, implementing on a branch, testing, creating PRs.

**WARNING:** `procyon-iterate` enforces a strict design-before-code pipeline (brainstorming → writing-plans → subagent-driven-development). Do NOT skip any phase.

## Quick Reference

| Task | Skill | Example |
|------|-------|---------|
| Check running jobs | `procyon-usage` | `procyon status --pretty` |
| Launch training | `procyon-usage` | `procyon run --name JOB -- cmd` |
| Check GPU usage | `procyon-gpu` | `procyon gpu --pretty` |
| Find free GPUs | `procyon-gpu` | `procyon gpu` (parse JSON) |
| File a bug | `procyon-usage` | `procyon issue --title "..." --body "..."` |
| Fix Procyon bugs | `procyon-iterate` | Human says "iterate on Procyon" |
| Add Procyon features | `procyon-iterate` | Human says "implement issue #NNN" |

## Rules

1. **NEVER** modify `procyon.py` outside the `procyon-iterate` workflow
2. **NEVER** use `kill`/`pkill`/`killall` on training processes — use Procyon
3. **ALWAYS** check `procyon status` before launching any training job
4. **ALWAYS** use `procyon run` wrapper for new jobs
