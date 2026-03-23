# Procyon — Process Guardian

## What is Procyon?

Procyon is a lightweight process protection tool for long-running ML workloads on shared servers. It solves two problems:

1. **Anti-duplicate**: Prevent a process from being launched twice into the same job slot (e.g., two training runs writing to the same checkpoint dir).
2. **Kill protection**: Auto-restart critical processes if they die unexpectedly, and require explicit confirmation before killing registered processes.

Born from a real incident: a rogue Claude Code agent spawned duplicate training processes into a running VQ-VAE job, and a manual kill of what appeared to be duplicates turned out to be legitimate DataLoader workers — crashing the training at epoch 10/15 with no checkpoint saved.

---

## Design

### Core: `procyon.py` — single-file CLI tool

```
procyon register  --name <job_name> --pid <pid> --cmd "<full command>" [--checkpoint_dir <path>]
procyon watch     # start background watchdog daemon
procyon kill      --name <job_name>  # safe kill with confirmation
procyon status    # list all registered processes and their health
procyon unregister --name <job_name>  # remove from registry (on clean exit)
```

### Layer A: Lock Files (anti-duplicate)

Each registered job writes a lock file at `<checkpoint_dir>/procyon.lock` (or `~/.procyon/locks/<name>.lock` if no checkpoint_dir). Lock file contains:

```json
{"name": "rvq_full_pca", "pid": 3203377, "cmd": "python3 scripts/train_rvq.py ...", "started": "2026-03-21T19:25:00", "checkpoint_dir": "/data/.../checkpoints/rvq_full_pca"}
```

On `register`: check if lock exists → if yes, check if PID is alive → if alive, refuse with error. If dead (stale lock), clean up and proceed.

### Layer B: Global Registry

`~/.procyon/registry.json` — master list of all active jobs. `watch` reads this to know what to monitor.

### Watchdog (`watch`)

- Runs as background daemon (`nohup procyon watch &`)
- Polls registry every 30s
- If a registered PID is dead: log the event + auto-restart using the saved `cmd` + update registry with new PID
- Writes daemon log to `~/.procyon/watchdog.log`
- Restart is skipped if `checkpoint_final.pt` exists in checkpoint_dir (clean completion, not a crash)

### Safe Kill (`kill`)

```
$ procyon kill --name rvq_full_pca
⚠  PROCYON SAFE KILL
   Name:    rvq_full_pca
   PID:     3203377
   Running: 47h 32m (since 2026-03-21 19:25)
   Status:  Epoch 7/15, last loss 0.2464
   Cmd:     python3 scripts/train_rvq.py --checkpoint_dir ...

   Type the job name to confirm kill, or Ctrl+C to abort: _
```

In non-interactive mode (e.g., called from a script/agent without a TTY): **refuse entirely** and print an error. This is the key protection against rogue agents.

---

## File Structure

```
PROCYON/
├── CLAUDE.md          # this file
├── procyon.py         # single-file CLI (all logic here)
├── tests/
│   └── test_procyon.py
└── README.md
```

Keep it simple: one file, no dependencies beyond stdlib. No pip install required — just `python3 procyon.py`.

---

## Integration with MeshLex (example)

After implementation, MeshLex training scripts add two lines:

```python
# At the top of train_rvq.py, after args are parsed:
import subprocess
subprocess.run(["python3", "/home/pthahnix/PROCYON/procyon.py", "register",
                "--name", f"rvq_{args.exp_name}",
                "--pid", str(os.getpid()),
                "--cmd", " ".join(sys.argv),
                "--checkpoint_dir", args.checkpoint_dir], check=False)

# At the very end (finally block):
subprocess.run(["python3", "/home/pthahnix/PROCYON/procyon.py", "unregister",
                "--name", f"rvq_{args.exp_name}"], check=False)
```

---

## Key Constraints

- **Python stdlib only** — no external dependencies
- **Single file** — `procyon.py` contains everything
- **Non-invasive** — integrates with existing scripts via 2-line additions, doesn't require rewriting them
- **Fail-safe** — if procyon itself crashes or isn't running, the training job is unaffected
- **Non-interactive TTY detection** — `kill` command must detect if it's called from a script (no TTY) and refuse

---

## What to Build

1. Write `procyon.py` with all 5 subcommands (register, watch, kill, status, unregister)
2. Write `tests/test_procyon.py` with unit tests for lock file logic, stale lock cleanup, TTY detection, registry CRUD
3. Write `README.md` with usage examples
4. Make `procyon.py` executable (`chmod +x`)

Start with TDD: write failing tests first, then implement.
