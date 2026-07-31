# Haru Semantic Motions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根据游客原话、助手回答、路线证据和实时状态，为Haru女导游选择最具体的动作，并保证同义动作轮换且任意时刻只播放一个动作。

**Architecture:** 新增纯函数语义解析器与独立单动作调度器。解析器只输出语义动作键，不接触Pixi；调度器读取角色注册表中的动作描述，以FORCE优先级原子切换循环动作，并用播放代次隔离旧定时器。现有Live2D渲染器继续独立处理口型和首帧显示。

**Tech Stack:** Vue 3、JavaScript ES modules、Node test runner、pixi-live2d-display 0.4.0。

## Global Constraints

- 只增强兼容角色ID `mao_pro`所指向的Haru女导游，Chitose保持现状。
- 排除M03、M06、M11、M14、M15和M24；所有未配置动作不得触发。
- 具体语义优先；只有真正等价的M22/M23执行轮换，且不得连续重复。
- 任意时刻只允许一个身体动作；高优先级状态可抢占，旧定时器不得恢复旧动作。
- 不修改Qwen、WebSocket协议、后端、数据库、音频格式、口型参数或Live2D资源。
- 不覆盖工作区中ExploreView、角色移除及其他无关改动。

---

### Task 1: Semantic intent resolver

**Files:**
- Create: `frontend/src/features/digital-human/lib/live2dSemanticMotion.js`
- Create: `frontend/tests/live2d-semantic-motion.test.js`

**Interfaces:**
- Produces: `resolveHaruMotionIntent({ state, userText, assistantText, hasRouteSource }) -> string`
- Produces: `createMotionVariantRotator() -> { pick(key, variants), reset() }`

- [ ] **Step 1: Write failing tests**

Cover state precedence, route precedence, complaint/apology, praise/shyness, agreement strength, surprise, uncertainty, excluded motion absence, M22/M23 alternation and no immediate repeat.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `node --test frontend/tests/live2d-semantic-motion.test.js`

Expected: module-not-found or missing-export failure.

- [ ] **Step 3: Implement the minimal resolver**

Use ordered local phrase groups over normalized visitor and assistant text. Return one intent only; unmatched speaking content returns `explanation`, unmatched non-speaking content returns `idle`.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `node --test frontend/tests/live2d-semantic-motion.test.js`

Expected: all semantic and rotation tests pass.

### Task 2: Haru motion registry and exclusive scheduler

**Files:**
- Modify: `frontend/src/features/digital-human/lib/live2dCharacters.js`
- Modify: `frontend/src/features/digital-human/lib/live2dMotion.js`
- Modify: `frontend/tests/live2d-characters.test.js`
- Modify: `frontend/tests/live2d.test.js`

**Interfaces:**
- Profile field: `semanticMotions: Record<string, MotionDescriptor | MotionDescriptor[]>`
- Produces: `createExclusiveMotionController(model, profile, options)`
- Controller methods: `setIntent(intent, fallbackIntent)`, `playEntryMotion()`, `dispose()`

- [ ] **Step 1: Write failing registry and controller tests**

Assert exact Haru motion indices and durations, absence of excluded indices, FORCE priority, one active timer, stale callback isolation, same-motion non-restart, one-shot fallback and M22/M23 rotation.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `node --test frontend/tests/live2d-characters.test.js frontend/tests/live2d.test.js`

- [ ] **Step 3: Implement registry and scheduler**

Model looping clips are treated as one-shot through their configured duration unless marked `loopWhileActive`. Clearing or replacing an intent increments a generation and cancels the previous scheduled fallback.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `node --test frontend/tests/live2d-characters.test.js frontend/tests/live2d.test.js`

### Task 3: Realtime UI integration

**Files:**
- Modify: `frontend/src/composables/useRealtimeChat.js`
- Modify: `frontend/src/views/GuideView.vue`
- Modify: `frontend/src/components/ChatMain.vue`
- Modify: `frontend/src/features/digital-human/components/DigitalHumanStage.vue`
- Modify: `frontend/src/features/digital-human/renderers/Live2DAvatarRenderer.vue`
- Modify: `frontend/src/features/digital-human/index.js`
- Modify: `frontend/tests/realtime-protocol.test.js`

**Interfaces:**
- `useRealtimeChat.latestUserText: ComputedRef<string>`
- Stage/renderer props: `userText`, `assistantText`, `hasRouteSource`

- [ ] **Step 1: Add failing integration assertions**

Assert latest visitor text is exposed, route state reaches the stage, Haru renderer imports the semantic resolver/controller, and Chitose does not receive Haru motion configuration.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `npm --prefix frontend run test`

- [ ] **Step 3: Wire the approved context**

Pass current user text and route source through GuideView and ChatMain. Resolve one semantic intent in the stage, debounce streaming semantic changes for300ms, and let the renderer controller own all motion playback.

- [ ] **Step 4: Run frontend tests and verify GREEN**

Run: `npm --prefix frontend run test`

### Task 4: Documentation and full verification

**Files:**
- Modify: `project_structure.md`
- Modify: `daily-modify/2026-07-30.md`

- [ ] **Step 1: Document the semantic motion boundary**

Record the resolver, exclusive scheduler, configured Haru motions, exclusions, and the fact that Chitose is unchanged.

- [ ] **Step 2: Run full verification**

Run:

```powershell
npm --prefix frontend run test
npm --prefix frontend run build
python -m pytest -q
```

Expected: frontend tests pass, Vite build succeeds, and Python suite has zero failures.

