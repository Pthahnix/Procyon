---
title: daemonize: leaks inherited file descriptors
priority: low
tag: improvement
date: 2026-03-23T07:15:25.103737
author: claude-code
status: resolved
---

After double-fork daemonization, only sys.stdin/stdout/stderr are redirected to /dev/null. All other inherited fds remain open. Standard practice: close fds > 2 via os.closerange().
