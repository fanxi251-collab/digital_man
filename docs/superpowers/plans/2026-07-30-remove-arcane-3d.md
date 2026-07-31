# Remove Arcane 3D Digital Human Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore Mao Pro Live2D as the default female guide and remove all generated Arcane 3D runtime code, assets, dependencies, and tests.

**Architecture:** Return the digital-human frontend to its Live2D registry while preserving the existing role protocol identifiers. Remove only the generated 3D layer; shared realtime audio, avatar voice profiles, history, Agent/RAG, and route behavior remain unchanged.

**Tech Stack:** Vue 3, Pixi.js 6.5.10, pixi-live2d-display 0.4.0, FastAPI, Node test runner, pytest.

## Global Constraints

- Do not touch `arcane-arknights-endfield/` or `arcane__arknights_endfield.glb`; the user will remove them.
- Preserve unrelated changes, especially `frontend/src/views/ExploreView.vue`, `.codex/`, and `.cursor/`.
- Delete generated 3D files one explicit path at a time; do not use recursive deletion.
- Keep the non-Arcane Live2D role behavior unchanged.
- Keep realtime protocol role ID `mao_pro` and the existing female voice configuration.

---

### Task 1: Lock the restored Live2D contract with failing tests

**Files:**
- Modify: `frontend/tests/live2d-characters.test.js`
- Modify: `tests/test_frontend.py`
- Modify: `tests/test_realtime_avatar_profiles.py`

**Interfaces:**
- Consumes: `resolveAvatarProfile("mao_pro")` and `resolve_avatar_profile(settings, "mao_pro")`.
- Produces: Tests requiring Mao Pro Live2D, no Three.js dependency, and the original Mao backend identity.

- [ ] **Step 1: Change the registry test to expect Mao Pro Live2D**

Assert `rendererType === "live2d"` and model URL `/digital-human/live2d/mao_pro/mao_pro.model3.json`.

- [ ] **Step 2: Change integration tests to reject Three.js and Arcane runtime references**

Assert `frontend/package.json` has no `three`, the stage contains no `ThreeDAvatarRenderer`, and the backend profile identifies the Mao female guide.

- [ ] **Step 3: Run tests to verify RED**

Run:

```powershell
npm --prefix frontend run test
python -m pytest tests/test_frontend.py tests/test_realtime_avatar_profiles.py -q
```

Expected: failures because Arcane is still registered and Three.js is still present.

### Task 2: Restore the three-role Live2D implementation

**Files:**
- Modify: `frontend/src/features/digital-human/lib/avatarProfiles.js`
- Modify: `frontend/src/features/digital-human/components/DigitalHumanStage.vue`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `src/lingjing_ai/realtime/avatar_profiles.py`
- Modify: `src/lingjing_ai/api/app.py`

**Interfaces:**
- Consumes: Existing `Live2DAvatarRenderer` and Live2D public assets.
- Produces: Live2D-only profiles without any 3D renderer dependency.

- [ ] **Step 1: Restore Mao Pro profile and stage rendering**

Register Mao Pro with its original model URL, attribution, expression map, and fit values. Remove the 3D renderer branch from `DigitalHumanStage.vue`.

- [ ] **Step 2: Remove Three.js dependency**

Run:

```powershell
npm --prefix frontend uninstall three
```

- [ ] **Step 3: Restore backend identity and Live2D static completeness check**

Restore the Mao display name and identity. Require all three Live2D model directories, Cubism Core, and PCM worklet when selecting static resources.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run:

```powershell
npm --prefix frontend run test
python -m pytest tests/test_frontend.py tests/test_realtime_avatar_profiles.py -q
```

Expected: all focused tests pass.

### Task 3: Remove generated 3D files and update documentation

**Files:**
- Delete: `frontend/src/features/digital-human/renderers/ThreeDAvatarRenderer.vue`
- Delete: `frontend/src/features/digital-human/lib/audioDrivenMouth.js`
- Delete: `frontend/src/features/digital-human/lib/threeMotion.js`
- Delete: `frontend/tests/three-avatar.test.js`
- Delete: `tests/test_arcane_assets.py`
- Delete: `tools/digital-human/arcane/refine_arcane_glb.mjs`
- Delete: `tools/digital-human/arcane/arcane-rig-map.json`
- Delete: `frontend/public/digital-human/3d/arcane/arcane-guide.glb`
- Delete: `frontend/public/digital-human/3d/arcane/model-manifest.json`
- Delete: `frontend/public/digital-human/3d/arcane/ATTRIBUTION.md`
- Modify: `project_structure.md`
- Modify: `daily-modify/2026-07-30.md`

**Interfaces:**
- Consumes: The restored Live2D-only frontend contract.
- Produces: A repository with no generated Arcane runtime or Three.js code.

- [ ] **Step 1: Delete each generated 3D file by explicit path**

Do not remove directories recursively and do not touch the original Arcane downloads.

- [ ] **Step 2: Restore Live2D-only project documentation**

Document Mao Pro as the default female guide and record why Arcane 3D was removed.

- [ ] **Step 3: Verify no runtime references remain**

Run:

```powershell
rg -n "ThreeDAvatarRenderer|threeMotion|audioDrivenMouth|digital-human/3d/arcane|from \"three\"" frontend src tests project_structure.md
```

Expected: no matches.

### Task 4: Full verification

**Files:**
- Verify only.

**Interfaces:**
- Consumes: Restored Live2D implementation.
- Produces: Test and build evidence.

- [ ] **Step 1: Run frontend tests**

```powershell
npm --prefix frontend run test
```

- [ ] **Step 2: Run production build**

```powershell
npm --prefix frontend run build
```

- [ ] **Step 3: Run backend tests**

```powershell
python -m pytest -q
```

- [ ] **Step 4: Confirm original Arcane inputs remain present and unchanged**

Check the original GLB SHA-256 remains `697832CDBF646F30309749088EB42CBEF73326839489E728D56F0788AC2C3F3D`.
