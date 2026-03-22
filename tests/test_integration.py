"""
集成测试：模拟完整的消息处理流程。
Mock 掉飞书 API 和 Claude CLI，验证从收到消息到发送回复的完整链路。
"""
import asyncio
import json
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

os.environ.setdefault("FEISHU_APP_ID", "test_app_id")
os.environ.setdefault("FEISHU_APP_SECRET", "test_app_secret")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── helpers ──────────────────────────────────────────────────

def _make_event(
    user_id: str = "user_001",
    chat_id: str = "user_001",
    chat_type: str = "p2p",
    text: str = "hello",
    message_id: str = "msg_001",
    mentions: list = None,
):
    """构造一个模拟的飞书消息事件"""
    event = MagicMock()
    event.event.sender.sender_id.open_id = user_id
    event.event.message.chat_type = chat_type
    event.event.message.chat_id = chat_id
    event.event.message.message_type = "text"
    event.event.message.content = json.dumps({"text": text})
    event.event.message.message_id = message_id
    event.event.message.mentions = mentions
    return event


def _make_claude_output(text: str, session_id: str = "sid_abc123") -> list[bytes]:
    """构造 Claude CLI 的 stream-json 输出行"""
    lines = [
        json.dumps({"type": "system", "session_id": session_id}).encode() + b"\n",
    ]
    # 分成小块模拟流式
    chunk_size = 20
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        lines.append(json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": chunk},
            },
        }).encode() + b"\n")
    lines.append(json.dumps({
        "type": "result",
        "session_id": session_id,
        "result": text,
    }).encode() + b"\n")
    return lines


def _make_tool_use_output(
    tool_name: str,
    tool_input: dict,
    result_text: str,
    session_id: str = "sid_abc123",
) -> list[bytes]:
    """构造包含工具调用的 Claude CLI 输出"""
    lines = [
        json.dumps({"type": "system", "session_id": session_id}).encode() + b"\n",
        # tool_use start
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {"type": "tool_use", "name": tool_name},
            },
        }).encode() + b"\n",
        # tool input delta
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": json.dumps(tool_input),
                },
            },
        }).encode() + b"\n",
        # tool_use stop
        json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_stop"},
        }).encode() + b"\n",
        # text output
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": result_text},
            },
        }).encode() + b"\n",
        # result
        json.dumps({
            "type": "result",
            "session_id": session_id,
            "result": result_text,
        }).encode() + b"\n",
    ]
    return lines


class FakeProc:
    """模拟 asyncio.create_subprocess_exec 返回的进程"""
    def __init__(self, stdout_lines: list[bytes], returncode: int = 0):
        self.stdin = MagicMock()
        self.stdin.write = MagicMock()
        self.stdin.drain = AsyncMock()
        self.stdin.close = MagicMock()
        self._lines = list(stdout_lines)
        self._index = 0
        self.stderr = MagicMock()
        self.stderr.read = AsyncMock(return_value=b"")
        self.returncode = returncode

    @property
    def stdout(self):
        return self

    async def readline(self):
        if self._index >= len(self._lines):
            return b""
        line = self._lines[self._index]
        self._index += 1
        return line

    async def wait(self):
        return self.returncode

    def kill(self):
        pass


# ── 测试：私聊完整流程 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_private_chat_full_flow():
    """私聊消息 → Claude 回复 → 卡片更新的完整流程"""
    from main import handle_message_async, _chat_locks

    _chat_locks.clear()
    event = _make_event(text="你好，帮我看看代码")
    claude_lines = _make_claude_output("代码看起来没问题，测试也通过了。")
    proc = FakeProc(claude_lines)

    card_updates = []

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("asyncio.create_subprocess_exec", return_value=proc):

        # Mock feishu client
        mock_feishu.send_card_to_user = AsyncMock(return_value="card_msg_001")
        mock_feishu.update_card = AsyncMock(side_effect=lambda mid, content: card_updates.append(content))
        mock_feishu.send_text_to_user = AsyncMock()

        # Mock store
        mock_session = MagicMock()
        mock_session.session_id = None
        mock_session.model = "claude-sonnet-4-6"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "bypassPermissions"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_claude_response = AsyncMock()

        await handle_message_async(event)

    # 验证：发送了占位卡片
    mock_feishu.send_card_to_user.assert_called_once()
    assert mock_feishu.send_card_to_user.call_args[1].get("loading") is True

    # 验证：卡片被更新过（流式 + 最终）
    assert len(card_updates) > 0
    # 最后一次更新应该是完整内容
    assert "代码看起来没问题" in card_updates[-1]

    # 验证：session 状态被更新
    mock_store.on_claude_response.assert_called_once()


@pytest.mark.asyncio
async def test_private_chat_streaming_updates_card():
    """验证流式文本确实会增量更新卡片"""
    from main import handle_message_async, _chat_locks
    import bot_config as config

    _chat_locks.clear()
    # 生成一段比 STREAM_CHUNK_SIZE 长的文本，确保触发中间推送
    long_text = "x" * (config.STREAM_CHUNK_SIZE * 3)
    event = _make_event(text="写段代码")
    claude_lines = _make_claude_output(long_text)
    proc = FakeProc(claude_lines)

    card_updates = []

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("asyncio.create_subprocess_exec", return_value=proc):

        mock_feishu.send_card_to_user = AsyncMock(return_value="card_001")
        mock_feishu.update_card = AsyncMock(side_effect=lambda mid, content: card_updates.append(content))

        mock_session = MagicMock()
        mock_session.session_id = "existing_sid"
        mock_session.model = "claude-sonnet-4-6"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "bypassPermissions"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_claude_response = AsyncMock()

        await handle_message_async(event)

    # 应该有多次中间更新（流式推送）+ 一次最终更新
    # 至少 2 次中间推送（text 长度 = 3 * chunk_size，每 chunk_size 推一次）
    assert len(card_updates) >= 3, f"Expected >= 3 updates, got {len(card_updates)}"


@pytest.mark.asyncio
async def test_tool_use_updates_card_with_progress():
    """验证工具调用时卡片会显示工具进度"""
    from main import handle_message_async, _chat_locks

    _chat_locks.clear()
    event = _make_event(text="列出文件")
    claude_lines = _make_tool_use_output("Bash", {"command": "ls -la"}, "文件列表如下...")
    proc = FakeProc(claude_lines)

    card_updates = []

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("asyncio.create_subprocess_exec", return_value=proc):

        mock_feishu.send_card_to_user = AsyncMock(return_value="card_001")
        mock_feishu.update_card = AsyncMock(side_effect=lambda mid, content: card_updates.append(content))

        mock_session = MagicMock()
        mock_session.session_id = "sid_123"
        mock_session.model = "claude-sonnet-4-6"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "bypassPermissions"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_claude_response = AsyncMock()

        await handle_message_async(event)

    # 至少有一次更新包含工具调用进度
    tool_updates = [u for u in card_updates if "执行命令" in u or "ls -la" in u]
    assert len(tool_updates) > 0, f"No tool progress in updates: {card_updates}"

    # 最后一次更新是最终结果
    assert "文件列表如下" in card_updates[-1]


# ── 测试：群聊 @mention 过滤 ─────────────────────────────────

@pytest.mark.asyncio
async def test_group_chat_ignores_without_mention():
    """群聊消息没有 @机器人 时应该被忽略"""
    from main import handle_message_async, _chat_locks

    _chat_locks.clear()
    event = _make_event(
        user_id="user_001",
        chat_id="group_001",
        chat_type="group",
        text="这是一条普通群消息",
        mentions=None,  # 没有 @mention
    )

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store:
        mock_feishu.send_card_to_user = AsyncMock()
        mock_feishu.reply_card = AsyncMock()

        await handle_message_async(event)

    # 不应该有任何 feishu 调用
    mock_feishu.send_card_to_user.assert_not_called()
    mock_feishu.reply_card.assert_not_called()


@pytest.mark.asyncio
async def test_group_chat_ignores_empty_mention_list():
    """群聊消息 mentions 为空列表时也应该被忽略"""
    from main import handle_message_async, _chat_locks

    _chat_locks.clear()
    event = _make_event(
        user_id="user_001",
        chat_id="group_001",
        chat_type="group",
        text="没人被 at",
        mentions=[],
    )

    with patch("main.feishu") as mock_feishu:
        await handle_message_async(event)

    mock_feishu.reply_card.assert_not_called()


@pytest.mark.asyncio
async def test_group_chat_responds_with_mention():
    """群聊消息有 @机器人 时应该回复"""
    from main import handle_message_async, _chat_locks

    _chat_locks.clear()

    # 模拟 @mention 对象
    mention = MagicMock()
    mention.key = "@_user_1"

    event = _make_event(
        user_id="user_001",
        chat_id="group_001",
        chat_type="group",
        text="@_user_1 你好",
        message_id="group_msg_001",
        mentions=[mention],
    )

    claude_lines = _make_claude_output("你好！有什么可以帮你的？")
    proc = FakeProc(claude_lines)

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("asyncio.create_subprocess_exec", return_value=proc):

        mock_feishu.reply_card = AsyncMock(return_value="reply_card_001")
        mock_feishu.update_card = AsyncMock()

        mock_session = MagicMock()
        mock_session.session_id = None
        mock_session.model = "claude-sonnet-4-6"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "bypassPermissions"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_claude_response = AsyncMock()

        await handle_message_async(event)

    # 群聊应该用 reply_card 而不是 send_card_to_user
    mock_feishu.reply_card.assert_called()
    # 第一次调用是占位卡片
    first_call = mock_feishu.reply_card.call_args_list[0]
    assert first_call[0][0] == "group_msg_001"  # reply to original message
    assert first_call[1].get("loading") is True


@pytest.mark.asyncio
async def test_group_chat_strips_mention_placeholder():
    """群聊应该去掉 @mention 占位符后再发给 Claude"""
    from main import handle_message_async, _chat_locks

    _chat_locks.clear()

    mention = MagicMock()
    mention.key = "@_user_1"

    event = _make_event(
        user_id="user_001",
        chat_id="group_001",
        chat_type="group",
        text="@_user_1 帮我看看这段代码",
        message_id="group_msg_002",
        mentions=[mention],
    )

    captured_stdin = []
    claude_lines = _make_claude_output("代码没问题")

    class CapturingProc(FakeProc):
        def __init__(self, lines):
            super().__init__(lines)
            self.stdin = MagicMock()
            self.stdin.drain = AsyncMock()
            self.stdin.close = MagicMock()
            def capture_write(data):
                captured_stdin.append(data)
            self.stdin.write = capture_write

    proc = CapturingProc(claude_lines)

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("asyncio.create_subprocess_exec", return_value=proc):

        mock_feishu.reply_card = AsyncMock(return_value="reply_card_002")
        mock_feishu.update_card = AsyncMock()

        mock_session = MagicMock()
        mock_session.session_id = None
        mock_session.model = "claude-sonnet-4-6"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "bypassPermissions"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_claude_response = AsyncMock()

        await handle_message_async(event)

    # 验证发给 Claude 的文本不包含 @mention 占位符
    assert len(captured_stdin) > 0
    sent_text = captured_stdin[0].decode("utf-8")
    assert "@_user_1" not in sent_text
    assert "帮我看看这段代码" in sent_text


# ── 测试：群聊斜杠命令 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_group_chat_slash_command_with_mention():
    """群聊中 @机器人 + 斜杠命令应该正常工作"""
    from main import handle_message_async, _chat_locks

    _chat_locks.clear()

    mention = MagicMock()
    mention.key = "@_user_1"

    event = _make_event(
        user_id="user_001",
        chat_id="group_001",
        chat_type="group",
        text="@_user_1 /help",
        message_id="group_msg_003",
        mentions=[mention],
    )

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store:

        mock_feishu.reply_card = AsyncMock(return_value="reply_card_003")

        await handle_message_async(event)

    # /help 应该通过 reply_card 回复
    mock_feishu.reply_card.assert_called()
    # 回复内容应该包含帮助文本
    call_args = mock_feishu.reply_card.call_args
    assert "可用命令" in call_args[1].get("content", "")


# ── 测试：session 隔离（端到端）──────────────────────────────

@pytest.mark.asyncio
async def test_group_sessions_isolated_end_to_end():
    """不同群聊发消息，各自的 session 独立"""
    from main import handle_message_async, _chat_locks
    from session_store import SessionStore

    _chat_locks.clear()

    mention = MagicMock()
    mention.key = "@_user_1"

    # 两个群分别发 /model 命令设置不同模型
    event_a = _make_event(
        user_id="user_001", chat_id="group_a", chat_type="group",
        text="@_user_1 /model opus", message_id="msg_a",
        mentions=[mention],
    )
    event_b = _make_event(
        user_id="user_001", chat_id="group_b", chat_type="group",
        text="@_user_1 /model haiku", message_id="msg_b",
        mentions=[mention],
    )

    real_store = SessionStore()

    with patch("main.feishu") as mock_feishu, \
         patch("main.store", real_store):

        mock_feishu.reply_card = AsyncMock(return_value="card_id")

        await handle_message_async(event_a)
        await handle_message_async(event_b)

    session_a = await real_store.get_current("user_001", "group_a")
    session_b = await real_store.get_current("user_001", "group_b")

    assert session_a.model == "claude-opus-4-6"
    assert session_b.model == "claude-haiku-4-5-20251001"


# ── 测试：_chat_locks 清理 ──────────────────────────────────

@pytest.mark.asyncio
async def test_chat_locks_cleanup():
    """当 _chat_locks 超过上限时应该清理"""
    from main import _chat_locks, _MAX_CHAT_LOCKS, handle_message_async

    _chat_locks.clear()

    # 填满锁到上限
    for i in range(_MAX_CHAT_LOCKS):
        _chat_locks[f"chat_{i}"] = asyncio.Lock()

    assert len(_chat_locks) == _MAX_CHAT_LOCKS

    # 发一条新 chat 的消息，应该触发清理
    event = _make_event(
        user_id="user_new",
        chat_id="brand_new_chat",
        chat_type="p2p",
        text="/help",
    )

    with patch("main.feishu") as mock_feishu:
        mock_feishu.send_card_to_user = AsyncMock(return_value="card_id")
        await handle_message_async(event)

    # 清理后只剩新加入的那个（私聊 chat_id = user_id）
    assert len(_chat_locks) <= 2
    assert "user_new" in _chat_locks


# ── 测试：fresh session fallback ─────────────────────────────

@pytest.mark.asyncio
async def test_fresh_session_fallback_shows_warning():
    """当旧 session 失败并自动切换新 session 时，应该显示警告"""
    from main import handle_message_async, _chat_locks

    _chat_locks.clear()
    event = _make_event(text="继续刚才的")

    # 第一次调用失败（returncode=1, no stderr, no output）
    first_proc = FakeProc([], returncode=1)
    # 第二次调用成功
    second_lines = _make_claude_output("好的，我来帮你")
    second_proc = FakeProc(second_lines)
    procs = iter([first_proc, second_proc])

    card_updates = []

    with patch("main.feishu") as mock_feishu, \
         patch("main.store") as mock_store, \
         patch("asyncio.create_subprocess_exec", side_effect=lambda *a, **kw: next(procs)):

        mock_feishu.send_card_to_user = AsyncMock(return_value="card_001")
        mock_feishu.update_card = AsyncMock(side_effect=lambda mid, content: card_updates.append(content))

        mock_session = MagicMock()
        mock_session.session_id = "old_sid_that_fails"
        mock_session.model = "claude-sonnet-4-6"
        mock_session.cwd = "/tmp"
        mock_session.permission_mode = "bypassPermissions"
        mock_store.get_current = AsyncMock(return_value=mock_session)
        mock_store.on_claude_response = AsyncMock()

        await handle_message_async(event)

    # 最后一次更新应该包含 fallback 警告
    assert any("自动切换到新 session" in u for u in card_updates), \
        f"No fallback warning in updates: {card_updates}"
    # 也应该包含实际回复
    assert any("好的，我来帮你" in u for u in card_updates)
