# 故障排查

## 机器人"连着但不回消息"

### 症状

- 飞书里给机器人发消息，完全没反应
- 日志里明明有 `✅ 事件订阅已连接`，看起来连上了
- 但永远没有 `[收到消息]` 这一行事件到达
- Watchdog 每 10 分钟重启一次连接，重启后还是同样症状

### 根因：配置被别的 skill 悄悄覆盖了

Bridge 的架构有一个隐形依赖：

- **发消息**走 Python SDK，读的是项目里的 `.env`
- **收消息**走 `lark-cli` 子进程，默认读的是**全局** `~/.lark-cli/config.json`

这台 Mac 上装了一堆 lark-\* skill（lark-mail、lark-minutes、lark-doc、lark-base 等等），它们**共用同一个**全局配置文件。谁最后写谁就赢。如果某个 skill 把这份配置改成了另一个飞书 App 的凭证，bridge 的 lark-cli 子进程跟着订阅了那个 App 的事件，但你的机器人绑在**另一个 App** 上，消息就永远到不了 bridge。

**打个比方：** 你家装了两部电话，一部（Python SDK）专门拨出去，一部（lark-cli）专门接听。室友（别的 skill）把接听这部电话的号码改了，别人再打你家旧号码进来，那边永远没人接。你自己拨出去还正常，因为那部电话号码没被动。

### 已做的修复

1. bridge 直接共用全局配置 `~/.lark-cli/config.json`（里面存的就是 Zara's CC 的 App 凭证，appSecret 走 keychain 更安全）
2. `main.py` 的 `lark-cli event +subscribe` 加了 `--force` 参数，启动时强制接管飞书后端的 WebSocket 槽位，避免崩溃残留的幽灵连接吃掉事件

> 注意：既然共用全局配置，如果某天你在别的 lark-\* skill 里切换了身份或换了 App，bridge 会跟着变。真要再出现"收不到消息"，先确认这份配置没被别的 skill 改掉。

### 下次自己怎么诊断

症状一样（连着但收不到），按顺序跑这两步：

```bash
# 1. 全局配置现在配的 App ID 是哪个？
lark-cli config show | grep appId

# 2. 和 .env 里的 FEISHU_APP_ID 比对，必须完全一致
grep FEISHU_APP_ID "/Users/bytedance/Documents/Claude code projects/feishu-claude-code/.env"
```

App ID 对不上，就是配置被别的 skill 覆盖了。**修复方式：** 用 `lark-cli auth login` 重新登录到 Zara's CC 那个 App。

如果 App ID 都对得上但还是收不到，可能的下一层问题：

- 飞书开放平台那边 `im.message.receive_v1` 事件订阅被取消了
- 机器人被管理员禁用或权限被撤销
- App Secret 过期或被刷新（需要重新从开放平台获取并更新两份配置）

### 重启命令速查

```bash
# 完全重启（改了 plist 之后必须这样，kickstart 不会重载环境变量）
launchctl unload ~/Library/LaunchAgents/com.zara.feishu-claude.plist
launchctl load ~/Library/LaunchAgents/com.zara.feishu-claude.plist

# 快速踢一脚（没改配置、只是进程卡住了）
launchctl kickstart -k gui/$(id -u)/com.zara.feishu-claude

# 看日志
tail -f "/Users/bytedance/Documents/Claude code projects/feishu-claude-code/stdout.log"
```
