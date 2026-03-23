---
title: procyon.py file permissions should be 0755 not 0775
priority: low
tag: improvement
date: 2026-03-23T07:15:25.035842
author: claude-code
status: open
---

procyon.py is currently 0775 (group-writable). Should be chmod 755 to prevent group members from modifying the guardian.
