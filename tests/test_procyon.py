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

    def test_save_registry_uses_fd_based_locking(self):
        """Verify save_registry uses os.open (not open('w')) to avoid TOCTOU."""
        import inspect
        from procyon import save_registry, load_registry, ensure_dirs
        # Source inspection: must use os.open, not open('w')
        source = inspect.getsource(save_registry)
        assert "os.open" in source, "save_registry should use os.open, not open('w')"
        assert "ftruncate" in source, "save_registry should use ftruncate after locking"
        # Functional roundtrip test
        ensure_dirs()
        reg = {"processes": {"job_a": {"pid": 111, "cmd": "echo a"}}, "version": "0.1.0"}
        save_registry(reg)
        reg2 = {"processes": {"job_b": {"pid": 222, "cmd": "echo b"}}, "version": "0.1.0"}
        save_registry(reg2)
        loaded = load_registry()
        assert "job_b" in loaded["processes"]
        assert "job_a" not in loaded["processes"]
        assert loaded["processes"]["job_b"]["pid"] == 222


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


class TestIssueCommand:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir
        self.issues_dir = os.path.join(self.tmpdir, "issues")
        os.makedirs(self.issues_dir)
        os.environ['PROCYON_ISSUES_DIR'] = self.issues_dir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)
        os.environ.pop('PROCYON_ISSUES_DIR', None)

    def test_issue_creates_file(self):
        rc, out, err = run_procyon('issue', '--title', 'Test bug',
                                   '--body', 'Something is broken')
        assert rc == 0
        assert out["status"] == "created"
        assert "path" in out
        # Verify file exists and has frontmatter
        files = os.listdir(self.issues_dir)
        md_files = [f for f in files if f.endswith('.md') and f != 'TODO.md']
        assert len(md_files) == 1
        content = open(os.path.join(self.issues_dir, md_files[0])).read()
        assert "title: Test bug" in content
        assert "status: open" in content
        assert "Something is broken" in content
        # Verify TODO.md was auto-created with entry
        todo_path = os.path.join(self.issues_dir, 'TODO.md')
        assert os.path.exists(todo_path)
        todo_content = open(todo_path).read()
        assert "- [ ]" in todo_content
        assert "Test bug" in todo_content

    def test_issue_sequential_numbering(self):
        run_procyon('issue', '--title', 'First', '--body', 'body1')
        run_procyon('issue', '--title', 'Second', '--body', 'body2')
        files = sorted(os.listdir(self.issues_dir))
        md_files = [f for f in files if f.endswith('.md') and f != 'TODO.md']
        assert len(md_files) == 2
        assert '_001_' in md_files[0]
        assert '_002_' in md_files[1]
        # Verify TODO.md has both entries
        todo_content = open(os.path.join(self.issues_dir, 'TODO.md')).read()
        assert "#001" in todo_content
        assert "#002" in todo_content

    def test_issue_with_priority_and_tag(self):
        rc, out, err = run_procyon('issue', '--title', 'Urgent',
                                   '--body', 'Fix now',
                                   '--priority', 'high', '--tag', 'feature')
        assert rc == 0
        files = os.listdir(self.issues_dir)
        md_files = [f for f in files if f.endswith('.md') and f != 'TODO.md']
        content = open(os.path.join(self.issues_dir, md_files[0])).read()
        assert "priority: high" in content
        assert "tag: feature" in content


class TestE2E:
    """Full workflow: run → status → verify → child exits → verify unregistered."""
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir
        os.environ['PROCYON_ISSUES_DIR'] = os.path.join(self.tmpdir, 'issues')
        os.makedirs(os.environ['PROCYON_ISSUES_DIR'])

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)
        os.environ.pop('PROCYON_ISSUES_DIR', None)

    def test_full_workflow_run_status_exit(self):
        # Start a short-lived child via procyon run
        marker = os.path.join(self.tmpdir, "done.txt")
        script = f'import time; open("{marker}","w").write("ok"); time.sleep(2)'
        proc = subprocess.Popen(
            [sys.executable, PROCYON, 'run', '--name', 'e2e_test',
             '--', sys.executable, '-c', script],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        time.sleep(1)
        # While running: status should show it
        rc, out, err = run_procyon('status')
        assert len(out) == 1
        assert out[0]["name"] == "e2e_test"
        assert out[0]["alive"] is True
        # Wait for child to finish
        proc.wait(timeout=10)
        # After exit: status should be empty
        rc, out, err = run_procyon('status')
        assert out == []
        # Marker file should exist
        assert os.path.exists(marker)

    def test_duplicate_prevention_e2e(self):
        # Start a long-lived child
        proc = subprocess.Popen(
            [sys.executable, PROCYON, 'run', '--name', 'dup_test',
             '--', sys.executable, '-c', 'import time; time.sleep(30)'],
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        time.sleep(1)
        # Try to register same name — should fail
        rc, out, err = run_procyon('register', '--name', 'dup_test',
                                   '--pid', str(os.getpid()), '--cmd', 'echo hi')
        assert rc != 0
        assert out["code"] == "DUPLICATE_PROCESS"
        # Try to run same name — should fail
        proc2 = subprocess.run(
            [sys.executable, PROCYON, 'run', '--name', 'dup_test',
             '--', 'echo', 'hello'],
            capture_output=True, text=True,
            env={**os.environ, 'PROCYON_HOME': self.tmpdir}
        )
        assert proc2.returncode != 0
        # Cleanup
        os.kill(proc.pid, signal.SIGINT)
        proc.wait(timeout=5)

    def test_issue_creation_e2e(self):
        rc, out, err = run_procyon('issue', '--title', 'E2E test issue',
                                   '--body', 'Testing issue creation',
                                   '--priority', 'low', '--tag', 'improvement')
        assert rc == 0
        assert out["status"] == "created"


class TestWatchdogLockUpdate:
    """Issue #002: watchdog must update lock file PID after auto-restart."""
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

    def test_watchdog_restart_updates_lock_file(self):
        """After auto-restart, lock file PID should match the new process PID."""
        from procyon import ensure_dirs, load_registry, save_registry, read_lock
        ensure_dirs()
        # Register a dead PID with a command that sleeps (so it stays alive after restart)
        reg = load_registry()
        reg["processes"]["lock_test"] = {
            "pid": 999999999,
            "cmd": f'{sys.executable} -c "import time; time.sleep(60)"',
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
        # Read the registry to get the new PID
        reg2 = load_registry()
        assert "lock_test" in reg2["processes"]
        new_pid = reg2["processes"]["lock_test"]["pid"]
        assert new_pid != 999999999  # should be different (restarted)
        # Read the lock file — its PID should match the registry PID
        lock = read_lock("lock_test", None)
        assert lock is not None, "Lock file should exist after restart"
        assert lock["pid"] == new_pid, f"Lock file PID {lock['pid']} != registry PID {new_pid}"
        # Cleanup: kill the restarted process and watchdog
        try:
            os.kill(new_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        run_procyon('watch', '--stop')


class TestDaemonizeFdCleanup:
    """Issue #004: daemonize should close inherited fds 3+."""

    def test_closerange_closes_inherited_fds(self):
        """Verify os.closerange closes fds 3+ (tests the pattern, not the fork).

        IMPORTANT: This test runs os.closerange in a subprocess to avoid
        closing pytest's own file descriptors."""
        import resource
        # Run in subprocess to protect pytest's fds
        script = '''
import os, resource, errno
r, w = os.pipe()
assert r >= 3
maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
if maxfd == resource.RLIM_INFINITY:
    maxfd = 1024
os.closerange(3, maxfd)
try:
    os.fstat(r)
    print("FAIL: fd should be closed")
    exit(1)
except OSError as e:
    if e.errno == errno.EBADF:
        print("OK")
    else:
        print(f"FAIL: unexpected error {e}")
        exit(1)
'''
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
        assert result.returncode == 0, f"subprocess failed: {result.stderr}"
        assert "OK" in result.stdout

    def test_daemonize_contains_closerange(self):
        """Verify daemonize() source contains os.closerange call."""
        import inspect
        from procyon import daemonize
        source = inspect.getsource(daemonize)
        assert "os.closerange" in source, "daemonize() should call os.closerange"
        assert "resource.getrlimit" in source or "RLIMIT_NOFILE" in source, \
            "daemonize() should use resource.getrlimit for max fd"


class TestKillYesFlag:
    """Issue #005: --yes flag should bypass TTY check and confirmation."""
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_kill_yes_bypasses_tty_check(self):
        """With --yes, kill should work even without a TTY."""
        # Start a background process to kill
        proc = subprocess.Popen(
            [sys.executable, '-c', 'import time; time.sleep(60)']
        )
        try:
            pid = proc.pid
            # Register it
            run_procyon('register', '--name', 'yes_test',
                        '--pid', str(pid), '--cmd', 'sleep 60')
            # Kill with --yes (no TTY in subprocess)
            rc, out, err = run_procyon('kill', '--name', 'yes_test', '--yes')
            assert rc == 0
            assert out["status"] == "killed"
            assert out["name"] == "yes_test"
        finally:
            try:
                proc.kill()
                proc.wait()
            except Exception:
                pass

    def test_kill_without_yes_still_requires_tty(self):
        """Without --yes, kill should still refuse in non-TTY context."""
        pid = os.getpid()
        run_procyon('register', '--name', 'tty_test',
                    '--pid', str(pid), '--cmd', 'echo hi')
        rc, out, err = run_procyon('kill', '--name', 'tty_test')
        assert rc != 0
        assert out["code"] == "NO_TTY"

    def test_kill_yes_not_found(self):
        """--yes should not bypass NOT_FOUND check."""
        rc, out, err = run_procyon('kill', '--name', 'nonexistent', '--yes')
        assert rc != 0
        assert out["code"] == "NOT_FOUND"

    def test_kill_yes_already_dead(self):
        """--yes should not bypass ALREADY_DEAD check."""
        run_procyon('register', '--name', 'dead_yes',
                    '--pid', '999999999', '--cmd', 'echo hi')
        rc, out, err = run_procyon('kill', '--name', 'dead_yes', '--yes')
        assert rc != 0
        assert out["code"] == "ALREADY_DEAD"


class TestGpuCommand:
    """Tests for procyon gpu subcommand."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.environ['PROCYON_HOME'] = self.tmpdir

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop('PROCYON_HOME', None)

    def test_query_gpu_info_parses_nvidia_smi(self):
        from unittest.mock import patch, MagicMock
        sys.path.insert(0, os.path.dirname(PROCYON))
        from procyon import query_gpu_info

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "0, NVIDIA GeForce RTX 3090, 24576 MiB, 8192 MiB, 16384 MiB, 45 %, 62, GPU-uuid-0000\n"
            "1, NVIDIA GeForce RTX 3090, 24576 MiB, 12288 MiB, 12288 MiB, 95 %, 78, GPU-uuid-1111\n"
        )
        with patch('subprocess.run', return_value=mock_result):
            gpus, uuid_map = query_gpu_info()

        assert len(gpus) == 2
        assert gpus[0]["index"] == 0
        assert gpus[0]["name"] == "NVIDIA GeForce RTX 3090"
        assert gpus[0]["memory_total"] == "24576 MiB"
        assert gpus[0]["memory_used"] == "8192 MiB"
        assert gpus[0]["memory_free"] == "16384 MiB"
        assert gpus[0]["utilization"] == "45 %"
        assert gpus[0]["temperature"] == "62 C"
        assert gpus[0]["uuid"] == "GPU-uuid-0000"
        assert uuid_map["GPU-uuid-0000"] == {"index": 0, "utilization": "45 %"}
        assert uuid_map["GPU-uuid-1111"] == {"index": 1, "utilization": "95 %"}

    def test_query_gpu_processes_parses_compute_apps(self):
        from unittest.mock import patch, MagicMock
        from procyon import query_gpu_processes

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "3459739, GPU-uuid-1111, 4096 MiB\n"
            "3462049, GPU-uuid-1111, 2048 MiB\n"
            "2303783, GPU-uuid-0000, 4096 MiB\n"
        )
        uuid_map = {
            "GPU-uuid-0000": {"index": 0, "utilization": "45 %"},
            "GPU-uuid-1111": {"index": 1, "utilization": "95 %"},
        }
        with patch('subprocess.run', return_value=mock_result):
            procs = query_gpu_processes(uuid_map)

        assert len(procs) == 3
        assert procs[0]["pid"] == 3459739
        assert procs[0]["gpu_memory"] == "4096 MiB"
        assert procs[0]["gpu_index"] == 1
        assert procs[0]["gpu_utilization"] == "95 %"
        assert procs[0]["cuda_device"] == "cuda:1"
        assert procs[2]["gpu_index"] == 0
        assert procs[2]["cuda_device"] == "cuda:0"

    def test_enrich_with_ps_merges_process_info(self):
        from unittest.mock import patch, MagicMock
        from procyon import enrich_with_ps

        procs = [
            {"pid": 1001, "gpu_memory": "4096 MiB", "gpu_index": 0,
             "gpu_utilization": "45 %", "cuda_device": "cuda:0"},
            {"pid": 1002, "gpu_memory": "2048 MiB", "gpu_index": 1,
             "gpu_utilization": "95 %", "cuda_device": "cuda:1"},
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "pthahnix  1001  254.0  1.4 train.py\n"
            "dyn       1002  460.0  0.7 main.py\n"
        )
        with patch('subprocess.run', return_value=mock_result):
            enriched = enrich_with_ps(procs)

        assert len(enriched) == 2
        assert enriched[0]["user"] == "pthahnix"
        assert enriched[0]["cpu_percent"] == 254.0
        assert enriched[0]["mem_percent"] == 1.4
        assert enriched[0]["cmd"] == "train.py"
        assert enriched[1]["user"] == "dyn"

    def test_enrich_with_ps_skips_vanished_pid(self):
        from unittest.mock import patch, MagicMock
        from procyon import enrich_with_ps

        procs = [
            {"pid": 1001, "gpu_memory": "4096 MiB", "gpu_index": 0,
             "gpu_utilization": "45 %", "cuda_device": "cuda:0"},
            {"pid": 9999, "gpu_memory": "2048 MiB", "gpu_index": 1,
             "gpu_utilization": "95 %", "cuda_device": "cuda:1"},
        ]
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "pthahnix  1001  254.0  1.4 train.py\n"
        with patch('subprocess.run', return_value=mock_result):
            enriched = enrich_with_ps(procs)

        assert len(enriched) == 1
        assert enriched[0]["pid"] == 1001

    def test_enrich_with_registry_marks_registered(self):
        from procyon import enrich_with_registry, ensure_dirs, save_registry

        ensure_dirs()
        reg = {
            "processes": {
                "nurglings-01": {"pid": 1001, "cmd": "train.py",
                                 "checkpoint_dir": None, "started": "2026-03-29T00:00:00",
                                 "registered_by": "run", "done_marker": "checkpoint_final.pt"},
            },
            "version": "0.2.0"
        }
        save_registry(reg)

        procs = [
            {"pid": 1001, "user": "pthahnix", "cmd": "train.py",
             "gpu_memory": "4096 MiB", "gpu_index": 0,
             "gpu_utilization": "45 %", "cuda_device": "cuda:0",
             "cpu_percent": 254.0, "mem_percent": 1.4},
            {"pid": 2002, "user": "dyn", "cmd": "main.py",
             "gpu_memory": "2048 MiB", "gpu_index": 1,
             "gpu_utilization": "95 %", "cuda_device": "cuda:1",
             "cpu_percent": 460.0, "mem_percent": 0.7},
        ]
        enriched = enrich_with_registry(procs)

        assert enriched[0]["procyon_registered"] is True
        assert enriched[0]["procyon_name"] == "nurglings-01"
        assert enriched[1]["procyon_registered"] is False
        assert enriched[1]["procyon_name"] is None

    def test_enrich_with_registry_missing_file(self):
        from procyon import enrich_with_registry, ensure_dirs

        ensure_dirs()
        # No registry file saved — should still work
        procs = [
            {"pid": 1001, "user": "pthahnix", "cmd": "train.py",
             "gpu_memory": "4096 MiB", "gpu_index": 0,
             "gpu_utilization": "45 %", "cuda_device": "cuda:0",
             "cpu_percent": 254.0, "mem_percent": 1.4},
        ]
        enriched = enrich_with_registry(procs)

        assert enriched[0]["procyon_registered"] is False
        assert enriched[0]["procyon_name"] is None

    def test_format_gpu_pretty_output(self):
        from procyon import format_gpu_pretty

        gpus = [
            {"index": 0, "name": "NVIDIA GeForce RTX 3090",
             "memory_total": "24576 MiB", "memory_used": "8192 MiB",
             "memory_free": "16384 MiB", "utilization": "45 %",
             "temperature": "62 C", "uuid": "GPU-uuid-0000"},
        ]
        procs = [
            {"pid": 1001, "user": "pthahnix", "cpu_percent": 254.0,
             "mem_percent": 1.4, "cmd": "train.py", "gpu_memory": "4096 MiB",
             "gpu_utilization": "45 %", "gpu_index": 0, "cuda_device": "cuda:0",
             "procyon_registered": True, "procyon_name": "nurglings-01"},
        ]
        output = format_gpu_pretty(gpus, procs)

        assert "=== GPU Overview ===" in output
        assert "GPU 0:" in output
        assert "NVIDIA GeForce RTX 3090" in output
        assert "8192 / 24576 MiB" in output
        assert "=== GPU Processes ===" in output
        assert "pthahnix" in output
        assert "train.py" in output
        assert "nurglings-01" in output
        assert "* GPU_UTIL is per-card, not per-process" in output

    def test_format_gpu_pretty_no_processes(self):
        from procyon import format_gpu_pretty

        gpus = [
            {"index": 0, "name": "NVIDIA GeForce RTX 3090",
             "memory_total": "24576 MiB", "memory_used": "0 MiB",
             "memory_free": "24576 MiB", "utilization": "0 %",
             "temperature": "35 C", "uuid": "GPU-uuid-0000"},
        ]
        output = format_gpu_pretty(gpus, [])

        assert "=== GPU Overview ===" in output
        assert "No GPU processes running." in output

    def test_gpu_subcommand_exists(self):
        """procyon gpu should be a recognized subcommand."""
        rc, out, err = run_procyon('gpu')
        # Should not fail with "invalid choice" — may return empty JSON
        assert rc == 0 or "invalid choice" not in err

    def test_gpu_args_parsing(self):
        """--user and --pretty flags should parse without error."""
        from procyon import build_parser
        parser = build_parser()
        args = parser.parse_args(['gpu', '--user', 'pthahnix', '--pretty'])
        assert args.command == 'gpu'
        assert args.user == 'pthahnix'
        assert args.pretty is True

    def test_gpu_json_output_structure(self):
        """Full cmd_gpu flow with mocked nvidia-smi and ps."""
        from unittest.mock import patch, MagicMock, call
        from procyon import cmd_gpu, ensure_dirs, save_registry
        import io

        ensure_dirs()
        # Save a registry entry for PID 1001
        save_registry({
            "processes": {
                "nurglings-01": {"pid": 1001, "cmd": "train.py",
                                 "checkpoint_dir": None, "started": "2026-03-29T00:00:00",
                                 "registered_by": "run", "done_marker": "checkpoint_final.pt"},
            },
            "version": "0.2.0"
        })

        gpu_info_result = MagicMock()
        gpu_info_result.returncode = 0
        gpu_info_result.stdout = "0, RTX 3090, 24576 MiB, 8192 MiB, 16384 MiB, 45 %, 62, GPU-uuid-0000\n"

        compute_apps_result = MagicMock()
        compute_apps_result.returncode = 0
        compute_apps_result.stdout = "1001, GPU-uuid-0000, 4096 MiB\n"

        ps_result = MagicMock()
        ps_result.returncode = 0
        ps_result.stdout = "pthahnix  1001  254.0  1.4 train.py\n"

        def mock_subprocess_run(cmd, **kwargs):
            cmd_str = ' '.join(cmd)
            if '--query-gpu=' in cmd_str:
                return gpu_info_result
            elif '--query-compute-apps=' in cmd_str:
                return compute_apps_result
            elif cmd[0] == 'ps':
                return ps_result
            return MagicMock(returncode=1, stdout='')

        args = type('Args', (), {'user': None, 'pretty': False})()

        with patch('subprocess.run', side_effect=mock_subprocess_run), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            try:
                cmd_gpu(args)
            except SystemExit:
                pass
            output = json.loads(mock_stdout.getvalue())

        assert "gpus" in output
        assert "processes" in output
        assert len(output["gpus"]) == 1
        assert output["gpus"][0]["index"] == 0
        assert len(output["processes"]) == 1
        proc = output["processes"][0]
        assert proc["user"] == "pthahnix"
        assert proc["pid"] == 1001
        assert proc["gpu_memory"] == "4096 MiB"
        assert proc["cuda_device"] == "cuda:0"
        assert proc["procyon_registered"] is True
        assert proc["procyon_name"] == "nurglings-01"

    def test_gpu_user_filter(self):
        """--user should filter processes to matching user only."""
        from unittest.mock import patch, MagicMock
        from procyon import cmd_gpu, ensure_dirs
        import io

        ensure_dirs()

        gpu_info_result = MagicMock()
        gpu_info_result.returncode = 0
        gpu_info_result.stdout = "0, RTX 3090, 24576 MiB, 8192 MiB, 16384 MiB, 45 %, 62, GPU-uuid-0000\n"

        compute_apps_result = MagicMock()
        compute_apps_result.returncode = 0
        compute_apps_result.stdout = (
            "1001, GPU-uuid-0000, 4096 MiB\n"
            "1002, GPU-uuid-0000, 2048 MiB\n"
        )

        ps_result = MagicMock()
        ps_result.returncode = 0
        ps_result.stdout = (
            "pthahnix  1001  254.0  1.4 train.py\n"
            "dyn       1002  460.0  0.7 main.py\n"
        )

        def mock_subprocess_run(cmd, **kwargs):
            cmd_str = ' '.join(cmd)
            if '--query-gpu=' in cmd_str:
                return gpu_info_result
            elif '--query-compute-apps=' in cmd_str:
                return compute_apps_result
            elif cmd[0] == 'ps':
                return ps_result
            return MagicMock(returncode=1, stdout='')

        args = type('Args', (), {'user': 'pthahnix', 'pretty': False})()

        with patch('subprocess.run', side_effect=mock_subprocess_run), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            try:
                cmd_gpu(args)
            except SystemExit:
                pass
            output = json.loads(mock_stdout.getvalue())

        assert len(output["processes"]) == 1
        assert output["processes"][0]["user"] == "pthahnix"

    def test_gpu_nvidia_smi_missing(self):
        """Should print error and exit 1 when nvidia-smi fails."""
        from unittest.mock import patch
        from procyon import cmd_gpu, ensure_dirs
        import io

        ensure_dirs()

        with patch('subprocess.run', side_effect=FileNotFoundError("nvidia-smi not found")), \
             patch('sys.stdout', new_callable=io.StringIO) as mock_stdout:
            try:
                cmd_gpu(type('Args', (), {'user': None, 'pretty': False})())
            except SystemExit as e:
                assert e.code == 1
            output = json.loads(mock_stdout.getvalue())
            assert output["code"] == "NVIDIA_SMI_ERROR"
