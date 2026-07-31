# 数字人实时二维地图与虚拟定位随行讲解 Implementation Plan

当前时间：2026-07-31 10:19（Asia/Shanghai）

> **For agentic workers:** 建议按任务逐项执行，每个任务先写失败测试，再实现最小代码并进行两阶段审查。不要在同一提交中混入当前工作区已有的 Live2D、角色资源或部署文档改动。

**Goal:** 在 `/visitor/guide` 数字人模式中加入可稳定比赛演示的二维实时地图、经典路线虚拟定位、真实 GPS 切换、六景点自动晓晓讲解以及结构化 AI 路线接管。

**Architecture:** 新建低耦合 `guided-tour` 前端功能模块，由统一位置源、路线模拟器、围栏、讲解器和导览状态机组成；高德 2D 与本地 SVG 共享位置和路线契约。`GuideView` 负责协调现有实时问答与自动讲解优先级，`DigitalHumanStage` 只组合数字人、地图和回答面板。后端只新增经典路线目录与白名单晓晓在线合成接口，不改变现有问答或 WebSocket 协议。

**Tech Stack:** Vue 3、Vite、原生 Composition API、Node test runner、GSAP（仅沿用已有能力）、高德 JS API 2.0、FastAPI、httpx、Azure Speech REST、pytest。

## 全局约束

- 保留当前未提交的 Live2D、Haru 语义动作、实时音频和部署改动，不覆盖或回滚用户代码。
- 禁止引入新的前端 UI、地图或动画依赖。
- 禁止恢复已放弃的沉浸式地图或伪 3D 逻辑。
- 不改现有 WebSocket 事件、会话数据和问答响应结构。
- 不保存真实 GPS、虚拟轨迹或游客原始音频。
- 单个新增代码文件控制在 800 行以内；定位、围栏、模拟、音频和地图职责分离。
- 六个核心讲解词和音频必须人工审核；在线接口只接受白名单 `stop_id` 或已发布 `attraction_id`，不得开放任意文本合成。
- 实现前先确认当前 Live2D 工作已处于可安全叠加的基线；若仍在修改同一文件，只做最小局部补丁并逐个检查差异。

---

### Task 1：建立导览数据契约与地理纯函数

**Files:**

- Create: `frontend/src/features/guided-tour/lib/geo.js`
- Create: `frontend/src/features/guided-tour/lib/tourRoute.js`
- Create: `frontend/tests/guided-tour-geo.test.js`
- Create: `frontend/tests/guided-tour-route.test.js`

**Interfaces:**

- `parseTourPoint(value) -> { longitude, latitude } | null`
- `distanceMeters(a, b) -> number`
- `buildRouteMetrics(polyline) -> { points, segments, totalDistance }`
- `interpolateRoutePosition(metrics, distance) -> Position`
- `normalizeTourRoute(routeSummary) -> ExecutableTourRoute | null`

- [ ] **Step 1: 写地理和路线契约失败测试**
  - 覆盖字符串/数组坐标、非法值、相同点、跨段累计距离和首尾钳制。
  - 覆盖 V2 路线摘要、旧版 metadata、少于两个坐标点和相邻重复点。
- [ ] **Step 2: 运行 `npm test -- --test-name-pattern="guided tour"`，确认因模块不存在而失败**
- [ ] **Step 3: 实现最小 Haversine、累计距离和按距离插值逻辑**
  - 注释同时说明算法作用和选择按距离而非按点索引的原因。
- [ ] **Step 4: 实现结构化路线规范化，复用 `resolveRouteSummary()` 而不是复制来源判断**
- [ ] **Step 5: 运行新增 Node 测试并检查边界值**

### Task 2：建立经典路线目录与后端只读接口

**Files:**

- Create: `config/guided_tour.json`
- Create: `src/lingjing_ai/guided_tour/__init__.py`
- Create: `src/lingjing_ai/guided_tour/catalog.py`
- Create: `src/lingjing_ai/api/guided_tour_routes.py`
- Create: `tests/test_guided_tour_catalog.py`
- Create: `tests/test_guided_tour_api.py`
- Modify: `src/lingjing_ai/api/app.py`
- Modify: `project_structure.md`

**Interfaces:**

- `GuidedTourCatalog.get_classic_route() -> dict`
- `GuidedTourCatalog.get_stop(stop_id) -> dict | None`
- `GET /api/visitor/guided-tour/classic`

- [ ] **Step 1: 写目录验证失败测试**
  - 要求 `schema_version`、稳定 route ID、至少两个路线点、六个唯一 stop、有限坐标、35 米半径、3000ms 驻留和安全本地音频 URL。
  - 要求 stop 顺序严格为九龙灌浴、天下第一掌、祥符禅寺、灵山大佛、灵山梵宫、五印坛城。
- [ ] **Step 2: 写游客 API 失败测试**
  - 返回公开路线配置，不包含文件系统路径、密钥或内部合成配置。
- [ ] **Step 3: 运行 `python -m pytest tests/test_guided_tour_catalog.py tests/test_guided_tour_api.py -q`，确认失败原因正确**
- [ ] **Step 4: 创建版本化 JSON 和只读目录服务**
  - 使用经核验的六景点坐标和本地预编排折线。
  - 先写每处约 20–35 秒固定讲解词；内容审核通过后才能进入下一音频任务。
- [ ] **Step 5: 注册独立 FastAPI router，不修改现有地图和实时路由**
- [ ] **Step 6: 运行目录与 API 测试，检查应用首次启动和配置缺失错误信息**

### Task 3：实现可测试的路线模拟器

**Files:**

- Create: `frontend/src/features/guided-tour/composables/useRouteSimulation.js`
- Create: `frontend/tests/guided-tour-simulation.test.js`

**Interfaces:**

- Inputs: executable route、speed multiplier、clock adapter。
- Outputs: `position`、`progress`、`status`、`speedMultiplier`。
- Actions: `start()`、`pause(reason)`、`resume()`、`setSpeed(1 | 2)`、`reset()`、`replaceRoute(route)`、`dispose()`。

- [ ] **Step 1: 写确定性虚拟时钟测试**
  - 覆盖开始、暂停不前进、恢复、1×/2×、终点完成、重置和换线归零。
  - 覆盖后台大时间差不补跑，避免瞬间穿过多个围栏。
- [ ] **Step 2: 运行新增测试，确认组合式函数尚不存在**
- [ ] **Step 3: 使用注入时钟和 `requestAnimationFrame` 适配器实现模拟器**
- [ ] **Step 4: 确保 dispose 后不再产生位置事件并运行测试**

### Task 4：实现统一演示定位与真实 GPS 源

**Files:**

- Create: `frontend/src/features/guided-tour/composables/useLocationProvider.js`
- Create: `frontend/tests/guided-tour-location.test.js`

**Interfaces:**

- `mode: "simulation" | "gps"`
- `position: Position | null`
- `gpsStatus: "idle" | "requesting" | "active" | "low_accuracy" | "denied" | "unavailable"`
- `useSimulation()`、`requestGps()`、`stopGps()`、`dispose()`。

- [ ] **Step 1: 用伪 geolocation 写失败测试**
  - 默认不得请求浏览器权限。
  - 显式切换才调用 `watchPosition()`。
  - GPS 回调和模拟器输出统一结构。
  - 权限拒绝后恢复演示定位，`clearWatch()` 只调用一次。
  - 低精度或无效坐标不进入围栏有效位置流。
- [ ] **Step 2: 运行测试并确认失败**
- [ ] **Step 3: 实现位置规范化、精度状态与来源切换**
- [ ] **Step 4: 运行测试并确认真实坐标没有持久化调用**

### Task 5：实现 35 米、3 秒、单轮一次的抵达围栏

**Files:**

- Create: `frontend/src/features/guided-tour/composables/useArrivalGeofence.js`
- Create: `frontend/tests/guided-tour-geofence.test.js`

**Interfaces:**

- Inputs: position、ordered stops、clock。
- Outputs: `nearestStop`、`distance`、`dwellProgress`、`triggeredStop`、`triggeredIds`。
- Actions: `update(position, now)`、`markHandled(stopId)`、`reset()`。

- [ ] **Step 1: 写 34.9m、35m、35.1m 边界和连续时间失败测试**
- [ ] **Step 2: 增加 2.9 秒不触发、3 秒触发、中途离开清零、重复进入不重播测试**
- [ ] **Step 3: 增加重叠围栏按路线顺序和距离决策测试**
- [ ] **Step 4: 实现纯逻辑围栏，不在模块内启动计时器**
  - 使用位置帧时间累计，因为集中状态机更容易暂停和测试。
- [ ] **Step 5: 运行新增测试并确认通过**

### Task 6：实现白名单晓晓在线合成与预生成工具

**Files:**

- Create: `src/lingjing_ai/guided_tour/speech.py`
- Create: `src/lingjing_ai/api/guided_tour_speech_routes.py`
- Create: `tools/generate_guided_tour_audio.py`
- Create: `tests/test_guided_tour_speech.py`
- Modify: `src/lingjing_ai/config/settings.py`
- Modify: `src/lingjing_ai/api/app.py`
- Modify: `docs/项目部署运行配置说明书.md`
- Modify: `app.env`

**Interfaces:**

- Settings: `AZURE_SPEECH_KEY`、`AZURE_SPEECH_REGION`、`GUIDED_TOUR_TTS_ENABLED`。
- Fixed voice: `zh-CN-XiaoxiaoNeural`。
- `POST /api/visitor/guided-tour/narrations/stops/{stop_id}/synthesize -> audio/mpeg`
- `POST /api/visitor/guided-tour/narrations/attractions/{attraction_id}/synthesize -> audio/mpeg`
- `python tools/generate_guided_tour_audio.py --output frontend/public/digital-human/narration/xiaoxiao`

- [ ] **Step 1: 写配置和白名单失败测试**
  - 未配置时返回明确的 `503`，未知 stop、未发布 attraction 或缺少公开摘要时返回 `404`。
  - 请求体不能提交任意文本或覆盖 voice。
  - 上游请求只使用目录中已审核文本或已发布景点公开摘要，并使用固定音色。
- [ ] **Step 2: 写伪 HTTP 上游成功、超时、非音频响应和凭据脱敏测试**
- [ ] **Step 3: 运行 Python 测试并确认失败**
- [ ] **Step 4: 使用现有 HTTP 客户端能力实现 Azure Speech REST 适配器**
  - 不记录 key、完整 SSML 或游客信息。
  - 设置短超时和有限重试，避免阻塞导览。
- [ ] **Step 5: 注入 `AttractionStore`，注册两类白名单合成接口并实现预生成脚本**
- [ ] **Step 6: 人工审核六段讲解词后执行预生成，逐个试听并确认晓晓音色、语速、停顿和音量一致**
- [ ] **Step 7: 将六个获批音频逐个加入 `frontend/public/digital-human/narration/xiaoxiao/`**
  - 每次只处理明确文件，遵守项目禁止批量删除资源的要求。
- [ ] **Step 8: 运行语音测试，并验证凭据缺失不影响应用启动**

### Task 7：实现本地优先的景点讲解播放器

**Files:**

- Create: `frontend/src/features/guided-tour/composables/useScenicNarration.js`
- Create: `frontend/src/features/guided-tour/lib/narrationPolicy.js`
- Create: `frontend/tests/guided-tour-narration.test.js`

**Interfaces:**

- Inputs: stop、audio factory、fetch adapter、clock。
- Outputs: `text`、`title`、`state`、`audioLevel`、`requiresManualPlay`、`source`。
- Actions: `prepare()`、`play(stop)`、`playManually()`、`stop(reason)`、`dispose()`。

- [ ] **Step 1: 写三级优先级失败测试**
  - 本地成功不请求在线接口。
  - 本地 404 后先保留文本，再请求在线合成。
  - 在线失败后进入纯文字状态并正常完成。
- [ ] **Step 2: 写播放拦截、结束、错误、停止、对象 URL 释放和音频电平清零测试**
- [ ] **Step 3: 运行测试并确认失败**
- [ ] **Step 4: 实现 HTMLAudio/Web Audio 分析器播放链路**
  - RMS 输出复用 Live2D 既有 `audioLevel` 口型契约。
- [ ] **Step 5: 实现手动播放恢复和 dispose，运行测试**

### Task 8：实现高德 2D 随行地图与本地 SVG 降级

**Files:**

- Create: `frontend/src/features/guided-tour/components/DigitalHumanTourMap.vue`
- Create: `frontend/src/features/guided-tour/components/GuidedTourFallbackMap.vue`
- Create: `frontend/src/features/guided-tour/components/TourMapControls.vue`
- Create: `frontend/src/features/guided-tour/composables/useGuidedTourMap.js`
- Create: `frontend/src/features/guided-tour/lib/fallbackProjection.js`
- Create: `frontend/tests/guided-tour-map.test.js`
- Create: `frontend/tests/guided-tour-fallback-map.test.js`

**Interfaces:**

- Map inputs: route、previewRoute、stops、position、targetStop、dwellProgress、status。
- Map actions: `initialize()`、`renderRoute()`、`previewRoute()`、`updatePosition()`、`focusStop()`、`resumeFollow()`、`resize()`、`destroy()`。
- Control emits: `start`、`pause`、`resume`、`speed-change`、`reset`、`location-mode-change`、`accept-preview-route`。

- [ ] **Step 1: 写独立地图实例和资源释放失败测试**
  - 高德脚本 Promise 可共享，但地图、标记和折线实例必须独立。
  - 固定 `viewMode: "2D"`，不得出现 pitch、rotation 或伪 3D 容器。
- [ ] **Step 2: 写经典路线、AI 预览、游客光点、聚焦和恢复跟随测试**
- [ ] **Step 3: 写配置缺失与脚本失败转入 SVG 的测试**
- [ ] **Step 4: 实现经纬度边界到 SVG 百分比投影和降级路线动画**
- [ ] **Step 5: 实现高德适配器，复用 `amapLoader.js` 而不修改独立 MapView 的行为**
- [ ] **Step 6: 实现可访问控制器和 reduced-motion 样式，运行测试**

### Task 9：实现随行导览状态机和问答抢占策略

**Files:**

- Create: `frontend/src/features/guided-tour/composables/useGuidedTour.js`
- Create: `frontend/src/features/guided-tour/lib/tourState.js`
- Create: `frontend/tests/guided-tour-state.test.js`
- Create: `frontend/tests/guided-tour-orchestrator.test.js`
- Modify: `frontend/src/features/digital-human/index.js`

**Interfaces:**

- Outputs: `status`、`displayAnswer`、`displayState`、`displayAudioLevel`、`route`、`previewRoute`、`position`、`activeStop`、`controls`。
- Actions: `load()`、`start()`、`pause()`、`resume()`、`reset()`、`setSpeed()`、`setLocationMode()`、`setAiRoutePreview()`、`acceptAiRoute()`、`interruptForUser()`、`activate()`、`deactivate()`、`dispose()`。

- [ ] **Step 1: 写完整状态序列失败测试**
  - `idle → moving → approaching → dwelling → narrating → post_narration → moving → completed`。
- [ ] **Step 2: 写抵达后自动暂停、音频完成后 1.5 秒恢复和单景点单次触发测试**
- [ ] **Step 3: 写用户发送文字/开始录音抢占自动讲解测试**
  - 停止景点音频，暂停路线，AI 状态优先，不自动恢复。
- [ ] **Step 4: 写回答优先级测试**
  - 讲解结束后保留；下一 AI 回答或下一景点讲解覆盖。
- [ ] **Step 5: 实现集中协调器并从数字人 feature barrel 导出**
- [ ] **Step 6: 运行状态机和协调测试**

### Task 10：接入现有实时问答来源和 AI 路线预览

**Files:**

- Modify: `frontend/src/composables/useRealtimeChat.js`
- Modify: `frontend/src/views/GuideView.vue`
- Modify: `frontend/src/components/ChatMain.vue`
- Create: `frontend/tests/guided-tour-chat-integration.test.js`
- Modify: `tests/test_frontend.py`

**Interfaces:**

- `useRealtimeChat.latestRouteSummary: ComputedRef<RouteSummary | null>`
- `ChatMain` 新增导览展示 props 与控制 events，但不把定位逻辑放入共享聊天层。
- `GuideView` 包装 `ask`、`startRecording`、路由失活和页面恢复，以协调导览抢占。

- [ ] **Step 1: 写最新成功路线摘要失败测试**
  - 普通来源和失败路线不产生预览；V2 与旧版成功路线产生预览。
- [ ] **Step 2: 写 AI 路线触发点匹配失败测试**
  - 六个核心点使用审核讲解；其他已发布且有坐标、摘要的景点使用公开摘要；草稿、无坐标和无摘要景点被排除。
- [ ] **Step 3: 写 AI 流式回答覆盖景点讲解、用户提问暂停路线和音频不重叠测试**
- [ ] **Step 4: 运行 Node 与 Python 静态契约测试并确认失败**
- [ ] **Step 5: 在 `useRealtimeChat` 暴露只读路线摘要，不改事件协议**
- [ ] **Step 6: 数字人模式按需加载已发布景点并构建路线附近触发点，不阻塞经典路线首屏**
- [ ] **Step 7: 在 `GuideView` 建立协调包装，保持普通文字模式原调用路径**
- [ ] **Step 8: 运行集成测试并确认取消、重试和历史会话行为不变**

### Task 11：重构数字人舞台为“左人、右上地图、右下回答”

**Files:**

- Modify: `frontend/src/features/digital-human/components/DigitalHumanStage.vue`
- Modify: `frontend/src/features/digital-human/components/DigitalHumanAnswerPanel.vue`
- Modify: `frontend/src/components/ChatMain.vue`
- Modify: `frontend/src/guide.css`
- Modify: `tests/test_frontend.py`

**Interfaces:**

- `DigitalHumanStage` 接收导览地图状态和 actions，继续接收当前 avatar、state 与 audioLevel。
- `DigitalHumanAnswerPanel` 支持 `contentKind: "assistant" | "narration"` 和可选路线接管按钮。

- [ ] **Step 1: 更新静态契约测试并确认旧两栏结构失败**
- [ ] **Step 2: 保留 `.avatar-visual`，新增 `.digital-human-companion` 右栏**
  - 右栏使用地图在上、回答在下的两行网格。
  - 不改变 Live2D renderer、角色切换、语义动作和实时语音 props。
- [ ] **Step 3: 添加 AI 预览状态和“沿此路线演示”按钮**
- [ ] **Step 4: 添加桌面 1180px 舞台、900px 以下纵排和 390px 窄屏样式**
- [ ] **Step 5: 检查输入框、顶部角色栏和底部导航不被遮挡，运行前端测试**

### Task 12：生命周期、隐私和异常回归

**Files:**

- Modify: `frontend/src/views/GuideView.vue`
- Modify: `frontend/src/features/guided-tour/composables/useGuidedTour.js`
- Modify: `frontend/tests/guided-tour-orchestrator.test.js`
- Modify: `tests/test_frontend.py`

- [ ] **Step 1: 写 `onActivated`、`onDeactivated`、切换模式和卸载失败测试**
- [ ] **Step 2: 确保离场暂停模拟、停止讲解、清除 GPS watch、延迟计时和地图资源**
- [ ] **Step 3: 确保重新激活保留进度但要求用户继续，不自动播放声音**
- [ ] **Step 4: 静态检查真实坐标不进入 localStorage、会话 API、日志或分析请求**
- [ ] **Step 5: 验证地图、GPS、音频和在线合成四类失败互不扩散**

### Task 13：完整验证、视觉验收与文档收尾

**Files:**

- Modify: `docs/qwen_audio_realtime.md`
- Modify: `docs/项目部署运行配置说明书.md`
- Modify: `docs/比赛7分钟演示视频稿.md`
- Modify: `project_structure.md`
- Modify: `daily-modify/2026-07-31.md`

- [ ] **Step 1: 运行前端单元测试**
  - `cd frontend`
  - `npm test`
- [ ] **Step 2: 运行前端构建**
  - `npm run build`
- [ ] **Step 3: 运行导览相关 Python 测试**
  - `python -m pytest tests/test_guided_tour_catalog.py tests/test_guided_tour_api.py tests/test_guided_tour_speech.py tests/test_frontend.py -q`
- [ ] **Step 4: 运行完整 Python 测试**
  - `python -m pytest -q`
- [ ] **Step 5: 在 `1520×856` 完整播放经典路线**
  - 验证六处顺序、35 米/3 秒、暂停讲解、口型、1.5 秒恢复和单轮一次。
- [ ] **Step 6: 在 `768×1024`、`390×844` 检查纵排、滚动、输入框和底部导航**
- [ ] **Step 7: 验证 AI 路线预览、接管、重置和无效路线拒绝**
- [ ] **Step 8: 分别断开地图、本地音频、在线合成和 GPS，验证降级**
- [ ] **Step 9: 连续重置并运行 5 次，检查地图实例、监听器、GPS watch、计时器、音频对象和 Blob URL 不累积**
- [ ] **Step 10: 最后单独进行一次受控真实 GPS、真实高德和在线晓晓合成冒烟验证**
- [ ] **Step 11: 更新部署说明、比赛演示脚本、项目结构和当日修改记录**

## 实施完成条件

- 所有新增 Node 和 Python 测试通过，`npm run build` 成功。
- 默认演示定位无需权限或外部 AI 即可完成六景点路线。
- 高德不可用时本地 SVG 地图仍能展示路线、位置和抵达进度。
- 本地晓晓音频驱动数字人口型；缺失时按在线合成、纯文字顺序降级。
- 用户问答与自动讲解没有音频重叠，普通文字模式和独立地图页无回归。
- 真实 GPS 不持久化，所有地图、定位、计时器和音频资源均正确释放。
