# 双模式 Qwen-Audio 智能导游

`/visitor/guide` 通过 `WS /api/visitor/realtime` 共用一条实时会话：常规模式仅请求文本，数字人模式请求文本和 24kHz PCM 音频。切换模式不会创建模型请求，也不会清空 PostgreSQL 历史。

## 配置

```yaml
LJAPI_KEY: 你的阿里云百炼 API Key
LJ_REALTIME_MODEL: qwen-audio-3.0-realtime-flash
LJ_REALTIME_WORKSPACE_ID: 可选的北京地域 Workspace ID
LJ_REALTIME_URL: 可选的完整 WebSocket 地址
LJ_REALTIME_VOICE: longanqian
LJ_REALTIME_VOICE_MAO_PRO: longanqian
LJ_REALTIME_VOICE_CHITOSE: longanlufeng
LJ_REALTIME_HISTORY_TURNS: 6
LJ_REALTIME_CONNECT_TIMEOUT_SECONDS: 15
LJ_ASR_CORRECTION_ENABLED: true
LJ_ASR_GLOSSARY_PATH: config/asr_glossary.yml
LJ_ASR_GLOSSARY_TTL_SECONDS: 60
```

存在 `LJ_REALTIME_WORKSPACE_ID` 时，客户端使用对应的北京地域专属域名；未配置时使用 `dashscope.aliyuncs.com`。`LJ_REALTIME_URL` 的优先级最高，适合联调代理或未来端点变更。

## 协议摘要

- 浏览器发送 JSON 控制事件，以及 16kHz、16bit、单声道 PCM 二进制帧。
- 常规模式每次响应显式使用 `modalities: ["text"]`。
- 数字人模式每次响应显式使用 `modalities: ["audio", "text"]`。
- 数字人角色的音色在上游连接第一次`session.update`中由服务端白名单设置；常规模式的每轮`response.create`仍不携带`voice`字段。
- 服务端向浏览器返回 JSON 状态/字幕事件和 24kHz PCM 二进制帧。
- Agent/RAG 先收集证据，证据作为临时系统消息注入 Qwen；完整回答后立即删除。
- 只有完整回答或本地证据降级文本会写入 PostgreSQL；取消、失败和空白转写不保存半截内容。
- 原始录音只经过浏览器内存、WebSocket 和上游模型，不写入文件或数据库。

## 前端音频

浏览器请求单声道、回声消除、降噪和自动增益，并使用 `AudioWorklet` 降采样后按约 100ms 分片上传。工作线程同时计算输入 RMS、峰值和削波比例；连续严重削波会要求重录，低音量只提示而不阻断。松开按钮后继续采集 300ms，以保护句尾辅音和景区名称。

输出 PCM 通过 `AudioContext` 队列播放，输出 RMS 用于驱动当前Live2D模型声明的口型参数；输入音量和输出音量使用不同状态。数字人舞台只依赖稳定的角色、状态、音量和语义表情接口，后续替换模型或升级3D渲染器无需修改音频链路。

数字人专属代码统一位于 `frontend/src/features/digital-human/`，业务组件只通过该目录的 `index.js` 使用舞台、语音控件和音频能力。共享的 `useRealtimeChat.js` 与 `realtimeProtocol.js` 继续服务常规和数字人两种模式。Worklet 的规范地址为 `/digital-human/pcm-capture-worklet.js`，旧 `/pcm-capture-worklet.js` 地址暂时保持兼容。

## Live2D角色

- `mao_pro`：兼容角色ID，当前显示Haru Greeter女导游，使用`longanqian`，表达亲切自然；原Mao Pro资源保留但运行时不加载。
- `chitose`：男导游，使用`longanlufeng`，表达沉稳清晰。

角色选择保存在浏览器`lingjing_digital_human_avatar`，不写入 PostgreSQL。浏览器只发送角色ID，音色和表达提示由后端白名单决定。收到`avatar.changed`前，数字人输入会保持禁用；切换角色会取消当前录音、生成和播放，但不会调用模型或清空历史。

## 景区词典与转写纠错

`config/asr_glossary.yml` 用于维护景区标准名称、常见误写、可选拼音和权重。运行时还会合并已发布景区名称、标签和知识文档标题；数据库词条缓存 60 秒，YAML 修改后自动重载，人工词条优先。

语音转写完成后先执行人工别名和拼音候选匹配，再复用同一次 `qwen3.7-plus` 问题扩写调用做上下文消歧。高置信度自动纠正，中置信度自动纠正并显示标记，低置信度发送 `user.transcript.confirmation_required`，由浏览器通过 `transcript.confirm` 返回候选或编辑文本。确认前不会创建新会话、运行 Agent 或写入历史；PostgreSQL 只保存最终确认文本。

纠正日志只包含 `turn_id`、置信度等级、是否纠正和命中词数量，不包含原始转写、完整问题、PCM 或密钥。

## 回答契约与路线 V2

每轮 Agent/RAG 完成证据收集后，会根据当前模式写入独立回答契约：常规问答先给结论、3—5个证据要点和建议，证据充分时目标约300—600字；数字人问答只朗读3—6句摘要。常规短回答在证据可靠时由本地后处理补充最多3条去重资料要点，不增加模型调用。

高德路线只采用第一推荐路线，并统一生成 `schema_version: 2` 摘要。摘要包含起终点、方式、距离、耗时、原始步骤总数、8—12条关键步骤，以及经 RDP 简化且最多500点的完整地图轨迹。API 的 `data.route_summary` 是权威结果，兼容字段 `data.route` 不再包含高分辨率原始路线对象，Redis 使用 `amap:route:v2:*` 避免复用旧缓存。

常规路线回答完成后，后端会检查起点、终点、方式、距离和耗时；如果模型遗漏任一字段，就在同一条文本流中追加由 V2 摘要生成的完整路线块，并将合并后的答案写入 PostgreSQL。数字人模式不追加与语音不一致的长字幕，完整轨迹和关键步骤由路线面板展示。路线工具失败时只返回具体错误，不使用知识库内容猜测实时路线。

## 降级行为

上游断线会自动重连一次并重新注入最近 6 轮历史。仍失败时，后端使用当前 Agent 证据生成本地抽取式文本；数字人模式只显示文本和语音不可用提示，不切换到其他最终回答模型。麦克风不可用时仍保留数字人舞台和文字输入。
