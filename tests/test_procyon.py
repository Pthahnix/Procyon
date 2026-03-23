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


class TestLockFiles:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_write_and_read_lock_with_checkpoint_dir(self):
        from procyon import write_lock, read_lock, ensure_dirs
        ensure_dirs()
        ckpt = os.path.join(self.tmpdir, "checkpoints")
        os.makedirs(ckpt)
        write_lock("test_job", 12345, "echo hi", ckpt)
        lock = read_lock("test_job", ckpt)
        assert lock["pid"] == 12345
        assert lock["name"] == "test_job"
        # Lock should be at checkpoint_dir/procyon.lock
        assert os.path.exists(os.path.join(ckpt, "procyon.lock"))

    def test_write_and_read_lock_without_checkpoint_dir(self):
        from procyon import write_lock, read_lock, ensure_dirs
        ensure_dirs()
        write_lock("test_job", 12345, "echo hi", None)
        lock = read_lock("test_job", None)
        assert lock["pid"] == 12345

    def test_remove_lock(self):
        from procyon import write_lock, read_lock, remove_lock, ensure_dirs
        ensure_dirs()
        write_lock("test_job", 12345, "echo hi", None)
        remove_lock("test_job", None)
        lock = read_lock("test_job", None)
        assert lock is None

    def test_check_stale_lock_dead_pid(self):
        from procyon import write_lock, check_stale_lock, ensure_dirs
        ensure_dirs()
        write_lock("test_job", 999999999, "echo hi", None)  # dead PID
        is_stale = check_stale_lock("test_job", None)
        assert is_stale is True

    def test_check_stale_lock_alive_pid(self):
        from procyon import write_lock, check_stale_lock, ensure_dirs
        ensure_dirs()
        write_lock("test_job", os.getpid(), "echo hi", None)  # alive PID
        is_stale = check_stale_lock("test_job", None)
        assert is_stale is False


class TestRegisterCommand:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_register_success(self):
        pid = os.getpid()
        rc, out, err = run_procyon('register', '--name', 'test_job',
                                   '--pid', str(pid), '--cmd', 'echo hello')
        assert rc == 0
        assert out["status"] == "registered"
        assert out["name"] == "test_job"

    def test_register_duplicate_alive_pid_refused(self):
        pid = os.getpid()
        run_procyon('register', '--name', 'test_job',
                    '--pid', str(pid), '--cmd', 'echo hello')
        rc, out, err = run_procyon('register', '--name', 'test_job',
                                   '--pid', str(pid), '--cmd', 'echo hello')
        assert rc != 0
        assert out["code"] == "DUPLICATE_PROCESS"

    def test_register_stale_lock_cleaned(self):
        # Register with dead PID, then register again — should succeed
        run_procyon('register', '--name', 'test_job',
                    '--pid', '999999999', '--cmd', 'echo hello')
        pid = os.getpid()
        rc, out, err = run_procyon('register', '--name', 'test_job',
                                   '--pid', str(pid), '--cmd', 'echo hello')
        assert rc == 0
        assert out["status"] == "registered"

    def test_register_with_checkpoint_dir(self):
        pid = os.getpid()
        ckpt = os.path.join(self.tmpdir, "ckpts")
        os.makedirs(ckpt)
        rc, out, err = run_procyon('register', '--name', 'test_job',
                                   '--pid', str(pid), '--cmd', 'echo hi',
                                   '--checkpoint_dir', ckpt)
        assert rc == 0
        assert os.path.exists(os.path.join(ckpt, "procyon.lock"))

    def test_register_stores_done_marker_and_registered_by(self):
        pid = os.getpid()
        run_procyon('register', '--name', 'test_job',
                    '--pid', str(pid), '--cmd', 'echo hi',
                    '--done-marker', 'custom_done.flag')
        from procyon import load_registry
        reg = load_registry()
        entry = reg["processes"]["test_job"]
        assert entry["done_marker"] == "custom_done.flag"
        assert entry["registered_by"] == "manual"


class TestUnregisterCommand:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_unregister_success(self):
        pid = os.getpid()
        run_procyon('register', '--name', 'test_job',
                    '--pid', str(pid), '--cmd', 'echo hello')
        rc, out, err = run_procyon('unregister', '--name', 'test_job')
        assert rc == 0
        assert out["status"] == "unregistered"

    def test_unregister_not_found(self):
        rc, out, err = run_procyon('unregister', '--name', 'nonexistent')
        assert rc != 0
        assert out["code"] == "NOT_FOUND"
