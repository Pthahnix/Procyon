---
title: watchdog: lock file not updated after auto-restart
priority: low
tag: bug
date: 2026-03-23T07:15:24.967850
author: claude-code
status: open
---

watchdog_loop updates registry PID after restart but does not call remove_lock/write_lock for the new PID. Lock file retains the old dead PID until next stale-lock cleanup.
