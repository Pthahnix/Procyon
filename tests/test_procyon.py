# tests/test_procyon.py
import subprocess, json, sys, os, tempfile

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


class TestRegistry:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir  # override ~/.procyon

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_load_empty_registry(self):
        from procyon import load_registry, ensure_dirs
        ensure_dirs()
        reg = load_registry()
        assert reg == {"processes": {}, "version": "0.1.0"}

    def test_save_and_load_roundtrip(self):
        from procyon import load_registry, save_registry, ensure_dirs
        ensure_dirs()
        reg = load_registry()
        reg["processes"]["test_job"] = {
            "pid": 12345, "cmd": "echo hello",
            "checkpoint_dir": None, "started": "2026-03-23T00:00:00",
            "registered_by": "manual", "done_marker": "checkpoint_final.pt"
        }
        save_registry(reg)
        reg2 = load_registry()
        assert reg2["processes"]["test_job"]["pid"] == 12345

    def test_pid_alive_current_process(self):
        from procyon import pid_alive
        assert pid_alive(os.getpid()) is True

    def test_pid_alive_dead_process(self):
        from procyon import pid_alive
        assert pid_alive(999999999) is False
