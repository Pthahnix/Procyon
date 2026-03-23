---
title: save_registry: TOCTOU race on file truncation before flock
priority: normal
tag: bug
date: 2026-03-23T07:15:24.898332
author: claude-code
status: open
---

open(..., 'w') truncates the file before fcntl.flock acquires the exclusive lock. Two concurrent writers can race. Fix: use a separate lockfile, or open with r+ after creation. Low risk for single-user workloads but not truly atomic.
