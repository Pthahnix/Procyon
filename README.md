# Procyon — Process Guardian

Lightweight process protection for long-running ML workloads on shared Linux servers.

Born from a real incident: a rogue Claude Code agent spawned duplicate training processes into a running VQ-VAE job, and a manual kill of what appeared to be duplicates turned out to be legitimate DataLoader workers — crashing the training at epoch 10/15 with no checkpoint saved.

## What It Does

- **Anti-duplicate**: Prevents the same job slot from being launched twice (checks by name + lock file)
- **Kill protection**: Refuses non-interactive kill attempts entirely; requires typed confirmation in a real terminal
- **Signal interception**: The `run` wrapper silently drops SIGTERM/SIGHUP from rogue agents
- **Auto-restart** *(optional)*: Watchdog daemon restarts crashed processes automatically

## Usage

Procyon is a **plain script tool** — no daemon to start, no service to manage. Just call it directly:

```bash
python3 ~/Procyon/procyon.py <command>
```

Or add an alias to `~/.bashrc`:

```bash
alias procyon='python3 ~/Procyon/procyon.py'
```

---

## Typical Workflow

### 1. Check what's running (always do this first)

```bash
python3 ~/Procyon/procyon.py status --pretty
```

### 2. Launch a protected training job

```bash
python3 ~/Procyon/procyon.py run --name rvq_pca \
  --checkpoint_dir /data/checkpoints/rvq_pca \
  -- python3 scripts/train_rvq.py --epochs 15
```

The `run` wrapper:
- Checks for a duplicate job with the same `--name` and refuses if one is running
- Auto-registers the child PID
- Intercepts SIGTERM/SIGHUP (won't die from rogue `kill` calls)
- Auto-unregisters when the child exits cleanly

### 3. Check GPU usage

```bash
# Visual dashboard with VRAM progress bars
python3 ~/Procyon/procyon.py gpu --human

# Filter to your own processes
python3 ~/Procyon/procyon.py gpu --user $(whoami) --human

# JSON output (for scripts)
python3 ~/Procyon/procyon.py gpu
```

Shows per-GPU VRAM usage, utilization, temperature, and per-process GPU memory with Procyon registration status. `--human` gives a visual dashboard, `--pretty` gives a plain table, default is JSON.

### 4. Safe kill (interactive terminal only)

```bash
python3 ~/Procyon/procyon.py kill --name rvq_pca
```

Will display job info and require you to type the job name to confirm. **Refuses entirely if called from a script or agent (no TTY).**

---

## Commands

| Command | Description |
|---|---|
| `procyon status [--pretty]` | List all registered processes and their health |
| `procyon gpu [--user USER] [--pretty] [--human]` | Show GPU processes with VRAM, utilization, CUDA device |
| `procyon run --name NAME -- CMD` | Wrapper mode: auto-register + signal protection |
| `procyon kill --name NAME` | Safe kill with confirmation (TTY only) |
| `procyon register --name NAME --pid PID --cmd CMD` | Register an existing process (for script integration) |
| `procyon unregister --name NAME` | Remove from registry on clean exit |
| `procyon watch [--stop] [--interval N]` | Start/stop background watchdog daemon (optional) |
| `procyon issue --title T --body B` | File an issue for future iteration |

All commands output JSON by default. Add `--pretty` for human-readable output.

---

## Optional: Watchdog Daemon

The watchdog polls the registry every 30 seconds and auto-restarts any crashed process. **This is optional** — the anti-duplicate and kill-protection work without it.

```bash
# Start (runs in background, survives terminal close)
python3 ~/Procyon/procyon.py watch

# Stop
python3 ~/Procyon/procyon.py watch --stop

# Custom poll interval
python3 ~/Procyon/procyon.py watch --interval 60
```

Restart is skipped if `checkpoint_final.pt` exists in the `checkpoint_dir` (clean completion detected).

To start automatically on login, add to `~/.bashrc`:

```bash
python3 ~/Procyon/procyon.py watch 2>/dev/null || true
```

---

## Script Integration (2-line)

For training scripts that manage their own process lifecycle:

```python
# At the top of train_rvq.py, after args are parsed:
import subprocess, os, sys
subprocess.run(["python3", "/home/pthahnix/Procyon/procyon.py", "register",
                "--name", f"rvq_{args.exp_name}",
                "--pid", str(os.getpid()),
                "--cmd", " ".join(sys.argv),
                "--checkpoint_dir", args.checkpoint_dir], check=False)

# At the very end (in a finally block):
subprocess.run(["python3", "/home/pthahnix/Procyon/procyon.py", "unregister",
                "--name", f"rvq_{args.exp_name}"], check=False)
```

---

## Protection Layers

1. **Layer 1 — Soft** *(active now)*: Anti-duplicate lock files, signal interception in `run` wrapper, TTY-gated kill
2. **Layer 2 — AppArmor** *(optional, requires sudo)*: Run `bash ~/Procyon/install.sh` to install profile
3. **Layer 3 — PID Namespace** *(future)*: Process isolation via `unshare`

---

## Setup

```bash
# Clone / already on server at ~/Procyon
cd ~/Procyon

# Optional: AppArmor profile (Layer 2 protection, requires sudo)
bash install.sh

# Verify
python3 procyon.py status --pretty
```

No pip install required. Python 3.10+ stdlib only.

## Requirements

- Python 3.10+ (stdlib only)
- Linux (tested on Ubuntu 24.04, kernel 6.8)
- AppArmor optional (for Layer 2)

## License

[Apache-2.0 License](LICENSE)
