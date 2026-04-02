import os
import shutil
from dotenv import load_dotenv

load_dotenv()

FEISHU_APP_ID = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]

CLAUDE_CLI = os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude") or "claude"

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-opus-4-6")
DEFAULT_CWD = os.path.expanduser(os.getenv("DEFAULT_CWD", "~"))
PERMISSION_MODE = os.getenv("PERMISSION_MODE", "bypassPermissions")

SESSIONS_DIR = os.path.expanduser("~/.feishu-claude")

# 卡片按钮回调 HTTP 端口（需 ngrok 暴露）
CALLBACK_PORT = int(os.getenv("CALLBACK_PORT", "9981"))

# 流式卡片更新：每积累多少字符推送一次
STREAM_CHUNK_SIZE = int(os.getenv("STREAM_CHUNK_SIZE", "20"))
