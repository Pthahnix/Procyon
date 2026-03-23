# Project Rules

## 1. Process Safety
- Username is `pthahnix`. Never interfere with any existing `pthahnix` processes (training jobs, background scripts, etc.).
- Before running any resource-intensive command, check for running processes with `ps aux | grep pthahnix` or `nvidia-smi`.

## 2. Storage
- All datasets and generated data go to `/data/` — never under `/home/`.
- Code, configs, and small outputs stay in the project repo under `/home/pthahnix/GeoEval/`.

## 3. GPU Usage
- **GPU 0: off-limits.** Do not use.
- **GPU 1 and GPU 2: available.** Set `CUDA_VISIBLE_DEVICES=1,2` when GPU is needed.
- For any task that requires GPU, notify the user first and wait for confirmation.

## 4. Network / Proxy
- If network is slow or failing, use the `mihomo` proxy already configured under the `pthahnix` user.
- The installation, config, and subscription are correct — do not modify or reinstall.
- To activate: ensure `mihomo` is running and set `HTTP_PROXY` / `HTTPS_PROXY` accordingly, or use `--proxy` flags where supported.

## 5. Version Control
- Commit and push important code, configs, results, and metrics promptly.
- Do not commit large binary files, checkpoints, or raw datasets to the repo.
- Use `.gitignore` to exclude `/data/`, `*.ckpt`, `*.pt`, `*.h5`, etc.

## 6. Large Data & Checkpoints
- For large datasets or model checkpoints, contact the user — they will prepare a Hugging Face repo.
- Do not attempt to store large files locally under `/home/` or push them to GitHub without confirmation.
