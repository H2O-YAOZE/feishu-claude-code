import asyncio
import unittest

from run_control import ActiveRunRegistry, stop_run


class FakeProc:
    def __init__(self):
        self.returncode = None
        self.terminate_called = False
        self.kill_called = False
        self.wait_calls = 0

    def terminate(self):
        self.terminate_called = True
        self.returncode = -15

    def kill(self):
        self.kill_called = True
        self.returncode = -9

    async def wait(self):
        self.wait_calls += 1
        return self.returncode


class RunControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_run_returns_false_when_no_active_run(self):
        registry = ActiveRunRegistry()

        stopped = await stop_run(registry, "user-1")

        self.assertFalse(stopped)

    async def test_stop_run_terminates_active_process_and_marks_state(self):
        registry = ActiveRunRegistry()
        run = registry.start_run("user-1", "card-1")
        proc = FakeProc()
        registry.attach_process("user-1", proc)
        stopped_runs = []

        async def on_stopped(active_run):
            stopped_runs.append(active_run)

        stopped = await stop_run(registry, "user-1", on_stopped=on_stopped)

        self.assertTrue(stopped)
        self.assertTrue(run.stop_requested)
        self.assertTrue(run.stop_announced)
        self.assertTrue(proc.terminate_called)
        self.assertFalse(proc.kill_called)
        self.assertEqual(proc.wait_calls, 1)
        self.assertEqual(stopped_runs, [run])

    async def test_attach_process_terminates_if_stop_was_requested_earlier(self):
        registry = ActiveRunRegistry()
        run = registry.start_run("user-1", "card-1")
        run.stop_requested = True
        proc = FakeProc()

        registry.attach_process("user-1", proc)

        self.assertIs(run.proc, proc)
        self.assertTrue(proc.terminate_called)


if __name__ == "__main__":
    unittest.main()
