---
title: Fix incorrect ~/PROCYON path in Procyon usage docs
priority: normal
tag: bug
date: 2026-03-27T03:47:59.486008
author: claude-code
status: open
---

The current Procyon usage instructions reference `python3 ~/PROCYON/procyon.py ...`, but on this Linux machine the actual installed path is `python3 ~/Procyon/procyon.py ...`.

Because the filesystem is case-sensitive, the documented uppercase path fails with:

python3: can't open file '/home/pthahnix/PROCYON/procyon.py': [Errno 2] No such file or directory

Impact:
- Manual status checks fail if copied from the current instructions.
- Automated monitor prompts inherited the wrong path and repeatedly tried the nonexistent location.
- Users have to add a fallback or manually correct the path every time.

Expected:
- Update Procyon usage documentation / templates / generated prompts to use the correct installed path, or avoid hardcoding a case-sensitive home-directory path.

Observed working command on this machine:
- `python3 ~/Procyon/procyon.py status`
