# OpenCode 适配器（Comi 桌宠桥接）

OpenCode Server 的 HTTP SSE → 统一事件 → 本地收件箱。纯 Python 标准库，
无额外依赖。

## 用法

```bash
python3 adapters/opencode/comi_opencode.py --base http://127.0.0.1:4096
```

- 服务地址：`--base` 或 `OPENCODE_BASE_URL`（默认 `http://127.0.0.1:4096`，
  即 OpenCode 默认监听；请指向**你自己启动的服务**，不要指向陌生端口）。
- 认证：服务开了鉴权就设 `OPENCODE_TOKEN`（Bearer）。
- 监测转发**所有会话**的事件（桌宠按 session 分组显示）；第二阶段发送任务
  时才会让你显式选择 session——绝不固定用列表第一条。
- 断线自动退避重连（1/2/5/10/15s 封顶）；重连后按事件 id/组合键去重，
  不重复提醒；服务长时间不在线时桌宠按断线回退到普通轮播。
- 卸载：Ctrl-C 退出 + `rm -rf ~/.comi-pet`。

## 事件映射

| OpenCode | 统一事件 |
| --- | --- |
| session.status（busy / idle） | turn.started / turn.ended |
| session.idle / session.error | turn.ended / turn.failed |
| permission.asked | permission.required（replied 不映射，等状态流） |
| tool.execute.before / after | tool.started / tool.finished（带 toolCallID） |

`session.idle` 只表示空闲，不等于代码已通过测试。发送接口
（`POST /session/:id/prompt_async`，其 204 仅表示已入队）属第二阶段：
入队与结果分离、带请求 ID、重试不重复执行。

能力声明：read_state ✅ · read_summary ❌（第一版不读消息接口）·
send_prompt ❌（第二阶段）。

**验证程度**：本机未安装 OpenCode；以官方 Server HTTP API 文档为依据实现，
用本地 mock SSE 服务做了重放测试（`tests/test_opencode_adapter.py`）。
实机接入前请按你版本的 `/doc`（OpenAPI）核验事件字段名（适配器对常见
命名差异做了宽容提取）。
