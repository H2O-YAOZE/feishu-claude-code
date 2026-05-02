# feishu-claude-code

在飞书里实时对话 Claude Code。WebSocket 长连接，流式卡片输出，手机上随时 code review、debug、问问题。

> 复用 Claude Max/Pro 订阅，不需要 API Key，不需要公网 IP。

## 与同类项目的差异

| 能力 | 原版 feishu-claude-code | 本项目 |
|---|---|---|
| 文本/图片消息 | ✅ | ✅ |
| 富文本/转发消息 | ❌ | ✅ |
| 文件消息 (PDF/Word 等) | ❌ | ✅ 自动下载后分析 |
| 语音消息 | ❌ | ✅ 下载到本地 |
| 文档链接自动解析 | ❌ | ✅ 自动取内容嵌入上下文 |
| 长回复 (>200字) | 流式卡片慢 | ✅ 自动生成飞书文档 |
| 文档评论 @回复 | ✅ | ✅ |
| 休眠唤醒自动重连 | ❌ | ✅ |
| 日志噪音过滤 | ❌ | ✅ |
| 外部文档安全边界 | ❌ | ✅ |

## 特性

**消息类型全覆盖**
- 文本、富文本 (post)、图片、文件 (PDF/Word/Excel/压缩包)、语音 (audio)、转发 (merge_forward)
- 群聊 @机器人 触发，私聊直接对话

**飞书文档深度集成**
- 文档链接自动识别并获取内容（docx/wiki/sheets/base/mindnotes/minutes）
- 长回复自动写入飞书文档，聊天里只发链接
- 文档评论 @机器人 自动回复

**流式卡片输出**
- Claude 实时思考过程可见
- 工具调用进度实时展示
- 支持卡片按钮交互（选项选择、模式切换）

**Session 管理**
- 跨设备恢复会话（手机上开始，电脑前继续）
- 群聊独立 session，互不干扰
- `/ws` 为不同群绑定不同工作目录

**运维健壮**
- 笔记本休眠唤醒自动重连
- DNS/网络抖动自动恢复
- launchd (macOS) / 启动脚本 (Windows) 保活

## 架构

```
┌──────────┐  WebSocket  ┌────────────────┐  subprocess  ┌────────────┐
│  飞书 App │◄───────────►│ feishu-bridge   │─────────────►│ claude CLI │
│  (用户)   │  长连接      │  (main.py)      │ stream-json  │  (本机)     │
└──────────┘             └────────────────┘              └────────────┘
                                │
                                │ subprocess (--as user)
                                ▼
                         ┌────────────┐
                         │  lark-cli   │  ← 用户 token，文档/文件/IM 操作
                         └────────────┘
```

关键设计决策：
- **收消息走 lark-cli WebSocket**：App 鉴权，不暴露公网端口
- **发消息走 Python SDK (lark_oapi)**：租户 token，流式卡片 patch
- **文档操作走 lark-cli**：用户 token，直接以用户身份读写文档，无需额外授权

## 快速开始

### 前置条件

| 依赖 | 最低版本 | 验证 |
|------|---------|------|
| Python | 3.11+ | `python --version` |
| Claude Code CLI | 最新 | `claude --version` |
| Claude Max/Pro 订阅 | — | `claude "hi"` 正常回复 |
| lark-cli | 1.0.20+ | `lark-cli --version` |

### 1. 飞书应用配置

1. [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用
2. 添加「机器人」能力
3. 权限管理 → 开启：
   - `im:message` — 获取与发送消息
   - `im:message:send_as_bot` — 以应用身份发消息
   - `im:resource` — 获取消息中资源文件
4. 事件与回调 → 使用长连接接收事件 → 添加 `im.message.receive_v1`
5. 凭证与基础信息 → 复制 App ID 和 App Secret
6. 版本管理与发布 → 创建版本 → 管理员审核通过

### 2. 安装

```bash
git clone https://github.com/zarazhangrui/feishu-claudecode-bridge.git
cd feishu-claudecode-bridge

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入 App ID 和 App Secret
```

### 3. lark-cli 登录

```bash
npm install -g @larksuite/cli
lark-cli config init
lark-cli auth login   # 浏览器授权，获取用户 token
```

### 4. 启动

```bash
# 前台运行
python main.py

# Windows 后台（登录自动启动）
start_bridge.bat

# macOS 后台（launchd 保活）
cp deploy/feishu-claude.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.zara.feishu-claude.plist
```

预期输出：

```
🚀 飞书 Claude Bot 启动中...
   App ID      : cli_xxx...
✅ 连接飞书 WebSocket 长连接（自动重连）...
```

## 命令速查

**会话管理**

| 命令 | 说明 |
|------|------|
| `/new` | 开始新 session |
| `/resume` | 查看历史 sessions |
| `/resume 序号` | 恢复指定 session |
| `/stop` | 停止当前任务 |
| `/status` | 当前 session 信息 |

**模型与模式**

| 命令 | 说明 |
|------|------|
| `/model opus` | 切换模型 (opus / sonnet / haiku) |
| `/mode bypass` | 切换权限模式 |

**工作目录**

| 命令 | 说明 |
|------|------|
| `/cd ~/project` | 切换工作目录 |
| `/ls` | 查看当前工作目录 |
| `/ws save 名称 路径` | 保存命名工作空间 |
| `/ws use 名称` | 绑定当前群/私聊到工作空间 |

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|:---:|-------|------|
| `FEISHU_APP_ID` | 是 | — | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 是 | — | 飞书应用 App Secret |
| `DEFAULT_MODEL` | 否 | `claude-sonnet-4-6` | 默认模型 |
| `DEFAULT_CWD` | 否 | `~` | 默认工作目录 |
| `PERMISSION_MODE` | 否 | `bypassPermissions` | 权限模式 |
| `STREAM_CHUNK_SIZE` | 否 | `20` | 流式推送积累阈值 |
| `CLAUDE_CLI_PATH` | 否 | 自动查找 | Claude CLI 路径 |

## License

[MIT](LICENSE)
