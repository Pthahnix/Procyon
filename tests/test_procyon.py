# tests/test_procyon.py
import subprocess, json, sys, os, tempfile, time, signal

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


class TestStatusCommand:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_status_empty(self):
        rc, out, err = run_procyon('status')
        assert rc == 0
        assert out == []

    def test_status_with_registered_process(self):
        pid = os.getpid()
        run_procyon('register', '--name', 'test_job',
                    '--pid', str(pid), '--cmd', 'echo hello')
        rc, out, err = run_procyon('status')
        assert rc == 0
        assert len(out) == 1
        assert out[0]["name"] == "test_job"
        assert out[0]["alive"] is True
        assert out[0]["protected"] is True
        assert "uptime_seconds" in out[0]

    def test_status_detects_dead_process(self):
        run_procyon('register', '--name', 'dead_job',
                    '--pid', '999999999', '--cmd', 'echo hello')
        rc, out, err = run_procyon('status')
        assert rc == 0
        assert out[0]["alive"] is False

    def test_status_pretty_is_string(self):
        pid = os.getpid()
        run_procyon('register', '--name', 'test_job',
                    '--pid', str(pid), '--cmd', 'echo hello')
        rc, out, err = run_procyon('status', '--pretty')
        assert rc == 0
        assert isinstance(out, str)
        assert "test_job" in out


class TestKillCommand:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_kill_no_tty_refused(self):
        """subprocess has no TTY — kill must refuse."""
        pid = os.getpid()
        run_procyon('register', '--name', 'test_job',
                    '--pid', str(pid), '--cmd', 'echo hello')
        rc, out, err = run_procyon('kill', '--name', 'test_job')
        assert rc != 0
        assert out["code"] == "NO_TTY"

    def test_kill_not_found(self):
        rc, out, err = run_procyon('kill', '--name', 'nonexistent')
        assert rc != 0
        assert out["code"] == "NOT_FOUND"

    def test_kill_already_dead(self):
        run_procyon('register', '--name', 'dead_job',
                    '--pid', '999999999', '--cmd', 'echo hello')
        rc, out, err = run_procyon('kill', '--name', 'dead_job')
        # NO_TTY takes precedence (check order: NOT_FOUND → NO_TTY → ALREADY_DEAD)
        assert rc != 0
        assert out["code"] == "NO_TTY"

    def test_kill_already_dead_with_mocked_tty(self):
        """Direct unit test: mock isatty to test ALREADY_DEAD code path."""
        from unittest.mock import patch
        sys.path.insert(0, os.path.dirname(PROCYON))
        from procyon import cmd_kill, ensure_dirs, load_registry, save_registry
        ensure_dirs()
        # Register a dead PID
        reg = load_registry()
        reg["processes"]["dead_job"] = {
            "pid": 999999999, "cmd": "echo hi", "checkpoint_dir": None,
            "started": "2026-03-23T00:00:00", "registered_by": "manual",
            "done_marker": "checkpoint_final.pt"
        }
        save_registry(reg)
        # Mock isatty and capture SystemExit + stdout
        import io
        with patch('sys.stdin') as mock_stdin, \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            mock_stdin.isatty.return_value = True
            args = type('Args', (), {'name': 'dead_job'})()
            try:
                cmd_kill(args)
            except SystemExit:
                pass
            output = json.loads(mock_stdout.getvalue())
            assert output["code"] == "ALREADY_DEAD"


class TestWatchCommand:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        # Kill any watchdog we spawned
        pidfile = os.path.join(self.tmpdir, "watchdog.pid")
        if os.path.exists(pidfile):
            try:
                pid = int(open(pidfile).read().strip())
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
            except (ProcessLookupError, ValueError):
                pass
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_watch_creates_pid_file(self):
        proc = subprocess.Popen(
            [sys.executable, PROCYON, 'watch', '--interval', '1'],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        time.sleep(1)
        pidfile = os.path.join(self.tmpdir, "watchdog.pid")
        assert os.path.exists(pidfile)
        # Cleanup
        pid = int(open(pidfile).read().strip())
        os.kill(pid, signal.SIGTERM)

    def test_watch_stop(self):
        proc = subprocess.Popen(
            [sys.executable, PROCYON, 'watch', '--interval', '1'],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        time.sleep(1)
        rc, out, err = run_procyon('watch', '--stop')
        assert rc == 0
        time.sleep(0.5)
        pidfile = os.path.join(self.tmpdir, "watchdog.pid")
        # PID file should be cleaned up
        if os.path.exists(pidfile):
            from procyon import pid_alive
            pid = int(open(pidfile).read().strip())
            assert not pid_alive(pid)

    def test_watch_refuses_if_already_running(self):
        proc = subprocess.Popen(
            [sys.executable, PROCYON, 'watch', '--interval', '1'],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        time.sleep(1)
        rc, out, err = run_procyon('watch')
        assert rc != 0
        assert out["code"] == "WATCHDOG_RUNNING"
        # Cleanup
        run_procyon('watch', '--stop')

    def test_watch_restarts_dead_process(self):
        """Watchdog should restart a registered process whose PID is dead."""
        from procyon import ensure_dirs, load_registry, save_registry
        ensure_dirs()
        # Register a dead PID with a command that creates a marker file
        marker = os.path.join(self.tmpdir, "restarted.txt")
        reg = load_registry()
        reg["processes"]["dead_job"] = {
            "pid": 999999999,
            "cmd": f'{sys.executable} -c "open(\\"{marker}\\",\\"w\\").write(\\"ok\\")"',
            "checkpoint_dir": None, "started": "2026-03-23T00:00:00",
            "registered_by": "manual", "done_marker": "checkpoint_final.pt"
        }
        save_registry(reg)
        # Start watchdog with short interval
        proc = subprocess.Popen(
            [sys.executable, PROCYON, 'watch', '--interval', '1'],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        time.sleep(3)  # wait for at least one watchdog cycle
        # Verify the marker file was created (process was restarted)
        assert os.path.exists(marker)
        run_procyon('watch', '--stop')

    def test_watch_skips_restart_when_done_marker_exists(self):
        """Watchdog should NOT restart if done_marker exists in checkpoint_dir."""
        from procyon import ensure_dirs, load_registry, save_registry
        ensure_dirs()
        ckpt = os.path.join(self.tmpdir, "ckpt_done")
        os.makedirs(ckpt)
        # Create the done marker
        open(os.path.join(ckpt, "checkpoint_final.pt"), "w").close()
        # Register a dead PID pointing to this checkpoint_dir
        reg = load_registry()
        reg["processes"]["done_job"] = {
            "pid": 999999999,
            "cmd": "echo should-not-run",
            "checkpoint_dir": ckpt, "started": "2026-03-23T00:00:00",
            "registered_by": "manual", "done_marker": "checkpoint_final.pt"
        }
        save_registry(reg)
        proc = subprocess.Popen(
            [sys.executable, PROCYON, 'watch', '--interval', '1'],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        time.sleep(3)
        # Process should be auto-unregistered, not restarted
        rc, out, err = run_procyon('status')
        assert out == []  # unregistered
        run_procyon('watch', '--stop')


class TestRunCommand:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_run_registers_and_unregisters(self):
        """Run a short command — should auto-register then auto-unregister."""
        marker = os.path.join(self.tmpdir, "marker.txt")
        rc = subprocess.call(
            [sys.executable, PROCYON, 'run', '--name', 'test_run',
             '--', sys.executable, '-c', f'open("{marker}","w").write("ok")'],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        assert rc == 0
        assert os.path.exists(marker)
        # Should be unregistered after child exits
        rc2, out, err = run_procyon('status')
        assert out == []  # empty, child done

    def test_run_blocks_duplicate(self):
        """If a job with same name is already registered, run should refuse."""
        pid = os.getpid()
        run_procyon('register', '--name', 'test_run',
                    '--pid', str(pid), '--cmd', 'echo hi')
        proc = subprocess.run(
            [sys.executable, PROCYON, 'run', '--name', 'test_run',
             '--', 'echo', 'hello'],
            capture_output=True, text=True,
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        assert proc.returncode != 0
        out = json.loads(proc.stdout)
        assert out["code"] == "DUPLICATE_PROCESS"

    def test_run_parent_ignores_sigterm(self):
        """Parent should not die on SIGTERM — it intercepts and drops it."""
        # Start a long-running child
        proc = subprocess.Popen(
            [sys.executable, PROCYON, 'run', '--name', 'test_sig',
             '--', sys.executable, '-c', 'import time; time.sleep(30)'],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        time.sleep(1)
        # Send SIGTERM to parent — should be intercepted
        os.kill(proc.pid, signal.SIGTERM)
        time.sleep(0.5)
        # Parent should still be alive
        assert proc.poll() is None
        # Cleanup: send SIGINT (which should be forwarded to child)
        os.kill(proc.pid, signal.SIGINT)
        proc.wait(timeout=5)
