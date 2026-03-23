# Procyon — Process Guardian

Lightweight process protection for long-running ML workloads on shared Linux servers.

## What It Does

- **Anti-duplicate**: Prevents a process from being launched twice into the same job slot
- **Kill protection**: Requires explicit confirmation before killing registered processes; refuses non-interactive (agent/script) kill attempts entirely
- **Auto-restart**: Watchdog daemon restarts crashed processes automatically
- **AppArmor integration**: Blocks other users from sending signals to protected processes

## Quick Start

```bash
# One-time setup (requires sudo)
bash install.sh

# Start watchdog daemon
python3 procyon.py watch

# Launch a protected training job (wrapper mode, recommended)
python3 procyon.py run --name rvq_pca \
  --checkpoint_dir /data/checkpoints/rvq_pca \
  -- python3 train_rvq.py --epochs 15

# Check all registered processes
python3 procyon.py status --pretty

# Safe kill (interactive terminal only)
python3 procyon.py kill --name rvq_pca
```

## Commands

| Command | Description |
|---|---|
| `procyon register` | Register a process (used by scripts) |
| `procyon unregister` | Remove a process from registry |
| `procyon status` | List all registered processes |
| `procyon kill` | Safe kill with confirmation (TTY only) |
| `procyon watch` | Start watchdog daemon |
| `procyon run` | Wrapper mode: auto-register + signal protection |
| `procyon issue` | File an issue for future iteration |

All commands output JSON by default. Add `--pretty` for human-readable output.

## Protection Layers

1. **Layer 1 — Soft**: Signal interception (SIGTERM/SIGHUP blocked by parent wrapper), process naming via `prctl`, TTY-gated kill
2. **Layer 2 — AppArmor**: Mandatory Access Control restricts who can send signals to protected processes
3. **Layer 3 — PID Namespace** *(future)*: Process isolation via `unshare`

## Requirements

- Python 3.10+ (stdlib only, no pip install needed)
- Linux (tested on Ubuntu 24.04, kernel 6.8)
- AppArmor (for Layer 2 protection)

## License

[Apache-2.0 License](LICENSE)
