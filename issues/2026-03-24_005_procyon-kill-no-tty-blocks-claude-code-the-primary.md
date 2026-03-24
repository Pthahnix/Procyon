---
title: "procyon kill NO_TTY blocks Claude Code — the primary operator"
priority: normal
tag: bug
date: 2026-03-24T04:30:08.910721
author: claude-code
status: resolved
---

## Problem

`procyon kill --name <job>` rejects with NO_TTY error when called from Claude Code's non-interactive shell. Claude Code is the primary tool that launches and manages Procyon jobs, but it cannot stop them.

## Error

```json
{"status": "error", "code": "NO_TTY", "message": "Kill requires an interactive terminal. Refusing non-interactive kill to protect against rogue agents."}
```

## Impact

- User explicitly requested stop, but Claude Code cannot execute it
- Only workaround: user manually types the command in a separate terminal
- Defeats the purpose of Procyon as a process guardian for agent workflows

## Suggested Fix

Add a `--yes` or `--confirm` flag that bypasses the TTY check, e.g.:

```bash
python3 procyon.py kill --name COLOSSUS --yes
```

This preserves safety (default still requires TTY) while allowing authorized non-interactive use.
