# Procyon — Process Guardian

## What is Procyon?

Procyon is a lightweight process protection tool for long-running ML workloads on shared servers. It solves two problems:

1. **Anti-duplicate**: Prevent a process from being launched twice into the same job slot (e.g., two training runs writing to the same checkpoint dir).
2. **Kill protection**: Auto-restart critical processes if they die unexpectedly, and require explicit confirmation before killing registered processes.

Born from a real incident: a rogue Claude Code agent spawned duplicate training processes into a running VQ-VAE job, and a manual kill of what appeared to be duplicates turned out to be legitimate DataLoader workers — crashing the training at epoch 10/15 with no checkpoint saved.

---

## Status: v0.1.0 — Deployed and Active

- Location: `/home/pthahnix/Procyon/procyon.py`
- Registry: `~/.procyon/registry.json`
- 42 tests passing
- Layer 1 (soft protection) active; Layer 2 (AppArmor) requires interactive `bash install.sh`

---

## How to Use (for Claude Code agents)

**IMPORTANT: You have a skill file for this.** Before managing any training process, invoke:
```
skill: procyon-usage
```

Key rules:
1. **ALWAYS** run `procyon status` before launching any training job
2. **NEVER** use `kill`, `pkill`, or `killall` on training processes
3. **ALWAYS** use `procyon run` wrapper mode for new jobs
4. **NEVER** call `procyon kill` — it will reject you (no TTY)
5. Use `procyon issue` to report bugs — do NOT modify `procyon.py` directly

---

## Usage Model

Procyon is a **plain CLI tool** — no daemon required for basic use. Commands are instant:

```bash
# Check running jobs
python3 ~/Procyon/procyon.py status --pretty

# Launch protected training (recommended)
python3 ~/Procyon/procyon.py run --name rvq_pca \
  --checkpoint_dir /data/checkpoints/rvq_pca \
  -- python3 scripts/train_rvq.py --epochs 15

# File an issue
python3 ~/Procyon/procyon.py issue --title "title" --body "details"
```

The watchdog (`procyon watch`) is optional — only needed for auto-restart on crash.

---

## Design

### Core: `procyon.py` — single-file CLI tool

All 7 subcommands:
```
procyon register   --name <name> --pid <pid> --cmd "<cmd>" [--checkpoint_dir <path>]
procyon unregister --name <name>
procyon status     [--pretty]
procyon kill       --name <name>          # TTY only, refuses agents
procyon watch      [--stop] [--interval N]
procyon run        --name <name> -- <cmd> [args...]
procyon issue      --title <t> --body <b> [--priority <p>] [--tag <t>]
```

### Layer A: Lock Files (anti-duplicate)

Each registered job writes a lock file at `<checkpoint_dir>/procyon.lock` (or `~/.procyon/locks/<name>.lock`). On `register`/`run`: check if lock exists → if PID alive, refuse. If dead (stale), clean up and proceed.

### Layer B: Global Registry

`~/.procyon/registry.json` — master list. Uses `fcntl.flock` for concurrency. `watch` reads this to know what to monitor.

### Watchdog (`watch`)

- Double-fork daemon, survives terminal close
- Polls registry every 30s (configurable via `--interval`)
- Dead PID → auto-restart via saved `cmd`, OR auto-unregister if `done_marker` exists in checkpoint_dir (clean completion)
- PID file at `~/.procyon/watchdog.pid`

### Safe Kill (`kill`)

Checks TTY via `sys.stdin.isatty()`. If no TTY (script/agent context): **refuses entirely with NO_TTY error**. If TTY: displays job info and requires typing the job name to confirm.

---

## File Structure

```
Procyon/
├── CLAUDE.md              # this file
├── README.md              # user-facing docs
├── procyon.py             # single-file CLI (all logic here)
├── install.sh             # one-time AppArmor + directory setup
├── tests/
│   └── test_procyon.py    # 42 tests
├── skill/
│   ├── procyon-usage.md   # CC daily usage SOP
│   └── procyon-iterate.md # CC iteration/upgrade SOP
├── issues/                # filed issues (procyon issue command)
└── VERSION                # current version
```

---

## Integration with Training Scripts (2-line)

```python
# At the top of train_rvq.py, after args are parsed:
import subprocess, os, sys
subprocess.run(["python3", "/home/pthahnix/Procyon/procyon.py", "register",
                "--name", f"rvq_{args.exp_name}",
                "--pid", str(os.getpid()),
                "--cmd", " ".join(sys.argv),
                "--checkpoint_dir", args.checkpoint_dir], check=False)

# At the very end (finally block):
subprocess.run(["python3", "/home/pthahnix/Procyon/procyon.py", "unregister",
                "--name", f"rvq_{args.exp_name}"], check=False)
```

Preferred alternative: use `procyon run` wrapper instead of modifying scripts.

---

## Key Constraints

- **Python stdlib only** — no external dependencies
- **Single file** — `procyon.py` contains everything
- **Non-invasive** — integrates via 2-line additions, or use `run` wrapper
- **Fail-safe** — if procyon crashes or isn't running, training job is unaffected
- **Non-interactive TTY detection** — `kill` refuses if called from a script/agent

---

## Iteration

To improve Procyon, invoke `skill: procyon-iterate`. This will:
1. Read open issues in `issues/`
2. Plan changes on a feature branch
3. Run tests, create PR, wait for human approval before merging

Do **not** modify `procyon.py` outside this workflow.
