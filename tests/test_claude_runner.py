import os
import unittest
from unittest import mock

os.environ.setdefault("FEISHU_APP_ID", "test-app-id")
os.environ.setdefault("FEISHU_APP_SECRET", "test-app-secret")

import claude_runner


class _DummyStdin:
    def __init__(self):
        self.buffer = []
        self.closed = False

    def write(self, data):
        self.buffer.append(data)

    async def drain(self):
        return None

    def close(self):
        self.closed = True


class _DummyStdout:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _DummyStderr:
    async def read(self):
        return b""


class _DummyProc:
    def __init__(self):
        self.stdin = _DummyStdin()
        self.stdout = _DummyStdout()
        self.stderr = _DummyStderr()
        self.returncode = 0

    async def wait(self):
        return self.returncode


class ClaudeRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_claude_reports_process_handle(self):
        proc = _DummyProc()
        seen = []

        async def on_process_start(started_proc):
            seen.append(started_proc)

        with mock.patch.object(
            claude_runner.asyncio,
            "create_subprocess_exec",
            mock.AsyncMock(return_value=proc),
        ):
            await claude_runner.run_claude(
                "hello",
                on_process_start=on_process_start,
            )

        self.assertEqual(seen, [proc])


if __name__ == "__main__":
    unittest.main()
