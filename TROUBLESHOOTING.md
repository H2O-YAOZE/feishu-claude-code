# 故障排查

## 机器人"连着但不回消息"

### 症状
- 飞书里给机器人发消息，完全没反应
- 日志里显示 `✅ 事件订阅已连接`
- 但没有 `[收到消息]` 日志
- 只有 `im.message.reaction.created_v1, not found handler`（这条无害，可忽略）

### 诊断步骤（按顺序）

```bash
# 1. 检查进程是否在跑
# Windows:
tasklist | findstr python
# macOS/Linux:
ps aux | grep "main.py"

# 2. 检查日志看连接状态
tail -20 bridge.log

# 3. 验证 App Secret 是否有效（在 bridge 目录执行）
python -c "from dotenv import load_dotenv; import os,json,ssl,urllib.request
load_dotenv()
app_id = os.environ['FEISHU_APP_ID']
app_secret = os.environ['FEISHU_APP_SECRET']
body = json.dumps({'app_id': app_id, 'app_secret': app_secret}).encode()
req = urllib.request.Request('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', data=body, headers={'Content-Type':'application/json'}, method='POST')
with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=10) as r:
    print(json.loads(r.read()))"
# 期望输出 code=0。如果是 code=10014 (app secret invalid)，需要从飞书开放平台获取新 Secret

# 4. 检查 App ID 一致
grep FEISHU_APP_ID .env
lark-cli config show | grep appId
# 两者必须一致
```

## Windows 特有故障

### 启动时报 `AttributeError: module 'os' has no attribute 'getpgid'`
根因：`os.getpgid()` / `os.killpg()` 仅限 Unix，Windows 不支持。
已修：`_kill_process_tree()` 和 `_cleanup_stale_processes()` 已适配 Windows（使用 `taskkill`）。

### 日志出现 `UnicodeDecodeError: 'gbk' codec can't decode`
根因：subprocess 管道在 Windows 上默认用 GBK 编码，但 lark-cli 输出 UTF-8。
已修：`Popen()` 调用显式指定 `encoding="utf-8"`。

### 僵尸 lark-cli.exe 占 WebSocket 槽位
症状：bridge 重连后收不到消息。
清理：
```cmd
taskkill /F /IM lark-cli.exe
taskkill /F /IM python.exe
:: 然后重新启动 bridge
```

### 每次启动需要 clear __pycache__
如果修改代码后不生效，清理 Python 字节码缓存：
```bash
rm -rf __pycache__
```

## macOS 特有故障

### 配置被别的 skill 覆盖
Bridge 收消息走 lark-cli 子进程，读全局 `~/.lark-cli/config.json`。如果别的 lark-* skill 改了这份配置的 App ID，bridge 收不到消息。

```bash
# 检查全局配置的 App ID
lark-cli config show | grep appId
# 与 .env 里的 FEISHU_APP_ID 对比
grep FEISHU_APP_ID .env
```

### 重启命令
```bash
# 完全重启（用 launchd）
launchctl unload ~/Library/LaunchAgents/com.zara.feishu-claude.plist
launchctl load ~/Library/LaunchAgents/com.zara.feishu-claude.plist

# 快速踢一脚
launchctl kickstart -k gui/$(id -u)/com.zara.feishu-claude

# 看日志
tail -f stdout.log
```

## 消息收到了但不回

日志出现 `[error] 发送占位卡片失败: app secret invalid`：
- `.env` 里的 `FEISHU_APP_SECRET` 过期或错误
- 从飞书开放平台 → 你的应用 → 凭证与基础信息 获取新 Secret
- 更新 `.env` 后重启 bridge

## 重启后收不到第二第三条消息

可能是 lark-cli 子进程的 WebSocket slot 被旧连接占用：
1. 清除所有残留进程（见上方对应平台）
2. 清除 `__pycache__`
3. 重新启动 bridge
4. 等日志输出 `✅ 事件订阅已连接` 再发消息
