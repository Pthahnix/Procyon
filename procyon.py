#!/usr/bin/env python3
"""Procyon — Process Guardian CLI for ML workloads."""

import argparse
import ctypes
import fcntl
import json
import os
import resource
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VERSION = "0.2.0"

# Path constants — check PROCYON_HOME for test isolation
def _procyon_dir():
    return Path(os.environ.get('PROCYON_HOME', str(Path.home() / '.procyon')))


def _registry_path():
    return _procyon_dir() / 'registry.json'


def _locks_dir():
    return _procyon_dir() / 'locks'


def _watchdog_log():
    return _procyon_dir() / 'watchdog.log'


def _watchdog_pid():
    return _procyon_dir() / 'watchdog.pid'


# ---------------------------------------------------------------------------
# Directory / registry helpers
# ---------------------------------------------------------------------------

def ensure_dirs():
    """Create PROCYON_DIR and LOCKS_DIR if they don't exist."""
    os.makedirs(_procyon_dir(), exist_ok=True)
    os.makedirs(_locks_dir(), exist_ok=True)


def load_registry():
    """Load the registry JSON, acquiring a shared (read) lock.

    Returns the default empty registry dict if the file doesn't exist yet.
    """
    registry_path = _registry_path()
    if not registry_path.exists():
        return {"processes": {}, "version": VERSION}
    with open(registry_path, 'r') as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        data = json.load(f)
        # lock released when file is closed
    return data


def save_registry(reg):
    """Write registry dict to disk, acquiring an exclusive (write) lock."""
    path = _registry_path()
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps(reg, indent=2).encode())
    finally:
        os.close(fd)


def pid_alive(pid):
    """Return True if *pid* refers to a running process, False otherwise."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by another user
        return True


# ---------------------------------------------------------------------------
# Lock file primitives
# ---------------------------------------------------------------------------

def lock_path(name, checkpoint_dir):
    """Return the Path where the lock file for *name* should live."""
    if checkpoint_dir:
        return Path(checkpoint_dir) / "procyon.lock"
    return _locks_dir() / f"{name}.lock"


def write_lock(name, pid, cmd, checkpoint_dir):
    """Atomically write a lock file for the given job."""
    path = lock_path(name, checkpoint_dir)
    data = {
        "name": name,
        "pid": pid,
        "cmd": cmd,
        "started": datetime.now().isoformat(),
        "checkpoint_dir": checkpoint_dir,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.rename(tmp, path)


def read_lock(name, checkpoint_dir):
    """Read and return the lock file dict, or None if it doesn't exist."""
    path = lock_path(name, checkpoint_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def remove_lock(name, checkpoint_dir):
    """Delete the lock file if it exists."""
    lock_path(name, checkpoint_dir).unlink(missing_ok=True)


def check_stale_lock(name, checkpoint_dir):
    """Return True if lock exists with a dead PID, False if alive, None if no lock."""
    lock = read_lock(name, checkpoint_dir)
    if lock is None:
        return None
    return not pid_alive(lock["pid"])



# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def json_out(data):
    """Print data as JSON and exit 0."""
    print(json.dumps(data, default=str))
    sys.exit(0)


def json_err(code, msg):
    """Print error as JSON and exit 1."""
    print(json.dumps({"status": "error", "code": code, "message": msg}))
    sys.exit(1)


def pretty_table(rows, headers):
    """Return a formatted string table from rows (list of dicts) and headers (list of str)."""
    if not rows:
        return "(no entries)"
    col_widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            col_widths[h] = max(col_widths[h], len(str(row.get(h, ''))))
    sep = '  '.join('-' * col_widths[h] for h in headers)
    header_line = '  '.join(h.ljust(col_widths[h]) for h in headers)
    lines = [header_line, sep]
    for row in rows:
        lines.append('  '.join(str(row.get(h, '')).ljust(col_widths[h]) for h in headers))
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_register(args):
    ensure_dirs()
    lock = read_lock(args.name, args.checkpoint_dir)
    if lock is not None:
        if pid_alive(lock["pid"]):
            json_err("DUPLICATE_PROCESS",
                     f"Process '{args.name}' already running (PID {lock['pid']}). "
                     "Use 'procyon kill' or 'procyon unregister' first.")
        else:
            remove_lock(args.name, args.checkpoint_dir)
    write_lock(args.name, args.pid, args.cmd, args.checkpoint_dir)
    reg = load_registry()
    reg["processes"][args.name] = {
        "pid": args.pid,
        "cmd": args.cmd,
        "checkpoint_dir": args.checkpoint_dir,
        "started": datetime.now().isoformat(),
        "registered_by": "manual",
        "done_marker": args.done_marker,
    }
    save_registry(reg)
    json_out({"status": "registered", "name": args.name, "pid": args.pid})


def cmd_unregister(args):
    ensure_dirs()
    reg = load_registry()
    if args.name not in reg["processes"]:
        json_err("NOT_FOUND", f"Process '{args.name}' not found in registry.")
    checkpoint_dir = reg["processes"][args.name].get("checkpoint_dir")
    remove_lock(args.name, checkpoint_dir)
    del reg["processes"][args.name]
    save_registry(reg)
    json_out({"status": "unregistered", "name": args.name})


def cmd_status(args):
    ensure_dirs()
    reg = load_registry()
    entries = []
    now = datetime.now()
    for name, proc in reg["processes"].items():
        alive = pid_alive(proc["pid"])
        started = proc.get("started")
        try:
            started_dt = datetime.fromisoformat(started)
            uptime_seconds = int((now - started_dt).total_seconds())
        except (TypeError, ValueError):
            uptime_seconds = 0
        entries.append({
            "name": name,
            "pid": proc["pid"],
            "cmd": proc["cmd"],
            "checkpoint_dir": proc.get("checkpoint_dir"),
            "started": started,
            "uptime_seconds": uptime_seconds,
            "alive": alive,
            "protected": True,
        })
    if getattr(args, 'pretty', False):
        if not entries:
            print("No registered processes.")
        else:
            headers = ["name", "pid", "alive", "uptime_seconds", "cmd"]
            rows = [{h: str(e[h]) for h in headers} for e in entries]
            print(pretty_table(rows, headers))
        sys.exit(0)
    else:
        json_out(entries)


def cmd_kill(args):
    ensure_dirs()
    reg = load_registry()
    # 1. NOT_FOUND check (always runs)
    if args.name not in reg["processes"]:
        json_err("NOT_FOUND", f"Process '{args.name}' not found in registry.")
    # 2. TTY check — skip when --yes is passed
    if not getattr(args, 'yes', False) and not sys.stdin.isatty():
        json_err("NO_TTY", "Kill requires an interactive terminal. Refusing non-interactive kill to protect against rogue agents.")
    proc = reg["processes"][args.name]
    pid = proc["pid"]
    # 3. ALREADY_DEAD check (always runs)
    if not pid_alive(pid):
        json_err("ALREADY_DEAD", f"Process '{args.name}' (PID {pid}) is no longer alive. Use 'procyon unregister' to clean up.")
    # 4. Compute uptime for display
    try:
        started_dt = datetime.fromisoformat(proc["started"])
        uptime_secs = int((datetime.now() - started_dt).total_seconds())
        h, m = divmod(uptime_secs // 60, 60)
        uptime_str = f"{h}h {m}m"
    except Exception:
        uptime_str = "unknown"
    # 5. Confirmation prompt — skip when --yes is passed
    if not getattr(args, 'yes', False):
        print(f"\n  PROCYON SAFE KILL")
        print(f"   Name:    {args.name}")
        print(f"   PID:     {pid}")
        print(f"   Running: {uptime_str}")
        print(f"   Cmd:     {proc['cmd']}\n")
        try:
            confirm = input(f"   Type the job name to confirm kill, or Ctrl+C to abort: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            sys.exit(0)
        if confirm != args.name:
            print(f"   Confirmation mismatch. Aborting.")
            sys.exit(0)
    # 6. Kill: SIGTERM first, then SIGKILL if needed
    # Remove from registry first
    checkpoint_dir = proc.get("checkpoint_dir")
    remove_lock(args.name, checkpoint_dir)
    del reg["processes"][args.name]
    save_registry(reg)
    os.kill(pid, signal.SIGTERM)
    for _ in range(20):  # up to 10 seconds
        time.sleep(0.5)
        if not pid_alive(pid):
            break
    else:
        os.kill(pid, signal.SIGKILL)
    json_out({"status": "killed", "name": args.name, "pid": pid})


def daemonize():
    """Double-fork daemonization."""
    if os.fork() > 0:
        sys.exit(0)  # first parent exits
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)  # second parent exits
    # Close all inherited file descriptors (3+)
    maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if maxfd == resource.RLIM_INFINITY:
        maxfd = 1024
    os.closerange(3, maxfd)
    # Redirect stdio to /dev/null
    sys.stdin = open(os.devnull, 'r')
    sys.stdout = open(os.devnull, 'w')
    sys.stderr = open(os.devnull, 'w')


def watchdog_loop(interval):
    """Main watchdog loop — run as daemon."""
    pid_file = _watchdog_pid()
    pid_file.write_text(str(os.getpid()))

    def handle_sigterm(signum, frame):
        try:
            pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    while True:
        try:
            reg = load_registry()
            for name, proc in list(reg["processes"].items()):
                if not pid_alive(proc["pid"]):
                    checkpoint_dir = proc.get("checkpoint_dir")
                    done_marker = proc.get("done_marker", "checkpoint_final.pt")
                    # Check if done marker exists (clean completion)
                    if checkpoint_dir and Path(checkpoint_dir, done_marker).exists():
                        # Auto-unregister: clean completion
                        remove_lock(name, checkpoint_dir)
                        del reg["processes"][name]
                        save_registry(reg)
                    else:
                        # Auto-restart: crashed
                        new_proc = subprocess.Popen(proc["cmd"], shell=True)
                        reg["processes"][name]["pid"] = new_proc.pid
                        reg["processes"][name]["started"] = datetime.now().isoformat()
                        save_registry(reg)
                        write_lock(name, new_proc.pid, proc["cmd"], checkpoint_dir)
        except Exception:
            pass  # watchdog must never crash
        time.sleep(interval)


def cmd_watch(args):
    ensure_dirs()
    pid_file = _watchdog_pid()

    if args.stop:
        if not pid_file.exists():
            json_err("NOT_RUNNING", "Watchdog is not running.")
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            json_out({"status": "stopped", "pid": pid})
        except (ProcessLookupError, ValueError):
            pid_file.unlink(missing_ok=True)
            json_err("NOT_RUNNING", "Watchdog process not found.")

    # Check if already running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if pid_alive(pid):
                json_err("WATCHDOG_RUNNING", f"Watchdog already running (PID {pid}).")
        except ValueError:
            pass
        pid_file.unlink(missing_ok=True)

    # Daemonize and start loop
    daemonize()
    watchdog_loop(args.interval)


def cmd_run(args):
    ensure_dirs()
    # Parse cmd_args — strip leading '--' if present
    cmd_args = list(args.cmd_args)
    if cmd_args and cmd_args[0] == '--':
        cmd_args = cmd_args[1:]
    if not cmd_args:
        json_err("NO_CMD", "No command specified. Usage: procyon run --name NAME -- COMMAND [ARGS...]")

    # Anti-duplicate check (same as register)
    existing_lock = read_lock(args.name, args.checkpoint_dir)
    if existing_lock:
        if pid_alive(existing_lock["pid"]):
            json_err("DUPLICATE_PROCESS", f"Process '{args.name}' already running (PID {existing_lock['pid']}).")
        else:
            remove_lock(args.name, args.checkpoint_dir)

    # Fork: child execvp, parent registers + watches
    child_pid = os.fork()

    if child_pid == 0:
        # CHILD: try to set process name, then execvp
        try:
            libc = ctypes.CDLL("libc.so.6", use_errno=True)
            name_bytes = f"procyon:{args.name}".encode()[:15]
            libc.prctl(15, name_bytes, 0, 0, 0)  # PR_SET_NAME = 15
        except Exception:
            pass
        try:
            os.execvp(cmd_args[0], cmd_args)
        except Exception as e:
            print(json.dumps({"status": "error", "code": "EXEC_FAILED", "message": str(e)}))
            os._exit(1)

    # PARENT: register child, intercept signals, wait
    # Register in registry
    write_lock(args.name, child_pid, " ".join(cmd_args), args.checkpoint_dir)
    reg = load_registry()
    reg["processes"][args.name] = {
        "pid": child_pid,
        "cmd": " ".join(cmd_args),
        "checkpoint_dir": args.checkpoint_dir,
        "started": datetime.now().isoformat(),
        "registered_by": "run",
        "done_marker": args.done_marker,
    }
    save_registry(reg)
    print(json.dumps({"status": "started", "name": args.name, "pid": child_pid, "cmd": " ".join(cmd_args)}, default=str))
    sys.stdout.flush()

    # Signal handlers: SIGTERM/SIGHUP intercepted (no-op), SIGINT forwarded to child
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    def forward_sigint(signum, frame):
        try:
            os.kill(child_pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    signal.signal(signal.SIGINT, forward_sigint)

    # Wait for child to exit
    try:
        _, status = os.waitpid(child_pid, 0)
        exit_code = os.waitstatus_to_exitcode(status)
    except ChildProcessError:
        exit_code = 0

    # Unregister (clean up)
    try:
        remove_lock(args.name, args.checkpoint_dir)
        reg = load_registry()
        if args.name in reg["processes"]:
            del reg["processes"][args.name]
            save_registry(reg)
    except Exception:
        pass

    sys.exit(exit_code)


def cmd_issue(args):
    """File an issue for future iteration."""
    import re

    # Determine issues directory
    issues_dir_env = os.environ.get('PROCYON_ISSUES_DIR')
    if issues_dir_env:
        issues_dir = Path(issues_dir_env)
    else:
        # Auto-detect project root (walk up from __file__ looking for CLAUDE.md)
        here = Path(__file__).parent.resolve()
        project_root = here
        for parent in [here] + list(here.parents):
            if (parent / 'CLAUDE.md').exists():
                project_root = parent
                break
        issues_dir = project_root / 'issues'

    issues_dir.mkdir(parents=True, exist_ok=True)

    # Count existing issue .md files → next number (exclude TODO.md)
    existing = sorted([f for f in issues_dir.iterdir()
                       if f.suffix == '.md' and f.name != 'TODO.md'])
    next_num = len(existing) + 1

    # Slugify title
    slug = re.sub(r'[^a-z0-9]+', '-', args.title.lower()).strip('-')[:50]

    # Filename: YYYY-MM-DD_NNN_slug.md
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"{date_str}_{next_num:03d}_{slug}.md"
    filepath = issues_dir / filename

    # Write frontmatter + body
    content = f"""---
title: {args.title}
priority: {args.priority}
tag: {args.tag}
date: {datetime.now().isoformat()}
author: claude-code
status: open
---

{args.body}
"""
    filepath.write_text(content)

    # Auto-append entry to TODO.md
    todo_path = issues_dir / 'TODO.md'
    todo_entry = f"- [ ] [#{next_num:03d} {args.title}]({filename})\n"
    if todo_path.exists():
        with open(todo_path, 'a') as f:
            f.write(todo_entry)
    else:
        # Create TODO.md with header + first entry
        todo_header = (
            "# Procyon — Open Issues Tracker\n\n"
            "> Auto-maintained by `procyon issue`. Each new issue is appended "
            "here as an unchecked item.\n"
            "> Resolved issues are checked off (`- [x]`) during the iterate "
            "workflow.\n\n"
        )
        with open(todo_path, 'w') as f:
            f.write(todo_header + todo_entry)

    # Return relative path if possible
    try:
        rel_path = str(filepath.relative_to(Path.cwd()))
    except ValueError:
        rel_path = str(filepath)

    json_out({"status": "created", "path": rel_path})


# ---------------------------------------------------------------------------
# GPU monitoring helpers
# ---------------------------------------------------------------------------

def query_gpu_info():
    """Query nvidia-smi for GPU hardware info.

    Returns:
        (gpus, uuid_map) where gpus is a list of dicts and
        uuid_map is {uuid: {"index": int, "utilization": str}}.
    """
    result = subprocess.run(
        ['nvidia-smi',
         '--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,uuid',
         '--format=csv,noheader'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None, None

    gpus = []
    uuid_map = {}
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 8:
            continue
        idx = int(parts[0])
        util_str = parts[5]
        uuid = parts[7]
        gpu = {
            "index": idx,
            "name": parts[1],
            "memory_total": parts[2],
            "memory_used": parts[3],
            "memory_free": parts[4],
            "utilization": util_str,
            "temperature": f"{parts[6]} C",
            "uuid": uuid,
        }
        gpus.append(gpu)
        uuid_map[uuid] = {"index": idx, "utilization": util_str}
    return gpus, uuid_map


def query_gpu_processes(uuid_map):
    """Query nvidia-smi for GPU compute processes.

    Args:
        uuid_map: dict from query_gpu_info(), maps uuid to {index, utilization}.

    Returns:
        List of process dicts with pid, gpu_memory, gpu_index, gpu_utilization, cuda_device.
    """
    result = subprocess.run(
        ['nvidia-smi',
         '--query-compute-apps=pid,gpu_uuid,used_gpu_memory',
         '--format=csv,noheader'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return []

    procs = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 3:
            continue
        pid = int(parts[0])
        uuid = parts[1]
        gpu_mem = parts[2]
        gpu_info = uuid_map.get(uuid, {"index": -1, "utilization": "N/A"})
        procs.append({
            "pid": pid,
            "gpu_memory": gpu_mem,
            "gpu_index": gpu_info["index"],
            "gpu_utilization": gpu_info["utilization"],
            "cuda_device": f"cuda:{gpu_info['index']}",
        })
    return procs


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog='procyon',
        description='Procyon — Process Guardian for ML workloads',
    )
    parser.add_argument('--version', action='version', version=f'procyon {VERSION}')

    subparsers = parser.add_subparsers(dest='command')

    # register
    p_register = subparsers.add_parser('register', help='Register a running process')
    p_register.add_argument('--name', required=True, help='Job name')
    p_register.add_argument('--pid', required=True, type=int, help='Process ID')
    p_register.add_argument('--cmd', required=True, help='Full command string')
    p_register.add_argument('--checkpoint_dir', default=None, help='Checkpoint directory')
    p_register.add_argument('--done-marker', default='checkpoint_final.pt',
                            help='File whose presence indicates clean completion')

    # unregister
    p_unregister = subparsers.add_parser('unregister', help='Unregister a process')
    p_unregister.add_argument('--name', required=True, help='Job name')

    # status
    p_status = subparsers.add_parser('status', help='List registered processes')
    p_status.add_argument('--pretty', action='store_true', help='Human-readable output')

    # kill
    p_kill = subparsers.add_parser('kill', help='Safely kill a registered process')
    p_kill.add_argument('--name', required=True, help='Job name')
    p_kill.add_argument('--yes', action='store_true',
                        help='Skip TTY check and confirmation (for non-interactive use)')

    # watch
    p_watch = subparsers.add_parser('watch', help='Start/stop the watchdog daemon')
    p_watch.add_argument('--stop', action='store_true', help='Stop the watchdog daemon')
    p_watch.add_argument('--interval', type=int, default=30, help='Poll interval in seconds')

    # run
    p_run = subparsers.add_parser('run', help='Run a command under procyon supervision')
    p_run.add_argument('--name', required=True, help='Job name')
    p_run.add_argument('--checkpoint_dir', default=None, help='Checkpoint directory')
    p_run.add_argument('--done-marker', default='checkpoint_final.pt',
                       help='File whose presence indicates clean completion')
    p_run.add_argument('cmd_args', nargs=argparse.REMAINDER, help='Command to run')

    # issue
    p_issue = subparsers.add_parser('issue', help='File an issue report')
    p_issue.add_argument('--title', required=True, help='Issue title')
    p_issue.add_argument('--body', required=True, help='Issue body')
    p_issue.add_argument('--priority', default='normal', help='Priority level')
    p_issue.add_argument('--tag', default='bug', help='Issue tag')

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

DISPATCH = {
    'register': cmd_register,
    'unregister': cmd_unregister,
    'status': cmd_status,
    'kill': cmd_kill,
    'watch': cmd_watch,
    'run': cmd_run,
    'issue': cmd_issue,
}


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help(sys.stderr)
        sys.exit(1)

    handler = DISPATCH.get(args.command)
    if handler is None:
        json_err("UNKNOWN_COMMAND", f"Unknown command: {args.command}")

    handler(args)


if __name__ == '__main__':
    main()
