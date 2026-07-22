# 多轮对话与历史会话设计

当前时间：2026-07-11  Asia/Shanghai

## 目标

多轮对话用于解决游客追问中的省略指代问题，例如“那门票呢”“怎么去”“今日天气如何”。当前版本已经引入后端持久化历史会话：游客端使用匿名 `visitor_id`，后端用 PostgreSQL 保存会话和消息，问答时优先读取后端最近历史构建上下文。

旧的 `history` 请求字段继续兼容；当请求没有 `visitor_id` 或 `persist_history=false` 时，系统仍可使用前端传入的 `history` 作为轻量上下文。

## 存储设计

关系数据通过必填的 `DATABASE_URL` 连接 PostgreSQL，使用 schema：

```text
conversations
```

核心表：

- `conversation_sessions`：保存 `session_id`、`visitor_id`、标题、最近问题、创建时间、更新时间。
- `chat_messages`：保存单条用户/助手消息、`trace_id`、`sources`、`tool_trace`、创建时间。
- `completed_realtime_turns`：保存已完成实时轮次标识，保证重试幂等。

第一版只保存对话历史，不保存长期用户画像或偏好记忆。

## 请求格式

旧请求仍然可用：

```json
{"question": "灵山胜境有什么特色？"}
```

带持久会话的请求：

```json
{
  "question": "那门票呢？",
  "visitor_id": "visitor_xxx",
  "session_id": "sess_xxx",
  "persist_history": true,
  "history": []
}
```

规则：

- 传入 `session_id` 时，后端校验该会话是否属于当前 `visitor_id`，然后读取最近 12 条消息作为上下文。
- 未传入 `session_id` 但传入 `visitor_id` 时，后端自动创建新会话并返回 `session_id`。
- 后端会把单条历史消息裁剪到 800 字以内，避免 prompt 膨胀。

## 响应字段

普通 JSON 响应会额外包含：

```json
{
  "answer": "...",
  "sources": [],
  "confidence": 0.82,
  "is_answered": true,
  "trace_id": "agent_xxx",
  "needs_clarification": false,
  "clarifying_question": "",
  "session_id": "sess_xxx",
  "session_title": "灵山胜境有什么特色？"
}
```

流式接口的 `meta` 和 `done` 事件也会携带 `session_id`、`session_title`。

## 历史会话 API

```text
GET /api/visitor/sessions?visitor_id=xxx
GET /api/visitor/sessions/{session_id}/messages?visitor_id=xxx
DELETE /api/visitor/sessions/{session_id}?visitor_id=xxx
```

删除接口只删除一个明确会话及其消息，不提供批量删除。

## 上下文处理流程

```text
用户问题 + visitor_id/session_id
→ 读取后端最近 12 条消息
→ 如无后端历史，则兼容使用请求 history
→ 构建 ConversationContext
→ 补全 standalone_question
→ 按需问题扩写
→ RAG 检索或 Agent 工具调用
→ 回答生成
→ 写入用户消息和助手消息
```

## 前端行为

游客端会在 `localStorage` 中维护：

- `lingjing_visitor_id`：匿名游客标识。
- `lingjing_current_session_id`：当前会话 ID。

页面提供基础入口：

- “历史会话”：查看并切换已保存会话。
- “新建会话”：清空当前 `session_id`，下一次提问创建新会话。
- “删除当前会话”：删除一个明确会话。
- “清空上下文”：只清空前端内存 `chatHistory`，不删除后端会话。

`chatHistory` 仍保留为即时体验兜底，但以后端历史为准。

## 当前边界

- 第一版不做登录系统，不绑定真实用户账号。
- 第一版不做跨浏览器、跨设备同步；同一浏览器可通过 `localStorage` 恢复匿名会话。
- 第一版不做长期偏好记忆，历史只帮助理解上下文，不放宽事实性回答边界。
- 第一版只支持游客端历史会话；管理端统计和调试视图后续再做。
