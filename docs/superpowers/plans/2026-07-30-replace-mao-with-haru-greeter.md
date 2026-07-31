# Haru Greeter Female Guide Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Haru Greeter the visible default female guide while preserving the compatibility ID `mao_pro`, its Qwen voice configuration, and every existing Mao Pro runtime file.

**Architecture:** The frontend avatar registry keeps two public IDs (`mao_pro`, `chitose`) but redirects the female profile to a separate Haru runtime directory. The renderer starts Haru's explicitly declared idle motion because this model stores motions in an empty-string group and has no expression files. Backend profile text changes to Haru while connection protocol, history, voice settings, and role selection remain compatible.

**Tech Stack:** Vue 3, pixi.js 6.5.10, pixi-live2d-display 0.4.0, Cubism 4, FastAPI, Node test runner, pytest.

## Global Constraints

- Do not delete or modify `haru_greeter_ja/`.
- Do not delete or overwrite `frontend/public/digital-human/live2d/mao_pro/`.
- Keep the compatibility role ID `mao_pro` and voice setting `LJ_REALTIME_VOICE_MAO_PRO`.
- Keep Chitose unchanged as the only alternate role.
- Haru has no expression files, so semantic expression requests must safely return `null`.
- All model and runtime resources must load from local `/digital-human/` URLs.
- Do not change realtime protocol, SQLite history, Agent/RAG, route behavior, or Qwen call count.

---

### Task 1: Lock the Haru replacement contract with failing tests

**Files:**
- Modify: `frontend/tests/live2d-characters.test.js`
- Modify: `frontend/tests/live2d.test.js`
- Modify: `tests/test_frontend.py`
- Modify: `tests/test_realtime_avatar_profiles.py`

**Interfaces:**
- Consumes: `resolveAvatarProfile("mao_pro")`, `avatarExpression()`, `startProfileIdleMotion()`, and `resolve_avatar_profile()`.
- Produces: Tests that fail until Haru is the active female model, its local resources exist, idle playback is supported, and Mao remains available.

- [ ] **Step 1: Write frontend registry and idle-motion tests**

Assert that `mao_pro` resolves to Haru Greeter, uses `/digital-human/live2d/haru_greeter/haru_greeter_t05.model3.json`, declares idle motion `{ group: "", index: 0 }`, and maps all semantic expressions to `null`. Add an async unit test proving `startProfileIdleMotion(model, profile)` invokes `model.motion("", 0)` once and safely skips profiles without idle configuration.

- [ ] **Step 2: Write backend and asset tests**

Assert the backend `mao_pro` profile identifies Haru but still uses `longanqian`. Validate Haru model references, 27 local motions, EyeBlink/LipSync groups, static HTTP access, and a retained Mao Pro model file.

- [ ] **Step 3: Run focused tests and verify RED**

Run:

```powershell
npm --prefix frontend run test
python -m pytest tests/test_frontend.py tests/test_realtime_avatar_profiles.py -q
```

Expected: failures show the registry still targets Mao, the Haru runtime is absent, idle-motion support is missing, and the backend still names Mao.

### Task 2: Add the Haru runtime and idle-motion behavior

**Files:**
- Create: `frontend/public/digital-human/live2d/haru_greeter/**`
- Modify: `frontend/src/features/digital-human/lib/live2dCharacters.js`
- Modify: `frontend/src/features/digital-human/lib/live2dMotion.js`
- Modify: `frontend/src/features/digital-human/renderers/Live2DAvatarRenderer.vue`

**Interfaces:**
- Consumes: source files in `haru_greeter_ja/runtime/`.
- Produces: `startProfileIdleMotion(model, profile): Promise<boolean>` and a Haru-backed `mao_pro` profile.

- [ ] **Step 1: Copy the runtime without touching originals**

Copy all 34 files from `haru_greeter_ja/runtime/` to `frontend/public/digital-human/live2d/haru_greeter/`, preserving relative paths and filenames. Add a local README that records Live2D Inc., the official sample-data terms, and the preserved source folder.

- [ ] **Step 2: Redirect the female registry profile**

Set the female label and model URL to Haru Greeter, keep `id: "mao_pro"`, use an empty frozen expression map, preserve role label and fit settings, and declare `idleMotion: { group: "", index: 0 }`.

- [ ] **Step 3: Start the configured idle motion after model load**

Implement `startProfileIdleMotion()` with validation and error isolation. Call it after the model is attached and fitted; an optional motion failure must warn once but must not prevent the renderer from emitting `ready`.

- [ ] **Step 4: Run frontend tests and verify GREEN**

Run `npm --prefix frontend run test`.

Expected: all frontend tests pass.

### Task 3: Update backend identity and static-resource selection

**Files:**
- Modify: `src/lingjing_ai/realtime/avatar_profiles.py`
- Modify: `src/lingjing_ai/api/app.py`

**Interfaces:**
- Consumes: the unchanged role ID `mao_pro` and unchanged `settings.realtime_voice_mao_pro`.
- Produces: Haru-specific identity instructions and production static serving that requires Haru, Mao, and Chitose assets.

- [ ] **Step 1: Rename only the female persona**

Change `display_name` and `identity` to Haru Greeter while preserving every voice, pace, sentence, address, emotion, introduction, route, clarification, and error rule.

- [ ] **Step 2: Require the active and rollback runtimes**

Make the static-resource completeness check require `haru_greeter`, `mao_pro`, and `chitose`, so production cannot silently select a build that omits either the active female model or its rollback asset.

- [ ] **Step 3: Run focused backend tests and verify GREEN**

Run `python -m pytest tests/test_frontend.py tests/test_realtime_avatar_profiles.py -q`.

Expected: all focused backend and asset tests pass.

### Task 4: Documentation, build, and full verification

**Files:**
- Modify: `frontend/public/digital-human/live2d/NOTICE.md`
- Modify: `docs/qwen_audio_realtime.md`
- Modify: `project_structure.md`
- Modify: `daily-modify/2026-07-30.md`

**Interfaces:**
- Consumes: the implemented registry and profile behavior.
- Produces: accurate operator documentation distinguishing compatibility ID, active Haru model, and retained Mao rollback files.

- [ ] **Step 1: Update active documentation**

Document that `mao_pro` is a compatibility ID whose visible model is Haru Greeter; voice remains `longanqian`; Mao Pro assets are retained but unused at runtime.

- [ ] **Step 2: Record the daily change**

Append modified files, reasons, validation results, and the no-deletion decision to `daily-modify/2026-07-30.md`.

- [ ] **Step 3: Run full verification**

Run:

```powershell
npm --prefix frontend run test
npm --prefix frontend run build
python -m pytest -q
```

Expected: all tests and the production build pass without paid API calls.

- [ ] **Step 4: Inspect the built artifact**

Confirm the build contains Haru Greeter, retained Mao Pro, and Chitose runtime files, with no remote model URLs.
