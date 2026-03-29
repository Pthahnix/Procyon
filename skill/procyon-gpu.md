---
name: procyon-gpu
description: >
  Use when checking GPU usage on the server — who's using which GPU,
  how much VRAM, utilization, and whether processes are Procyon-registered.
---

# Procyon GPU Monitor

`procyon gpu` shows GPU process information alongside standard process info, with Procyon registration status.

## Quick Usage

```bash
# Visual dashboard with VRAM progress bars (recommended for humans)
python3 ~/Procyon/procyon.py gpu --human

# JSON output (default) — all users
python3 ~/Procyon/procyon.py gpu

# Plain table — all users
python3 ~/Procyon/procyon.py gpu --pretty

# Filter to a specific user
python3 ~/Procyon/procyon.py gpu --user pthahnix --human
```

## Output Modes

### JSON (default)

```json
{
  "gpus": [
    {
      "index": 0,
      "name": "NVIDIA GeForce RTX 3090",
      "memory_total": "24576 MiB",
      "memory_used": "8192 MiB",
      "memory_free": "16384 MiB",
      "utilization": "45 %",
      "temperature": "62 C",
      "uuid": "GPU-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    }
  ],
  "processes": [
    {
      "user": "pthahnix",
      "pid": 3459739,
      "cpu_percent": 1887.0,
      "mem_percent": 0.8,
      "cmd": "BARBARUS::NURGLINGS",
      "gpu_memory": "4096 MiB",
      "gpu_utilization": "95 %",
      "gpu_index": 1,
      "cuda_device": "cuda:1",
      "procyon_registered": true,
      "procyon_name": "nurglings-01"
    }
  ]
}
```

### Pretty (`--pretty`)

```
=== GPU Overview ===
GPU 0: NVIDIA GeForce RTX 3090  |  8192 / 24576 MiB (33%)  |  Util: 45%  |  Temp: 62°C
GPU 1: NVIDIA GeForce RTX 3090  |  12288 / 24576 MiB (50%)  |  Util: 95%  |  Temp: 78°C

=== GPU Processes ===
USER        PID    %CPU  %MEM  CMD                        GPU_MEM     GPU_UTIL  CUDA     PROCYON
dyn       2303783   254   1.4  train_2m_Base-GNN.py       4096 MiB    45 %      cuda:0   -
pthahnix  3459738  2479   0.8  BARBARUS::NURGLINGS        3072 MiB    95 %      cuda:1   nurglings-01

* GPU_UTIL is per-card, not per-process
```

### Visual Dashboard (`--human`)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ GPU 0  RTX 3090          ▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░   8192 / 24576 MiB  33%  62°C │
│ GPU 1  RTX 3090          ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░  22528 / 24576 MiB  91%  78°C │
└──────────────────────────────────────────────────────────────────────────────┘

USER        PID     %CPU  %MEM  CMD                     GPU_MEM     UTIL  CUDA    PROCYON
─────────── ─────── ───── ───── ─────────────────────── ─────────── ───── ─────── ────────────
dyn         2303783   254   1.4  train_2m_Base-GNN.py   4096 MiB     45%  cuda:0  -
pthahnix    3459738  2479   0.8  BARBARUS::NURGLINGS    3072 MiB     95%  cuda:1  nurglings-01

ⓘ UTIL is per-card · 2 processes · 1/2 registered
```

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--user USER` | all users | Filter processes to a specific user |
| `--pretty` | off (JSON) | Plain human-readable table output |
| `--human` | off (JSON) | Visual dashboard with VRAM progress bars |

## Key Details

- GPU_UTIL is per-card (NVML limitation), not per-process
- `--user` filters process rows only; GPU overview always shows all cards
- PROCYON column shows registered name if in `~/.procyon/registry.json`, `-` otherwise
- Unregistered processes have `procyon_registered: false` and `procyon_name: null` in JSON
- Requires `nvidia-smi` on PATH; exits with error if unavailable

## When to Use

- Before launching a training job — check which GPUs have free VRAM
- Monitoring who's using what on the shared server
- Verifying your processes are Procyon-registered
- Quick GPU health check (utilization, temperature)

## For Agents

Parse JSON output (default mode) programmatically. Key fields for decision-making:

- `gpus[].memory_free` — find GPUs with available VRAM
- `processes[].cuda_device` — know which CUDA devices are occupied
- `processes[].procyon_registered` — check if a process is protected
- `gpus[].utilization` — avoid overloaded cards
