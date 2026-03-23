#!/usr/bin/env python3
"""Procyon — Process Guardian CLI for ML workloads."""

import argparse
import json
import os
import sys
from pathlib import Path

VERSION = "0.1.0"

# Path constants — check PROCYON_HOME for test isolation
PROCYON_DIR = Path(os.environ.get('PROCYON_HOME', str(Path.home() / '.procyon')))
REGISTRY_PATH = PROCYON_DIR / 'registry.json'
LOCKS_DIR = PROCYON_DIR / 'locks'
WATCHDOG_LOG = PROCYON_DIR / 'watchdog.log'
WATCHDOG_PID = PROCYON_DIR / 'watchdog.pid'


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
