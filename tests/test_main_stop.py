import asyncio
import os
import sys
import types
import unittest
from unittest import mock

os.environ.setdefault("FEISHU_APP_ID", "test-app-id")
os.environ.setdefault("FEISHU_APP_SECRET", "test-app-secret")


def _install_fake_lark():
    if "lark_oapi" in sys.modules:
        return

    class _Builder:
        def app_id(self, *_args, **_kwargs):
            return self

        def app_secret(self, *_args, **_kwargs):
            return self

        def log_level(self, *_args, **_kwargs):
            return self

        def request_body(self, *_args, **_kwargs):
            return self

        def receive_id_type(self, *_args, **_kwargs):
            return self

        def receive_id(self, *_args, **_kwargs):
            return self

        def msg_type(self, *_args, **_kwargs):
            return self

        def content(self, *_args, **_kwargs):
            return self

        def message_id(self, *_args, **_kwargs):
            return self

        def event_handler(self, *_args, **_kwargs):
            return self

        def register_p2_im_message_receive_v1(self, *_args, **_kwargs):
            return self

        def build(self):
            return self

    class _Client:
        @staticmethod
        def builder():
            return _Builder()

    class _WsClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            return None

    fake_lark = types.ModuleType("lark_oapi")
    fake_lark.Client = _Client
    fake_lark.LogLevel = types.SimpleNamespace(INFO="INFO")
    fake_lark.ws = types.SimpleNamespace(Client=_WsClient)
    fake_lark.EventDispatcherHandler = types.SimpleNamespace(builder=lambda *_args, **_kwargs: _Builder())

    model_mod = types.ModuleType("lark_oapi.api.im.v1.model")
    for name in (
        "P2ImMessageReceiveV1",
        "CreateMessageRequest",
        "CreateMessageRequestBody",
        "PatchMessageRequest",
        "PatchMessageRequestBody",
        "ReplyMessageRequest",
        "ReplyMessageRequestBody",
    ):
        setattr(model_mod, name, type(name, (), {"builder": staticmethod(lambda: _Builder())}))

    sys.modules["lark_oapi"] = fake_lark
    sys.modules["lark_oapi.api"] = types.ModuleType("lark_oapi.api")
    sys.modules["lark_oapi.api.im"] = types.ModuleType("lark_oapi.api.im")
    sys.modules["lark_oapi.api.im.v1"] = types.ModuleType("lark_oapi.api.im.v1")
    sys.modules["lark_oapi.api.im.v1.model"] = model_mod


_install_fake_lark()

import main


class MainStopTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_stop_command_returns_no_active_run_message(self):
        with mock.patch.object(main, "stop_run", mock.AsyncMock(return_value=False)):
            reply = await main._handle_stop_command("user-1")

        self.assertIn("没有正在运行", reply)

    async def test_handle_stop_command_requests_stop_for_active_run(self):
        active_run = mock.Mock(stop_requested=False)

        with mock.patch.object(
            main._active_runs,
            "get_run",
            return_value=active_run,
        ), mock.patch.object(
            main,
            "stop_run",
            mock.AsyncMock(return_value=True),
        ) as stop_run_mock:
            reply = await main._handle_stop_command("user-1")

        stop_run_mock.assert_awaited_once()
        self.assertIn("已发送停止请求", reply)


if __name__ == "__main__":
    unittest.main()
