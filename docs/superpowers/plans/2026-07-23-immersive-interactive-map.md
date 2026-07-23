# Immersive Interactive Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `/visitor/map` 建成可在比赛大屏稳定演示的 78 秒沉浸式巡游与自由探索智慧地图，并在高德、路线、AI 或音频失败时保持连续可用。

**Architecture:** 保留现有路由与后端接口，以 `useTourDirector` 作为唯一时间轴和模式状态源。在线高德场景与本地摄影场景实现统一场景适配器，Vue 组件仅订阅导演状态并发出用户意图；纯逻辑使用 Node 原生测试，Vue/资源契约使用现有 Python 静态测试。

**Tech Stack:** Vue 3、Vue Router 4、Vite 5、GSAP 3、高德 JS API 2.0、Loca 2.0、Node `node:test`、Pytest。

## Global Constraints

- 执行前使用 `superpowers:using-git-worktrees` 创建隔离工作区；当前 `main` 有用户未提交修改，禁止在原工作区直接实施。
- 当前实施范围只包含设计规格的第一阶段；不加入定位签到、印章、AR、实时客流或新后端协议。
- 不缓存或打包高德地图瓦片；本地降级只使用项目自有图片、SVG、CSS 和本地音频。
- 默认巡游不能调用真实 AI、实时 TTS 或付费路线服务。
- 不修改现有 AI、实时语音、WebSocket、会话或地图后端协议。
- 高德初始化硬超时为 5 秒；在线/离线溶解为 450–500ms。
- 首屏关键本地图片、音频和矢量资源合计不超过 8MB。
- 目标视口为 1920×1080、1520×856、1440×900；主要镜头动画目标 60 FPS，不得持续低于 45 FPS。
- 所有语音必须有字幕；`prefers-reduced-motion` 下禁用飞行、旋转和脉冲。
- 单个实现文件原则上不超过 800 行，新增模块必须保持单一职责。
- 禁止批量删除文件或目录；只处理本计划明确列出的文件。
- 本地讲解音频必须经过用户认可后进入仓库；不得未经授权调用付费 TTS。

## File Structure

```text
frontend/src/features/immersive-map/
├── index.js                              对外导出稳定接口
├── data/classicTour.js                   78 秒经典巡游定义与字幕
├── data/personas.js                      三种画像和精选路线
├── lib/tourDefinition.js                 巡游校验与地点解析
├── lib/tourDirector.js                   纯时间轴状态机
├── lib/sceneAdapter.js                   场景适配器契约与降级协调
├── lib/personaRoutes.js                  画像路线预览、确认与撤销
├── lib/amapLoader.js                     高德与 Loca 共享加载器
├── composables/useTourDirector.js        Vue 响应式包装
├── composables/useAmapScene.js           在线地图适配器
├── composables/useOfflineScene.js        离线场景适配器
├── composables/useLocalNarration.js      本地音频与字幕同步
├── composables/usePersonaRouteAdvisor.js AI 理由请求与本地降级
├── components/ImmersiveMapStage.vue      在线/离线双场景与溶解
├── components/OfflineScenicStage.vue     本地摄影与 SVG 场景
├── components/LingjingOrb.vue            光球与 AI 入口
├── components/TourTimeline.vue           时间轴与键盘控制
├── components/ScenicStoryCard.vue        短时讲解卡
├── components/PersonaRouteSwitcher.vue   画像预览、应用与撤销
└── immersive-map.css                     大屏、降级和响应式样式

frontend/public/audio/immersive-map/
└── classic-tour.mp3                      用户认可的本地讲解音轨

frontend/tests/
├── immersive-map.test.js                 领域、导演与画像测试
└── amap-loader.test.js                    共享加载器测试
```

现有文件职责：

- `frontend/src/views/MapView.vue`：薄组合层，保留地点、详情和路线业务。
- `frontend/src/composables/useInteractiveMap.js`：改为兼容导出，避免旧引用立刻失效。
- `frontend/src/composables/useRouteMap.js`：改用共享高德加载器。
- `frontend/src/main.js`：引入沉浸式地图样式。
- `tests/test_frontend.py`：新增 Vue 模板、资源和加载顺序静态契约。

---

### Task 1: 巡游数据契约与稳定地点解析

**Files:**
- Create: `frontend/src/features/immersive-map/data/classicTour.js`
- Create: `frontend/src/features/immersive-map/data/personas.js`
- Create: `frontend/src/features/immersive-map/lib/tourDefinition.js`
- Create: `frontend/src/features/immersive-map/index.js`
- Create: `frontend/tests/immersive-map.test.js`

**Interfaces:**
- Consumes: `places: Array<{ place_id, kind, name, longitude, latitude }>` from `MapView`.
- Produces: `CLASSIC_TOUR`, `PERSONAS`, `validateTourDefinition(definition)`, `resolveTourPlaces(definition, places)`.

- [ ] **Step 1: Write the failing contract tests**

```js
import test from "node:test";
import assert from "node:assert/strict";
import { CLASSIC_TOUR, PERSONAS, resolveTourPlaces, validateTourDefinition } from "../src/features/immersive-map/index.js";

test("classic tour is a valid 78 second four-stop definition", () => {
  assert.equal(validateTourDefinition(CLASSIC_TOUR), true);
  assert.equal(CLASSIC_TOUR.durationMs, 78_000);
  assert.deepEqual(CLASSIC_TOUR.stops.map((stop) => stop.placeRef.name), [
    "灵山大照壁", "九龙灌浴", "灵山大佛", "灵山梵宫",
  ]);
});

test("tour references resolve against runtime database ids", () => {
  const places = CLASSIC_TOUR.stops.map((stop, index) => ({
    place_id: `runtime-${index}`,
    kind: stop.placeRef.kind,
    name: stop.placeRef.name,
    longitude: 120 + index / 100,
    latitude: 31 + index / 100,
  }));
  const resolved = resolveTourPlaces(CLASSIC_TOUR, places);
  assert.deepEqual(resolved.stops.map((stop) => stop.resolvedPlaceId), [
    "runtime-0", "runtime-1", "runtime-2", "runtime-3",
  ]);
});

test("persona definitions provide instant local reasons and curated routes", () => {
  assert.deepEqual(PERSONAS.map((persona) => persona.id), ["senior", "family", "photography"]);
  assert.ok(PERSONAS.every((persona) => persona.curatedPlaceRefs.length >= 3));
  assert.ok(PERSONAS.every((persona) => persona.localReasons.length === 3));
});
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `features/immersive-map/index.js`.

- [ ] **Step 3: Implement validation and runtime resolution**

```js
export function validateTourDefinition(definition) {
  if (!definition?.id || definition.durationMs !== 78_000 || !Array.isArray(definition.stops)) {
    throw new Error("经典巡游定义不完整");
  }
  let previousEnd = 0;
  for (const stop of definition.stops) {
    if (!stop.id || !stop.placeRef?.kind || !stop.placeRef?.name) throw new Error("巡游站点引用不完整");
    if (stop.startMs < previousEnd || stop.durationMs <= 0) throw new Error("巡游站点时间重叠");
    previousEnd = stop.startMs + stop.durationMs;
  }
  if (previousEnd > definition.durationMs) throw new Error("巡游站点超出总时长");
  return true;
}

export function resolveTourPlaces(definition, places) {
  validateTourDefinition(definition);
  const byRef = new Map(places.map((place) => [`${place.kind}:${place.name}`, place]));
  const stops = definition.stops.map((stop) => {
    const place = byRef.get(`${stop.placeRef.kind}:${stop.placeRef.name}`);
    if (!place) throw new Error(`经典巡游缺少核心地点：${stop.placeRef.name}`);
    return { ...stop, resolvedPlaceId: place.place_id, place };
  });
  return { ...definition, stops };
}
```

In `classicTour.js`, define stop windows exactly as `6_000/11_000`, `17_000/15_000`, `32_000/18_000`, and `50_000/16_000`; include `camera.amap`, `camera.offline`, `routeEffect`, and `storyCard` for every stop. Define caption cues for 06–17, 17–32, 32–50, 50–66, and 66–78 seconds.

In `personas.js`, define these curated refs:

```js
export const PERSONAS = [
  { id: "senior", label: "老人舒缓线", curatedPlaceRefs: ["灵山大照壁", "九龙灌浴", "灵山梵宫"], localReasons: ["减少连续步行", "预留休息弹性", "室内外体验交替"] },
  { id: "family", label: "亲子趣味线", curatedPlaceRefs: ["九龙灌浴", "灵山大佛", "吉祥食集", "灵山梵宫"], localReasons: ["动态水景优先", "核心文化故事", "用餐节点可弹性调整"] },
  { id: "photography", label: "摄影光影线", curatedPlaceRefs: ["灵山大照壁", "灵山大佛", "灵山梵宫", "五印坛城"], localReasons: ["开阔取景起步", "地标与山景结合", "建筑光影顺序清晰"] },
].map((persona) => ({ ...persona, curatedPlaceRefs: persona.curatedPlaceRefs.map((name) => ({ kind: name === "吉祥食集" ? "food" : "attraction", name })) }));
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: 3 tests PASS.

- [ ] **Step 5: Commit the domain layer**

```powershell
git add frontend/src/features/immersive-map frontend/tests/immersive-map.test.js
git commit -m "feat: add immersive map tour definitions"
```

---

### Task 2: 单一时钟巡游导演

**Files:**
- Create: `frontend/src/features/immersive-map/lib/tourDirector.js`
- Create: `frontend/src/features/immersive-map/composables/useTourDirector.js`
- Modify: `frontend/src/features/immersive-map/index.js`
- Modify: `frontend/tests/immersive-map.test.js`

**Interfaces:**
- Consumes: resolved `TourDefinition`, injected `now`, `requestFrame`, and `cancelFrame`.
- Produces: `createTourDirector(options)` and `useTourDirector(definition)` with `state`, `start`, `pause`, `resume`, `skip`, `requestTakeover`, `confirmTakeover`, `restart`, `switchScene`, `destroy`.

- [ ] **Step 1: Add failing fake-clock tests**

```js
test("director pauses without accumulating elapsed time and hands off at 78 seconds", () => {
  let now = 0;
  let frame = null;
  const director = createTourDirector({
    definition: CLASSIC_TOUR,
    now: () => now,
    requestFrame: (callback) => { frame = callback; return 1; },
    cancelFrame: () => { frame = null; },
  });
  director.start();
  now = 32_000; frame(now);
  assert.equal(director.snapshot().activeStopId, "buddha");
  director.pause();
  now = 50_000;
  assert.equal(director.snapshot().elapsedMs, 32_000);
  director.resume();
  now = 96_000; frame(now);
  assert.equal(director.snapshot().mode, "exploring");
  assert.equal(director.snapshot().elapsedMs, 78_000);
});

test("scene switching does not replace the touring mode", () => {
  const director = createTourDirector({ definition: CLASSIC_TOUR, now: () => 0, requestFrame: () => 1, cancelFrame: () => {} });
  director.start();
  director.switchScene("offline");
  assert.equal(director.snapshot().mode, "touring");
  assert.equal(director.snapshot().sceneKind, "offline");
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: FAIL because `createTourDirector` is not exported.

- [ ] **Step 3: Implement the director and Vue wrapper**

Implement the pure director with this state and transition core:

```js
const initialState = () => ({ mode: "idle", elapsedMs: 0, activeStopId: null, sceneKind: "amap", takeoverRequested: false });

export function createTourDirector({ definition, now, requestFrame, cancelFrame, onChange = () => {} }) {
  let state = initialState();
  let startedAt = 0;
  let frameId = null;
  const emit = () => onChange({ ...state });
  const stopFor = (elapsed) => definition.stops.find((stop) => elapsed >= stop.startMs && elapsed < stop.startMs + stop.durationMs);
  const cancel = () => { if (frameId !== null) cancelFrame(frameId); frameId = null; };
  const tick = (timestamp) => {
    if (state.mode !== "touring") return;
    state.elapsedMs = Math.min(definition.durationMs, timestamp - startedAt);
    state.activeStopId = stopFor(state.elapsedMs)?.id || null;
    if (state.elapsedMs >= definition.durationMs) { state.mode = "exploring"; cancel(); emit(); return; }
    emit(); frameId = requestFrame(tick);
  };
  const start = () => { cancel(); state = { ...initialState(), mode: "touring", sceneKind: state.sceneKind }; startedAt = now(); emit(); frameId = requestFrame(tick); };
  const pause = () => { if (state.mode !== "touring") return; cancel(); state.mode = "paused"; emit(); };
  const resume = () => { if (state.mode !== "paused") return; state.mode = "touring"; startedAt = now() - state.elapsedMs; emit(); frameId = requestFrame(tick); };
  const enterExplore = () => { cancel(); state.mode = "exploring"; state.takeoverRequested = false; emit(); };
  return { snapshot: () => ({ ...state }), start, pause, resume, skip: enterExplore, requestTakeover: () => { state.takeoverRequested = true; emit(); }, confirmTakeover: enterExplore, restart: start, switchScene: (sceneKind) => { state.sceneKind = sceneKind; emit(); }, destroy: cancel };
}
```

`useTourDirector` must hold a Vue `ref` snapshot, inject `performance.now`, `requestAnimationFrame`, and `cancelAnimationFrame`, and call `director.destroy()` in `onBeforeUnmount`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: all immersive-map tests PASS.

- [ ] **Step 5: Commit the director**

```powershell
git add frontend/src/features/immersive-map frontend/tests/immersive-map.test.js
git commit -m "feat: add immersive tour director"
```

---

### Task 3: 共享高德加载器与在线场景适配器

**Files:**
- Create: `frontend/src/features/immersive-map/lib/amapLoader.js`
- Create: `frontend/src/features/immersive-map/composables/useAmapScene.js`
- Create: `frontend/tests/amap-loader.test.js`
- Modify: `frontend/src/composables/useInteractiveMap.js`
- Modify: `frontend/src/composables/useRouteMap.js:1-113`
- Modify: `tests/test_frontend.py:640-660`

**Interfaces:**
- Consumes: `/api/tools/map/config`, target element/ref, normalized places, route summaries.
- Produces: `loadAmapRuntime({ includeLoca, timeoutMs, fetchImpl, browser, documentRef })` and `useAmapScene(target)` implementing the scene adapter plus current map methods.

- [ ] **Step 1: Write failing loader tests**

```js
test("loader applies security code before appending AMap and Loca scripts", async () => {
  const order = [];
  const browser = {};
  const documentRef = { head: { appendChild(node) { order.push(browser._AMapSecurityConfig?.securityJsCode ? node.src : "missing-security"); queueMicrotask(node.onload); } }, createElement: () => ({}) };
  const fetchImpl = async () => ({ ok: true, json: async () => ({ enabled: true, js_api_key: "key", security_js_code: "secret" }) });
  await loadAmapRuntime({ includeLoca: true, fetchImpl, browser, documentRef, timeoutMs: 100 });
  assert.equal(order.includes("missing-security"), false);
  assert.equal(browser._AMapSecurityConfig.securityJsCode, "secret");
  assert.equal(order.length, 2);
});

test("loader rejects after the configured timeout", async () => {
  const documentRef = { head: { appendChild() {} }, createElement: () => ({}) };
  const fetchImpl = async () => ({ ok: true, json: async () => ({ enabled: true, js_api_key: "key", security_js_code: "secret" }) });
  await assert.rejects(loadAmapRuntime({ fetchImpl, browser: {}, documentRef, timeoutMs: 5 }), /5 秒内未完成/);
});
```

- [ ] **Step 2: Run loader tests and verify RED**

Run: `cd frontend; node --test tests/amap-loader.test.js`

Expected: FAIL with missing `amapLoader.js`.

- [ ] **Step 3: Implement one shared loader**

```js
let runtimePromise = null;

export async function loadAmapRuntime({ includeLoca = false, timeoutMs = 5000, fetchImpl = fetch, browser = window, documentRef = document } = {}) {
  if (browser.AMap && (!includeLoca || browser.Loca)) return { AMap: browser.AMap, Loca: browser.Loca || null };
  if (runtimePromise) return runtimePromise;
  runtimePromise = (async () => {
    const response = await fetchImpl("/api/tools/map/config");
    const config = await response.json();
    if (!response.ok || !config.enabled) throw new Error(config.message || `HTTP ${response.status}`);
    browser._AMapSecurityConfig = { securityJsCode: config.security_js_code };
    await withTimeout(loadScript(documentRef, `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(config.js_api_key)}`), timeoutMs);
    if (includeLoca) await withTimeout(loadScript(documentRef, `https://webapi.amap.com/loca?v=2.0.0&key=${encodeURIComponent(config.js_api_key)}`), timeoutMs);
    return { AMap: browser.AMap, Loca: browser.Loca || null };
  })().catch((error) => { runtimePromise = null; throw error; });
  return runtimePromise;
}
```

`loadScript` must resolve on `onload`, reject on `onerror`, and `withTimeout` must clear its timer in both success and failure paths. Use the exact timeout error `高德地图未在 5 秒内完成加载` when `timeoutMs === 5000`.

- [ ] **Step 4: Build `useAmapScene` from the current map behavior**

Move current marker, selection, route, resize and destroy logic into `useAmapScene`. Initialize with `viewMode: "3D"`, `pitch: 45`, and `rotation: 0`. Add these methods:

```js
function setCamera(cue, { immediate = false } = {}) {
  if (!map) return;
  const options = { center: cue.center, zoom: cue.zoom, pitch: cue.pitch, rotation: cue.rotation };
  if (immediate || typeof map.setStatus !== "function") map.setZoomAndCenter(cue.zoom, cue.center);
  else map.setStatus(options);
}

function focusPlace(resolvedPlaceId, options = {}) {
  const place = places.find((item) => item.place_id === resolvedPlaceId);
  if (place) setCamera({ center: [place.longitude, place.latitude], zoom: options.zoom || 17, pitch: options.pitch || 52, rotation: options.rotation || 0 });
}
```

When Loca exists, `drawRoute` must create one `Loca.PulseLineLayer` backed by a `Loca.GeoJSONSource`; otherwise draw an `AMap.Polyline` with the same jade-to-gold visual intent. Destroy both Loca container and AMap instance in `destroy()`.

Replace `useInteractiveMap.js` with a compatibility export:

```js
export { useAmapScene as useInteractiveMap } from "../features/immersive-map/composables/useAmapScene.js";
```

Update `useRouteMap.js` to import `loadAmapRuntime` and remove its duplicate loader. Update the static test to inspect `amapLoader.js` for `_AMapSecurityConfig` and both composables for imports from the shared loader.

- [ ] **Step 5: Run targeted tests and build**

Run: `cd frontend; node --test tests/amap-loader.test.js tests/visitor-services.test.js`

Expected: all targeted Node tests PASS.

Run: `python -m pytest tests/test_frontend.py -q`

Expected: frontend contract tests PASS.

- [ ] **Step 6: Commit the online scene**

```powershell
git add frontend/src/features/immersive-map frontend/src/composables/useInteractiveMap.js frontend/src/composables/useRouteMap.js frontend/tests/amap-loader.test.js tests/test_frontend.py
git commit -m "feat: add shared AMap scene runtime"
```

---

### Task 4: 离线场景与不中断降级

**Files:**
- Create: `frontend/src/features/immersive-map/lib/sceneAdapter.js`
- Create: `frontend/src/features/immersive-map/composables/useOfflineScene.js`
- Create: `frontend/src/features/immersive-map/components/OfflineScenicStage.vue`
- Create: `frontend/src/features/immersive-map/components/ImmersiveMapStage.vue`
- Modify: `frontend/src/features/immersive-map/index.js`
- Modify: `frontend/tests/immersive-map.test.js`

**Interfaces:**
- Consumes: director snapshot, resolved tour, online scene adapter, local background `/images/guide-home-background.jpg`.
- Produces: `assertSceneAdapter(adapter)`, `createSceneFailover(options)`, `useOfflineScene()`, and stage events `scene-failed`, `select-place`.

- [ ] **Step 1: Add failing scene contract and failover tests**

```js
test("scene adapter requires every semantic command", () => {
  assert.throws(() => assertSceneAdapter({ initialize() {} }), /drawRoute/);
});

test("failover preserves elapsed time and never auto-recovers during touring", async () => {
  const changes = [];
  const failover = createSceneFailover({ timeoutMs: 5, onSwitch: (kind) => changes.push(kind) });
  const result = await failover.initializeOnline(() => new Promise(() => {}));
  assert.equal(result, "offline");
  assert.deepEqual(changes, ["offline"]);
  failover.reportFailure();
  assert.deepEqual(changes, ["offline"]);
  failover.markOnlineAvailable();
  assert.equal(failover.snapshot().recoveryAvailable, true);
  assert.equal(failover.snapshot().activeKind, "offline");
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: FAIL because scene adapter exports do not exist.

- [ ] **Step 3: Implement the contract and failover coordinator**

```js
const requiredMethods = ["initialize", "setCamera", "drawRoute", "focusPlace", "setActiveStop", "enterExploreMode", "resize", "destroy"];
export function assertSceneAdapter(adapter) {
  for (const method of requiredMethods) if (typeof adapter?.[method] !== "function") throw new Error(`场景适配器缺少 ${method}`);
  return adapter;
}

export function createSceneFailover({ timeoutMs = 5000, onSwitch }) {
  let state = { activeKind: "amap", recoveryAvailable: false };
  const switchToOffline = () => { if (state.activeKind === "offline") return; state.activeKind = "offline"; onSwitch("offline"); };
  const initializeOnline = async (initialize) => {
    try { await Promise.race([initialize(), new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), timeoutMs))]); return "amap"; }
    catch { switchToOffline(); return "offline"; }
  };
  return { initializeOnline, reportFailure: switchToOffline, markOnlineAvailable: () => { state.recoveryAvailable = true; }, restoreOnline: () => { state = { activeKind: "amap", recoveryAvailable: false }; onSwitch("amap"); }, snapshot: () => ({ ...state }) };
}
```

- [ ] **Step 4: Implement the offline adapter and dual scene component**

`useOfflineScene` must hold only visual state:

```js
const state = reactive({ camera: null, route: [], routeProgress: 0, activeStopId: null, exploreMode: false });
const adapter = {
  initialize: async () => true,
  setCamera: (camera) => { state.camera = camera; },
  drawRoute: (route, progress = 1) => { state.route = route; state.routeProgress = progress; },
  focusPlace: (resolvedPlaceId) => { state.activeStopId = resolvedPlaceId; },
  setActiveStop: (stopId) => { state.activeStopId = stopId; },
  enterExploreMode: () => { state.exploreMode = true; },
  resize: () => {},
  destroy: () => { state.route = []; },
};
```

`ImmersiveMapStage.vue` must render both canvases, bind `is-active` to `sceneKind`, and use `aria-hidden` plus `pointer-events` so only one scene is interactive. The local stage uses the existing project-owned guide background and an SVG route; it must not load external images.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: all immersive-map tests PASS.

- [ ] **Step 6: Commit the fallback scene**

```powershell
git add frontend/src/features/immersive-map
git commit -m "feat: add resilient offline map scene"
```

---

### Task 5: 时间轴、光球、讲解卡与本地旁白

**Files:**
- Create: `frontend/src/features/immersive-map/composables/useLocalNarration.js`
- Create: `frontend/src/features/immersive-map/components/LingjingOrb.vue`
- Create: `frontend/src/features/immersive-map/components/TourTimeline.vue`
- Create: `frontend/src/features/immersive-map/components/ScenicStoryCard.vue`
- Create: `frontend/public/audio/immersive-map/classic-tour.mp3`
- Modify: `frontend/tests/immersive-map.test.js`
- Modify: `tests/test_frontend.py`

**Interfaces:**
- Consumes: director state, caption cues, approved local MP3.
- Produces: `useLocalNarration({ audioUrl, captions, elapsedMs, mode })`; component events `pause`, `resume`, `skip`, `request-takeover`, `restart`, `ask-ai`.

- [ ] **Step 1: Add failing narration synchronization tests**

```js
test("caption selection follows elapsed time without audio", () => {
  const captions = [{ startMs: 6000, endMs: 17000, text: "从灵山大照壁起步" }];
  assert.equal(resolveCaption(captions, 5999), "");
  assert.equal(resolveCaption(captions, 6000), "从灵山大照壁起步");
  assert.equal(resolveCaption(captions, 17000), "");
});

test("keyboard shortcut ignores editable targets", () => {
  assert.equal(resolveTourShortcut({ code: "Space", targetTag: "TEXTAREA" }), null);
  assert.equal(resolveTourShortcut({ code: "Space", targetTag: "DIV" }), "toggle-pause");
  assert.equal(resolveTourShortcut({ code: "Escape", targetTag: "DIV" }), "skip");
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: FAIL because narration helpers are not exported.

- [ ] **Step 3: Implement narration and keyboard helpers**

```js
export function resolveCaption(captions, elapsedMs) {
  return captions.find((cue) => elapsedMs >= cue.startMs && elapsedMs < cue.endMs)?.text || "";
}

export function resolveTourShortcut({ code, targetTag }) {
  if (["INPUT", "TEXTAREA", "SELECT"].includes(String(targetTag).toUpperCase())) return null;
  if (code === "Space") return "toggle-pause";
  if (code === "Escape") return "skip";
  return null;
}
```

`useLocalNarration` must create one `Audio` object, set `currentTime = elapsedMs / 1000` when drift exceeds 250ms, pause in `paused`/hidden states, and always expose captions even after `error`. It must remove listeners and clear `src` on unmount.

In `useTourDirector`, listen for `visibilitychange`, call `pause()` only when the current mode is `touring`, and expose `pauseForDeactivation()` for `MapView.onDeactivated`. Remove the document listener during unmount.

- [ ] **Step 4: Prepare the approved local narration asset**

Record or synthesize one approved 96kbps MP3 containing these exact segments with silence matching the timeline:

1. 06–17s：“从灵山大照壁起步，一场山水与文化相遇的旅程由此展开。”
2. 17–32s：“前方是九龙灌浴。水幕与音乐讲述佛祖诞生的故事，也让亲子游客迅速进入旅程。”
3. 32–50s：“镜头抬升，灵山大佛成为整条中轴线的精神核心。请留意山势、台阶与佛像共同形成的庄严尺度。”
4. 50–66s：“最后抵达灵山梵宫，建筑、艺术与室内光影为经典巡游收束出温暖而宁静的尾声。”
5. 66–78s：“经典路线已经完成。现在请选择老人、亲子或摄影路线，让灵境智导为你重新安排下一段旅程。”

Export to `frontend/public/audio/immersive-map/classic-tour.mp3`. Run `ffprobe -v error -show_entries format=duration,bit_rate -of json frontend/public/audio/immersive-map/classic-tour.mp3` and confirm duration is 77–79 seconds and bitrate is at most 96kbps. Do not call an external paid generator without the user's explicit approval.

- [ ] **Step 5: Implement the three UI components**

`TourTimeline` props: `mode`, `elapsedMs`, `durationMs`, `stops`, `reducedMotion`; emit the six control events. `LingjingOrb` props: `state`, `caption`, `interactive`; emit `ask-ai`. `ScenicStoryCard` props: `stop`, `visible`; it must use `aria-live="polite"` and never trap focus.

Add a Python contract test:

```python
def test_immersive_map_tour_controls_and_local_audio_contract():
    root = Path("frontend/src/features/immersive-map")
    timeline = (root / "components/TourTimeline.vue").read_text(encoding="utf-8")
    narration = (root / "composables/useLocalNarration.js").read_text(encoding="utf-8")
    assert 'code === "Space"' in narration
    assert 'code === "Escape"' in narration
    assert 'aria-live="polite"' in (root / "components/ScenicStoryCard.vue").read_text(encoding="utf-8")
    assert "pause" in timeline and "request-takeover" in timeline
    assert Path("frontend/public/audio/immersive-map/classic-tour.mp3").is_file()
```

- [ ] **Step 6: Run targeted tests**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: all immersive-map tests PASS.

Run: `python -m pytest tests/test_frontend.py -q`

Expected: frontend contract tests PASS.

- [ ] **Step 7: Commit the tour UI and approved audio**

```powershell
git add frontend/src/features/immersive-map frontend/public/audio/immersive-map/classic-tour.mp3 frontend/tests/immersive-map.test.js tests/test_frontend.py
git commit -m "feat: add immersive tour controls and narration"
```

---

### Task 6: 画像路线预览、AI 理由与撤销

**Files:**
- Create: `frontend/src/features/immersive-map/lib/personaRoutes.js`
- Create: `frontend/src/features/immersive-map/composables/usePersonaRouteAdvisor.js`
- Create: `frontend/src/features/immersive-map/components/PersonaRouteSwitcher.vue`
- Modify: `frontend/src/features/immersive-map/index.js`
- Modify: `frontend/tests/immersive-map.test.js`

**Interfaces:**
- Consumes: `PERSONAS`, runtime places, `/api/agent/chat` with `persist_history: false`.
- Produces: `createPersonaRouteStore`, `requestPersonaReasons`, and component events `preview`, `apply`, `undo`.

- [ ] **Step 1: Add failing route preview and timeout tests**

```js
test("persona preview does not replace the applied route until confirmation", () => {
  const store = createPersonaRouteStore({ initialRoute: ["classic"] });
  store.preview({ personaId: "family", placeIds: ["a", "b"] });
  assert.deepEqual(store.snapshot().appliedPlaceIds, ["classic"]);
  assert.deepEqual(store.snapshot().previewPlaceIds, ["a", "b"]);
  store.applyPreview();
  assert.deepEqual(store.snapshot().appliedPlaceIds, ["a", "b"]);
  store.undo();
  assert.deepEqual(store.snapshot().appliedPlaceIds, ["classic"]);
});

test("persona advisor returns local reasons when AI times out", async () => {
  const result = await requestPersonaReasons({ persona: PERSONAS[0], routeNames: ["A", "B"], fetchImpl: async () => { throw new TypeError("Failed to fetch"); }, timeoutMs: 5 });
  assert.equal(result.source, "local");
  assert.deepEqual(result.reasons, PERSONAS[0].localReasons);
});
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: FAIL because persona route functions do not exist.

- [ ] **Step 3: Implement preview/apply/undo state**

```js
export function createPersonaRouteStore({ initialRoute }) {
  let state = { appliedPlaceIds: [...initialRoute], previousPlaceIds: null, previewPlaceIds: [], personaId: null };
  return {
    preview: ({ personaId, placeIds }) => { state.previewPlaceIds = [...placeIds]; state.personaId = personaId; },
    applyPreview: () => { state.previousPlaceIds = [...state.appliedPlaceIds]; state.appliedPlaceIds = [...state.previewPlaceIds]; state.previewPlaceIds = []; },
    undo: () => { if (state.previousPlaceIds) state.appliedPlaceIds = [...state.previousPlaceIds]; state.previousPlaceIds = null; },
    snapshot: () => structuredClone(state),
  };
}
```

`requestPersonaReasons` must POST to `/api/agent/chat` with `persist_history: false`, an empty history, and a prompt that includes only the selected persona label and route names. Abort after 6 seconds. Return `{ source: "ai", reasons }` only when three non-empty concise reasons can be parsed; otherwise return `{ source: "local", reasons: persona.localReasons }`.

Use this request boundary:

```js
export async function requestPersonaReasons({ persona, routeNames, fetchImpl = fetch, timeoutMs = 6000 }) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl("/api/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        question: `请用三条短句解释为什么${persona.label}适合依次游览：${routeNames.join("、")}`,
        history: [], visitor_id: "", session_id: "", persist_history: false,
      }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const answer = String((await response.json()).answer || "");
    const reasons = answer.split(/\n+/).map((line) => line.replace(/^[-\d.、\s]+/, "").trim()).filter(Boolean).slice(0, 3);
    if (reasons.length !== 3) throw new Error("AI 推荐理由格式不完整");
    return { source: "ai", reasons };
  } catch {
    return { source: "local", reasons: [...persona.localReasons] };
  } finally {
    clearTimeout(timer);
  }
}
```

- [ ] **Step 4: Implement `PersonaRouteSwitcher.vue`**

The component must display three image-free profile cards, local reasons immediately, and separate “预览路线”“应用这条路线”“撤销” controls. It must never call the map or AI directly; all work flows through emitted events.

- [ ] **Step 5: Run tests and verify GREEN**

Run: `cd frontend; node --test tests/immersive-map.test.js`

Expected: all immersive-map tests PASS.

- [ ] **Step 6: Commit persona interaction**

```powershell
git add frontend/src/features/immersive-map frontend/tests/immersive-map.test.js
git commit -m "feat: add interactive persona routes"
```

---

### Task 7: 将分层舞台接入 `MapView`

**Files:**
- Modify: `frontend/src/views/MapView.vue:1-166`
- Create: `frontend/src/features/immersive-map/immersive-map.css`
- Modify: `frontend/src/main.js:1-28`
- Modify: `frontend/src/visitor-pages.css:578-760`
- Modify: `tests/test_frontend.py`

**Interfaces:**
- Consumes: all feature exports from Tasks 1–6 and current attraction/food/route APIs.
- Produces: complete `/visitor/map` UI while retaining details, filters, route planning and route query behavior.

- [ ] **Step 1: Add a failing integration contract test**

```python
def test_map_view_composes_the_immersive_director_without_duplicating_business_logic():
    source = Path("frontend/src/views/MapView.vue").read_text(encoding="utf-8")
    styles = Path("frontend/src/features/immersive-map/immersive-map.css").read_text(encoding="utf-8")
    assert "ImmersiveMapStage" in source
    assert "TourTimeline" in source
    assert "LingjingOrb" in source
    assert "ScenicStoryCard" in source
    assert "PersonaRouteSwitcher" in source
    assert "useTourDirector" in source
    assert 'fetch("/api/visitor/attractions")' in source
    assert 'fetch(`/api/tools/map/route?' in source
    assert "prefers-reduced-motion" in styles
    assert ".immersive-map-stage.is-offline" in styles
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python -m pytest tests/test_frontend.py::test_map_view_composes_the_immersive_director_without_duplicating_business_logic -q`

Expected: FAIL because the immersive components and stylesheet are not integrated.

- [ ] **Step 3: Refactor `MapView` into a thin composition root**

The setup must follow this shape:

```js
const resolvedTour = computed(() => places.value.length ? resolveTourPlaces(CLASSIC_TOUR, places.value) : null);
const director = useTourDirector(resolvedTour);
const onlineScene = useAmapScene(mapElement);
const offlineScene = useOfflineScene();
const personaRoutes = createPersonaRouteStore({ initialRoute: [] });
const activeScene = computed(() => director.state.value.sceneKind === "offline" ? offlineScene.adapter : onlineScene);
const failover = createSceneFailover({ onSwitch: (kind) => director.switchScene(kind) });

async function startTour() {
  if (!resolvedTour.value) return;
  await offlineScene.adapter.initialize({ tour: resolvedTour.value, places: places.value });
  const kind = await failover.initializeOnline(() => onlineScene.initialize(visiblePlaces.value, selectPlace, { includeLoca: true }));
  director.switchScene(kind);
  director.start();
}

function handlePersonaPreview(persona) {
  const placeIds = resolvePersonaPlaces(persona, places.value).map((place) => place.place_id);
  personaRoutes.preview({ personaId: persona.id, placeIds });
  activeScene.value.drawRoute(placeIds.map((id) => places.value.find((place) => place.place_id === id)), 1);
}
```

Watch director state to dispatch `setCamera`, `drawRoute`, `setActiveStop`, and `enterExploreMode` to the active scene. The watcher must not create timers. Preserve `applyRouteQuery`, `showDetails`, `planRoute`, layer filtering and drawer behavior.

Render a single “开始灵境巡游” button while mode is `idle`. On `ImmersiveMapStage.scene-failed`, call `failover.reportFailure()` and immediately replay the current camera/route/stop command against `offlineScene.adapter` without changing `elapsedMs`. On map interaction during `touring`, call `director.requestTakeover()` and show a local confirmation card; only its confirm button calls `director.confirmTakeover()`. Show “恢复在线地图” only when mode is `exploring` and `recoveryAvailable` is true.

- [ ] **Step 4: Implement the dynamic focus layout and responsive styles**

Use CSS grid areas for `journey`, `stage`, and `advisor`. During `touring`, collapse the rails with opacity and transform while the stage spans the content width. During `exploring`, expand the rails. Use `transition: opacity 480ms, transform 480ms, grid-template-columns 480ms`; under reduced motion, use `opacity 100ms` only.

Desktop minimum target is 1440px wide. At widths below 900px, render the stage first, then persona controls and the existing planner; do not attempt cinematic side rails. Retain 44px minimum button height.

Move only immersive overrides into `immersive-map.css`; keep existing generic map cards in `visitor-pages.css`. Import the new stylesheet from `main.js` after `map-places.css`.

- [ ] **Step 5: Run integration tests and build**

Run: `python -m pytest tests/test_frontend.py -q`

Expected: all frontend contract tests PASS.

Run: `cd frontend; npm test`

Expected: all Node tests PASS.

Run: `cd frontend; npm run build`

Expected: Vite build exits 0 with no unresolved imports.

- [ ] **Step 6: Commit the integrated page**

```powershell
git add frontend/src/views/MapView.vue frontend/src/features/immersive-map/immersive-map.css frontend/src/main.js frontend/src/visitor-pages.css tests/test_frontend.py
git commit -m "feat: integrate immersive interactive map stage"
```

---

### Task 8: 故障矩阵、资源预算与大屏验收

**Files:**
- Modify: `frontend/tests/immersive-map.test.js`
- Modify: `frontend/tests/amap-loader.test.js`
- Modify: `tests/test_frontend.py`
- Modify: `daily-modify/2026-07-23.md`

**Interfaces:**
- Consumes: completed feature and its public contracts.
- Produces: regression coverage, resource checks, documented verification evidence.

- [ ] **Step 1: Add the full failure matrix tests**

Add cases that assert:

```js
test("skip enters exploring without changing the offline scene", () => {
  const director = createTourDirector({ definition: CLASSIC_TOUR, now: () => 0, requestFrame: () => 1, cancelFrame: () => {} });
  director.start(); director.switchScene("offline"); director.skip();
  assert.deepEqual({ mode: director.snapshot().mode, sceneKind: director.snapshot().sceneKind }, { mode: "exploring", sceneKind: "offline" });
});

test("restart clears takeover and resets elapsed time", () => {
  const director = createTourDirector({ definition: CLASSIC_TOUR, now: () => 0, requestFrame: () => 1, cancelFrame: () => {} });
  director.start(); director.requestTakeover(); director.confirmTakeover(); director.restart();
  assert.deepEqual({ mode: director.snapshot().mode, elapsedMs: director.snapshot().elapsedMs, takeoverRequested: director.snapshot().takeoverRequested }, { mode: "touring", elapsedMs: 0, takeoverRequested: false });
});

test("malformed AI reasons keep the three local reasons", async () => {
  const fetchImpl = async () => ({ ok: true, json: async () => ({ answer: "只有一条理由" }) });
  const result = await requestPersonaReasons({ persona: PERSONAS[0], routeNames: ["大照壁", "梵宫"], fetchImpl, timeoutMs: 50 });
  assert.deepEqual(result, { source: "local", reasons: PERSONAS[0].localReasons });
});
```

In `amap-loader.test.js`, retry with two injected documents: the first calls `script.onerror(new Error("offline"))`; the second sets `browser.AMap = { Map: class {} }` and calls `script.onload()`. Assert that the second `loadAmapRuntime` resolves, proving the rejected module promise was cleared. Do not add a mocking library.

Add Python resource assertions:

```python
def test_immersive_map_assets_fit_the_competition_budget():
    audio = Path("frontend/public/audio/immersive-map/classic-tour.mp3")
    background = Path("frontend/public/images/guide-home-background.jpg")
    assert audio.stat().st_size + background.stat().st_size <= 8 * 1024 * 1024
    assert "https://" not in Path("frontend/src/features/immersive-map/components/OfflineScenicStage.vue").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run all automated verification**

Run: `cd frontend; npm test`

Expected: all Node tests PASS with 0 failures.

Run: `python -m pytest tests/test_frontend.py tests/test_amap_api.py -q`

Expected: all selected Python tests PASS.

Run: `cd frontend; npm run build`

Expected: production build exits 0.

Run: `python -m pytest -q`

Expected: the complete Python suite passes; if PostgreSQL-backed tests are intentionally skipped by the established environment fixture, report the exact pass/skip counts.

- [ ] **Step 3: Perform browser acceptance without paid calls**

At 1920×1080, 1520×856, and 1440×900:

1. Intercept or disable `/api/tools/map/config`; confirm local stage is usable within 1.5 seconds.
2. Run the full tour and record 77–79 seconds from start to exploration.
3. Pause at each station, resume, then test `Esc` and confirmed map takeover.
4. Switch all three personas; verify preview, three reasons, apply, and undo.
5. Enable reduced motion; confirm no camera flight, rotation, or pulsing.
6. 连续重播 5 次；确认始终只有一个 AMap 实例、一个 Loca 容器、一个 Audio 对象，且键盘监听没有重复注册。
7. Restore real map configuration for one final smoke test; do not submit AI prompts or paid route requests during visual checks.

- [ ] **Step 4: Record daily modification evidence**

Append a new `daily-modify/2026-07-23.md` entry listing the exact changed files, why each changed, automated pass counts, build result, three viewports, online/offline results, and any audio-asset approval note. Preserve existing entries in that file.

- [ ] **Step 5: Request code review and address only in-scope findings**

Invoke `superpowers:requesting-code-review`. Review the diff against `docs/superpowers/specs/2026-07-23-immersive-interactive-map-design.md`; fix requirement gaps, regressions, leaks, and accessibility defects. Do not add Phase 2 or Phase 3 features.

- [ ] **Step 6: Commit verification artifacts**

```powershell
git add frontend/tests/immersive-map.test.js frontend/tests/amap-loader.test.js tests/test_frontend.py daily-modify/2026-07-23.md
git commit -m "test: verify immersive map resilience"
```

- [ ] **Step 7: Finish the development branch**

Run fresh `npm test`, `npm run build`, targeted Python tests, and full `pytest` once more. Invoke `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch` and present merge, PR, or preservation options to the user. Do not merge or delete the worktree without explicit user selection.
