#!/usr/bin/env python3
"""Procyon — Process Guardian CLI for ML workloads."""

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime
from pathlib import Path

VERSION = "0.1.0"

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
    with open(_registry_path(), 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(reg, indent=2))
        # lock released when file is closed


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
    json_err("NOT_IMPLEMENTED", "register is not yet implemented")


def cmd_unregister(args):
    json_err("NOT_IMPLEMENTED", "unregister is not yet implemented")


def cmd_status(args):
    if args.pretty:
        print("")
        sys.exit(0)
    json_out([])


def cmd_kill(args):
    json_err("NOT_IMPLEMENTED", "kill is not yet implemented")


def cmd_watch(args):
    json_err("NOT_IMPLEMENTED", "watch is not yet implemented")


def cmd_run(args):
    json_err("NOT_IMPLEMENTED", "run is not yet implemented")


def cmd_issue(args):
    json_err("NOT_IMPLEMENTED", "issue is not yet implemented")


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
