# feishu-claude-code

在飞书里直接和你本机的 Claude Code 对话。

WebSocket 长连接，流式卡片输出，手机上随时 code review、debug、问问题。

> 复用 Claude Max/Pro 订阅，不需要 API Key，不需要公网 IP。

## 特性

**核心能力**

- **流式卡片输出** — Claude 边想边输出，工具调用进度实时可见，不是等半天发一坨
- **Session 跨设备** — 手机上开始的对话，回到电脑前接着聊；CLI 终端的会话也能在飞书恢复
- **图片识别** — 直接发截图给 Claude 分析
- **斜杠命令** — 切换模型、恢复会话、查看用量、管理工作目录
- **Skills 透传** — `/commit`、`/review` 等 Claude Code Skills 直接在飞书里用

**群聊支持 (beta)**

- 拉机器人进群，**@机器人** 即可对话，不 @ 的消息静默忽略
- 每个群独立 session、模型、工作目录，和私聊互不干扰
- `/ws` 命令为不同群绑定不同项目目录，多群并发互不阻塞

**部署简单**

- **无需公网 IP** — 飞书 WebSocket 长连接，部署在家里的 Mac 上就行
- **零额外成本** — 直接调用本机 `claude` CLI，复用已有订阅
- **看门狗自愈** — 4 小时自动重启，防止 WebSocket 连接假死

## 快速开始

### 前置条件

| 依赖 | 最低版本 | 验证命令 |
|------|---------|---------|
| Python | 3.11+ | `python3 --version` |
| Claude Code CLI | 最新 | `claude --version` |
| Claude Max/Pro 订阅 | — | `claude "hi"` 能正常回复 |

### 安装与启动

```bash
git clone https://github.com/joewongjc/feishu-claude-code.git
cd feishu-claude-code

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 编辑 .env，填入飞书应用凭证（见下方「飞书应用配置」）

python main.py
```

预期输出：

```
🚀 飞书 Claude Bot 启动中...
   App ID      : cli_xxx...
✅ 连接飞书 WebSocket 长连接（自动重连）...
```

> 从旧版升级的用户可运行 `python migrate_sessions.py` 迁移 session 数据（会自动备份）。

## 命令速查

**会话管理**

| 命令 | 说明 |
|------|------|
| `/new` | 开始新 session |
| `/resume` | 查看历史 sessions |
| `/resume 序号` | 恢复指定 session |
| `/stop` | 停止当前正在运行的任务 |
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
| `/ls` | 查看当前工作目录内容 |
| `/ws save 名称 路径` | 保存命名工作空间 |
| `/ws use 名称` | 绑定当前群组/私聊到工作空间 |

**信息查询**

| 命令 | 说明 |
|------|------|
| `/usage` | 查看 Claude Max 用量 (macOS) |
| `/skills` | 列出 Claude Skills |
| `/mcp` | 列出 MCP Servers |
| `/help` | 帮助 |

**Skills 透传**

`/commit` 等未注册的斜杠命令会直接转发给 Claude CLI 执行。

## 架构

```
┌──────────┐  WebSocket  ┌────────────────┐  subprocess  ┌────────────┐
│  飞书 App │◄───────────►│ feishu-claude  │─────────────►│ claude CLI │
│  (用户)   │  长连接      │  (main.py)     │ stream-json  │  (本机)     │
└──────────┘             └────────────────┘              └────────────┘
```

飞书通过 WebSocket 推送消息到本机进程，进程调用 `claude` CLI 的 `--print --output-format stream-json` 模式获取流式输出，再通过飞书卡片消息的 patch API 实时更新内容。

## 飞书应用配置

### 1. 创建应用

1. 打开 [飞书开放平台](https://open.feishu.cn/app)，点击「创建企业自建应用」
2. 填写应用名称（如 `Claude Code`），选择图标，点击创建

### 2. 添加机器人能力

1. 进入应用详情，左侧菜单选择「添加应用能力」
2. 添加「机器人」能力

### 3. 开启权限

进入「权限管理」页面，搜索并开启以下权限：

| 权限 scope | 说明 |
|-----------|------|
| `im:message` | 获取与发送单聊、群组消息 |
| `im:message:send_as_bot` | 以应用的身份发送消息 |
| `im:resource` | 获取消息中的资源文件（图片等） |

### 4. 启用长连接模式

1. 左侧菜单「事件与回调」→「事件配置」
2. 订阅方式选择「使用长连接接收事件」（不是 Webhook）
3. 添加事件：`im.message.receive_v1`（接收消息）

### 5. 获取凭证

1. 进入「凭证与基础信息」页面
2. 复制 App ID 和 App Secret，填入 `.env` 文件

### 6. 发布应用

1. 点击「版本管理与发布」→「创建版本」
2. 填写版本号和更新说明，提交审核
3. 管理员在飞书管理后台审核通过后即可使用

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|:---:|-------|------|
| `FEISHU_APP_ID` | 是 | — | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 是 | — | 飞书应用 App Secret |
| `DEFAULT_MODEL` | 否 | `claude-sonnet-4-6` | 默认使用的 Claude 模型 |
| `DEFAULT_CWD` | 否 | `~` | Claude CLI 的默认工作目录 |
| `PERMISSION_MODE` | 否 | `bypassPermissions` | 工具权限模式 |
| `STREAM_CHUNK_SIZE` | 否 | `20` | 流式推送的字符积累阈值 |
| `CLAUDE_CLI_PATH` | 否 | 自动查找 | Claude CLI 可执行文件路径 |

## 持久化部署

### macOS (launchctl)

```bash
cp deploy/feishu-claude.plist ~/Library/LaunchAgents/com.feishu-claude.bot.plist
# 修改 plist 中的 /path/to/ 为实际路径

launchctl load ~/Library/LaunchAgents/com.feishu-claude.bot.plist
launchctl list | grep feishu-claude
tail -f /tmp/feishu-claude.log
```

### Linux (systemd)

```bash
sudo cp deploy/feishu-claude.service /etc/systemd/system/
# 修改 service 中的路径和 User

sudo systemctl daemon-reload
sudo systemctl enable feishu-claude
sudo systemctl start feishu-claude
journalctl -u feishu-claude -f
```

---

## English

**feishu-claude-code** bridges your local Claude Code CLI with Feishu/Lark messenger via WebSocket.

- No public IP needed (Feishu WebSocket long connection)
- Streaming card output (real-time typing effect with tool call progress)
- Reuses Claude Max/Pro subscription (no API key required)
- Full session management across devices
- Group chat support with @mention filtering and session isolation (beta)
- Image recognition, slash commands, Claude Skills passthrough

Quick start: clone, `pip install -r requirements.txt`, configure `.env`, run `python main.py`.

See the Chinese sections above for detailed setup instructions.

## License

[MIT](LICENSE)
