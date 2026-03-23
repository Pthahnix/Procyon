# tests/test_procyon.py
import subprocess, json, sys, os

PROCYON = os.path.join(os.path.dirname(__file__), '..', 'procyon.py')

def run_procyon(*args):
    """Run procyon.py, return (returncode, parsed_stdout, stderr).
    Note: inherits os.environ including PROCYON_HOME set in setup_method."""
    result = subprocess.run(
        [sys.executable, PROCYON] + list(args),
        capture_output=True, text=True,
        env=os.environ.copy()  # explicit copy for safety
    )
    try:
        parsed = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = result.stdout
    return result.returncode, parsed, result.stderr

class TestCLISkeleton:
    def test_no_args_returns_nonzero(self):
        rc, out, err = run_procyon()
        assert rc != 0

    def test_status_returns_json_array(self):
        rc, out, err = run_procyon('status')
        assert rc == 0
        assert isinstance(out, list)

    def test_status_pretty_returns_string(self):
        rc, out, err = run_procyon('status', '--pretty')
        assert rc == 0
        assert isinstance(out, str)

    def test_invalid_command_returns_nonzero(self):
        rc, out, err = run_procyon('nonexistent')
        assert rc != 0
