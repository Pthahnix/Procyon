---
name: procyon-usage
description: >
  Use when launching, monitoring, or managing ML training processes.
  MUST be invoked before starting any training job, killing any process,
  or checking training status on the server.
---

# Procyon — Process Guardian Usage

## MANDATORY: Before ANY Training Launch

1. Run `python3 ~/PROCYON/procyon.py status` to check for existing jobs
2. Parse the JSON output — if any job has the same `checkpoint_dir` or `name`, DO NOT launch
3. Use wrapper mode to launch: `python3 ~/PROCYON/procyon.py run --name <name> --checkpoint_dir <path> -- <training_command>`

## Commands Reference

### Check status (ALWAYS do this first)
```bash
python3 ~/PROCYON/procyon.py status
```
Returns JSON array. Check `alive` and `checkpoint_dir` fields.

### Launch protected training (preferred)
```bash
python3 ~/PROCYON/procyon.py run --name <unique_name> \
  --checkpoint_dir <path> \
  -- python3 scripts/train_rvq.py <args...>
```

### Register existing process (script integration)
```bash
python3 ~/PROCYON/procyon.py register --name <name> --pid <pid> --cmd "<full_cmd>" --checkpoint_dir <path>
```

### Unregister on clean exit
```bash
python3 ~/PROCYON/procyon.py unregister --name <name>
```

### File an issue
```bash
python3 ~/PROCYON/procyon.py issue --title "description" --body "details" --tag bug
```

## RULES — NON-NEGOTIABLE

1. **NEVER** use `kill`, `pkill`, or `killall` on any training process
2. **NEVER** use `procyon kill` — it will reject you (no TTY)
3. **ALWAYS** check `procyon status` before launching anything
4. **ALWAYS** use `procyon run` wrapper mode for new training jobs
5. If you encounter a Procyon bug or limitation, use `procyon issue` to report it — do NOT modify procyon.py yourself
6. All procyon commands output JSON by default — parse it, don't regex stdout
