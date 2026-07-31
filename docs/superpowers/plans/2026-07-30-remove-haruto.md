# Remove Haruto Child Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Completely remove Haruto so the digital-human system exposes only Mao Pro female guide and Chitose male guide.

**Architecture:** Shrink the shared frontend and backend avatar whitelists to two roles, remove Haruto's connection-level voice profile and environment setting, and delete its local Live2D runtime. Existing invalid-role handling will make stale browser preferences or `avatar.set: haruto` requests fall back or return `INVALID_AVATAR` without changing the realtime protocol shape.

**Tech Stack:** Vue 3, Pixi.js, pixi-live2d-display, FastAPI, Python dataclasses, Node test runner, pytest.

## Global Constraints

- Keep Mao Pro as the default role and Chitose as the only alternate role.
- Preserve realtime history, Agent/RAG, route behavior, audio format, and WebSocket event names.
- Remove `LJ_REALTIME_VOICE_HARUTO` and `realtime_voice_haruto`.
- Delete each Haruto runtime file by one explicit path; do not recursively delete directories.
- Preserve unrelated changes and the root Arcane source files.

---

### Task 1: Define the two-role contract with failing tests

**Files:**
- Modify: `frontend/tests/live2d-characters.test.js`
- Modify: `frontend/tests/realtime-protocol.test.js`
- Modify: `tests/test_realtime_avatar_profiles.py`
- Modify: `tests/test_realtime_session.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_frontend.py`

**Interfaces:**
- Consumes: `AVATAR_IDS`, `avatar_ids()`, `resolve_avatar_profile()`, `normalizeAvatarId()`.
- Produces: Tests requiring only `mao_pro` and `chitose`, with `haruto` rejected as invalid.

- [ ] Change role-list assertions to `["mao_pro", "chitose"]` and `("mao_pro", "chitose")`.
- [ ] Assert a stale `haruto` browser preference normalizes to `mao_pro`.
- [ ] Assert realtime `avatar.set` rejects `haruto` with `INVALID_AVATAR`.
- [ ] Assert settings no longer expose or read `LJ_REALTIME_VOICE_HARUTO`.
- [ ] Run focused frontend and backend tests and verify they fail because Haruto still exists.

### Task 2: Remove Haruto from runtime code and configuration

**Files:**
- Modify: `frontend/src/features/digital-human/lib/live2dCharacters.js`
- Modify: `src/lingjing_ai/realtime/avatar_profiles.py`
- Modify: `src/lingjing_ai/config/settings.py`
- Modify: `src/lingjing_ai/api/app.py`

**Interfaces:**
- Consumes: Existing two-role selector and server-owned voice profiles.
- Produces: A two-role whitelist where `haruto` is invalid.

- [ ] Delete the Haruto frontend profile.
- [ ] Delete the Haruto backend profile and voice setting.
- [ ] Change static completeness checks to require only Mao Pro and Chitose.
- [ ] Run focused tests and verify the two-role contract passes.

### Task 3: Delete Haruto resources and documentation references

**Files:**
- Delete: every file under `frontend/public/digital-human/live2d/haruto/` by explicit path.
- Modify: `docs/qwen_audio_realtime.md`
- Modify: `docs/项目部署运行配置说明书.md`
- Modify: `project_structure.md`
- Modify: `daily-modify/2026-07-30.md`

**Interfaces:**
- Consumes: The two-role runtime.
- Produces: No Haruto runtime asset, voice configuration, product documentation, or active test reference.

- [ ] Delete each Haruto model, texture, physics, metadata, README, and motion file individually.
- [ ] Remove Haruto voice and role documentation.
- [ ] Search runtime, tests, and active documentation for `haruto`, `longanxiaoxin`, and `LJ_REALTIME_VOICE_HARUTO`.

### Task 4: Verify the complete application

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Two-role Live2D implementation.
- Produces: Test and build evidence.

- [ ] Run `npm --prefix frontend run test`.
- [ ] Run `npm --prefix frontend run build`.
- [ ] Run `python -m pytest -q`.
- [ ] Verify the production build contains Mao Pro and Chitose assets and no Haruto asset or source reference.
