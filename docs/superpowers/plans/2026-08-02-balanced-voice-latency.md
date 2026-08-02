# Balanced Voice Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

当前时间：2026-08-02（Asia/Shanghai）

**Goal:** 在保留景区专名纠错、句尾保护和低置信度确认的前提下，缩短语音提交、转写归一化和回答首字等待。

**Architecture:** 前端把 PCM 采集策略拆成可测试的纯模块，按真实分片时长统计语音质量，并在 160–240ms 间选择句尾等待。后端在确定性转写结果足够明确时跳过问题理解模型，并通过独立的延迟跟踪器记录提交到转写、归一化、证据准备、响应请求和首字阶段。

**Tech Stack:** Vue 3、Vite、Web Audio API/AudioWorklet、Node.js `node:test`、Python 3、pytest、asyncio、Qwen Realtime WebSocket。

## Global Constraints

- 使用“均衡模式”：60ms 音频分片、160–240ms 自适应句尾保护、按纠错置信度决定模型调用。
- 有效语音提交门槛继续为 300ms；中低置信度专名保护和低置信度确认不得移除。
- 不新增前端依赖，不更换模型，不启用未完成转写的推测式预检索。
- WebSocket 事件、前端消息结构、数字人 PCM 播放、来源面板和路线面板契约保持兼容。
- 新增日志不得包含原始音频或完整敏感内容，只记录 turn/trace 标识、阶段名和毫秒数。
- 单个生产代码文件尽量不超过 800 行；新增职责优先放入低耦合小模块。
- 保留工作区现有无关修改；由于目标文件已有用户修改，实施时不得按整文件暂存或提交这些文件，除非用户另行授权。
- 每个生产行为严格执行 RED → GREEN → REFACTOR，并保留失败测试与通过测试的命令输出证据。

---

## File Structure

- Create: `frontend/public/digital-human/pcm-capture-policy.js` — 定义 16kHz/60ms 分片并计算带真实时长的 PCM 指标。
- Modify: `frontend/public/digital-human/pcm-capture-worklet.js` — 消费纯策略模块并上传 60ms PCM 块。
- Modify: `frontend/src/features/digital-human/lib/audioCaptureQuality.js` — 按块时长累计质量并选择 160ms 或 240ms 句尾等待。
- Modify: `frontend/src/features/digital-human/composables/usePcmAudio.js` — 把块时长指标传入质量跟踪器，维持现有资源生命周期。
- Modify: `frontend/src/features/digital-human/index.js` — 导出新的句尾策略函数供实时会话使用。
- Modify: `frontend/src/composables/useRealtimeChat.js` — 在停止录音时根据质量快照选择句尾等待。
- Modify: `frontend/tests/pcm-audio.test.js` — 覆盖真实时长累计、自适应句尾和取消行为。
- Create: `frontend/tests/pcm-capture-policy.test.js` — 直接运行纯采集策略，验证分片大小和指标。
- Modify: `src/lingjing_ai/realtime/conversation.py` — 增加无需模型的转写快速路径。
- Modify: `tests/test_realtime_conversation.py` — 覆盖 `none`、唯一 `high`、多候选、`medium`、`low` 与异常回退。
- Create: `src/lingjing_ai/realtime/latency.py` — 提供注入时钟、按 turn 隔离且一次性消费的阶段计时器。
- Modify: `src/lingjing_ai/realtime/session.py` — 在既有事件边界调用延迟计时器，不承担计算职责。
- Create: `tests/test_realtime_latency.py` — 覆盖阶段计时、未知阶段、不重复上报和清理。
- Modify: `tests/test_realtime_session.py` — 验证真实会话事件会记录各阶段且首字只记录一次。
- Modify: `docs/qwen_audio_realtime.md` — 更新 60ms 分片、自适应尾音和纠错快速路径说明。
- Create or modify: `daily-modify/2026-08-02.md` — 记录实际修改及最终验证结果。

---

### Task 1: 60ms PCM 分片与真实音频时长

**Files:**
- Create: `frontend/public/digital-human/pcm-capture-policy.js`
- Modify: `frontend/public/digital-human/pcm-capture-worklet.js`
- Modify: `frontend/src/features/digital-human/lib/audioCaptureQuality.js`
- Modify: `frontend/src/features/digital-human/composables/usePcmAudio.js`
- Test: `frontend/tests/pcm-capture-policy.test.js`
- Test: `frontend/tests/pcm-audio.test.js`

**Interfaces:**
- Produces: `TARGET_SAMPLE_RATE = 16000`, `CAPTURE_CHUNK_MS = 60`, `SAMPLES_PER_CHUNK = 960` and `calculateCaptureMetrics(samples, sampleRate)`.
- Produces: `createCaptureQualityTracker().add({ rms, clippedRatio, durationMs })`, where `durationMs` is accumulated instead of assuming a fixed block duration.
- Preserves: `usePcmAudio({ onCaptureChunk, onPlaybackStateChange })` and its public return shape.

- [ ] **Step 1: Write the failing pure capture-policy test**

Add `frontend/tests/pcm-capture-policy.test.js`:

```js
import assert from "node:assert/strict";
import test from "node:test";

import {
  CAPTURE_CHUNK_MS,
  SAMPLES_PER_CHUNK,
  TARGET_SAMPLE_RATE,
  calculateCaptureMetrics,
} from "../public/digital-human/pcm-capture-policy.js";

test("60ms capture chunks expose their real audio duration", () => {
  const samples = new Float32Array(SAMPLES_PER_CHUNK).fill(0.02);
  const metrics = calculateCaptureMetrics(samples, TARGET_SAMPLE_RATE);

  assert.equal(CAPTURE_CHUNK_MS, 60);
  assert.equal(SAMPLES_PER_CHUNK, 960);
  assert.equal(metrics.durationMs, 60);
  assert.ok(metrics.rms > 0.019 && metrics.rms < 0.021);
});
```

- [ ] **Step 2: Run the new test and verify RED**

Run: `cd frontend; node --test tests/pcm-capture-policy.test.js`

Expected: FAIL because `pcm-capture-policy.js` does not exist.

- [ ] **Step 3: Implement the pure capture policy and connect the worklet**

Create `pcm-capture-policy.js` with literal 16kHz/60ms values and a pure metric function. Update the worklet to import these exports, set `samplesPerChunk` to `SAMPLES_PER_CHUNK`, and send the returned `{ rms, peak, clippedRatio, durationMs }` beside each transferable PCM buffer.

The worklet comment must state both what the 60ms block does and why it reduces upstream visibility delay without sending very small frames.

- [ ] **Step 4: Run the capture-policy test and verify GREEN**

Run: `cd frontend; node --test tests/pcm-capture-policy.test.js`

Expected: PASS.

- [ ] **Step 5: Write the failing real-duration quality test**

Extend `frontend/tests/pcm-audio.test.js`:

```js
test("capture quality preserves the 300ms speech threshold with 60ms chunks", () => {
  const quality = createCaptureQualityTracker();
  for (let index = 0; index < 4; index += 1) {
    quality.add({ rms: 0.02, clippedRatio: 0, durationMs: 60 });
  }
  assert.equal(quality.snapshot().voicedDurationMs, 240);
  assert.equal(quality.snapshot().canCommit, false);

  quality.add({ rms: 0.02, clippedRatio: 0, durationMs: 60 });
  assert.equal(quality.snapshot().voicedDurationMs, 300);
  assert.equal(quality.snapshot().canCommit, true);
});
```

- [ ] **Step 6: Run the focused quality test and verify RED**

Run: `cd frontend; node --test --test-name-pattern="preserves the 300ms" tests/pcm-audio.test.js`

Expected: FAIL because the tracker still adds a fixed 100ms per voiced frame.

- [ ] **Step 7: Implement real-duration accumulation**

Replace `voicedFrames * AUDIO_CHUNK_MS` with a private `voicedDurationMs` accumulator. Accept only finite positive `durationMs`; use 100ms solely as a compatibility fallback for any older producer that omits the field. Reset the accumulator in `reset()`.

No caller API changes are required because `usePcmAudio` already forwards the complete metrics object to `qualityTracker.add()`.

- [ ] **Step 8: Run Task 1 tests**

Run: `cd frontend; node --test tests/pcm-capture-policy.test.js tests/pcm-audio.test.js`

Expected: PASS.

- [ ] **Step 9: Review Task 1 diff without committing shared dirty files**

Run: `git diff --check -- frontend/public/digital-human/pcm-capture-policy.js frontend/public/digital-human/pcm-capture-worklet.js frontend/src/features/digital-human/lib/audioCaptureQuality.js frontend/src/features/digital-human/composables/usePcmAudio.js frontend/tests/pcm-capture-policy.test.js frontend/tests/pcm-audio.test.js`

Expected: exit code 0. Do not stage the modified shared files because they contain pre-existing user work.

---

### Task 2: 160–240ms 自适应句尾保护

**Files:**
- Modify: `frontend/src/features/digital-human/lib/audioCaptureQuality.js`
- Modify: `frontend/src/features/digital-human/index.js`
- Modify: `frontend/src/composables/useRealtimeChat.js`
- Test: `frontend/tests/pcm-audio.test.js`

**Interfaces:**
- Produces: `resolveTailProtectionMs(snapshot) -> 160 | 240`.
- Changes: `createTailProtection().start(callback, delayMs)` with a safe default of 240ms.
- Consumes: `audio.captureSnapshot()` already returns `latestRms` and quality fields.

- [ ] **Step 1: Write failing adaptive-tail behavior tests**

Update imports in `pcm-audio.test.js`, then add:

```js
test("tail protection waits 160ms after silence and 240ms while speech remains active", () => {
  assert.equal(resolveTailProtectionMs({ latestRms: 0.001 }), 160);
  assert.equal(resolveTailProtectionMs({ latestRms: 0.02 }), 240);
  assert.equal(resolveTailProtectionMs({ latestRms: Number.NaN }), 240);
  assert.equal(resolveTailProtectionMs(), 240);
});

test("tail protection schedules the selected delay and cancellation prevents commit", async () => {
  const scheduled = [];
  const tail = createTailProtection({
    schedule(callback, delay) {
      scheduled.push({ callback, delay, cancelled: false });
      return scheduled.length - 1;
    },
    cancel(handle) { scheduled[handle].cancelled = true; },
  });
  let commits = 0;

  tail.start(() => { commits += 1; }, 160);
  assert.equal(scheduled[0].delay, 160);
  tail.cancel();
  if (!scheduled[0].cancelled) await scheduled[0].callback();
  assert.equal(commits, 0);
});
```

- [ ] **Step 2: Run adaptive-tail tests and verify RED**

Run: `cd frontend; node --test --test-name-pattern="tail protection" tests/pcm-audio.test.js`

Expected: FAIL because `resolveTailProtectionMs` is missing and `start()` ignores a selected delay.

- [ ] **Step 3: Implement the policy and consume it at release time**

In `audioCaptureQuality.js`, define `SILENT_TAIL_PROTECTION_MS = 160` and `ACTIVE_TAIL_PROTECTION_MS = 240`. `resolveTailProtectionMs` returns 160 only for a finite `latestRms < SILENCE_RMS`; otherwise it returns 240. `createTailProtection.start(callback, delayMs = ACTIVE_TAIL_PROTECTION_MS)` validates the delay and falls back to 240.

Export the resolver through `features/digital-human/index.js`. In `useRealtimeChat.stopRecording()`, take a pre-tail quality snapshot, resolve the delay, and pass it to `tailProtection.start`. Continue taking the final snapshot after capture stops so the extra tail audio contributes to the 300ms voice check.

Update the status text from a fixed-delay implication to `正在保护句尾语音`.

- [ ] **Step 4: Run front-end focused tests and verify GREEN**

Run: `cd frontend; node --test tests/pcm-audio.test.js`

Expected: PASS, including cancellation behavior.

- [ ] **Step 5: Review Task 2 diff without staging shared files**

Run: `git diff --check -- frontend/src/features/digital-human/lib/audioCaptureQuality.js frontend/src/features/digital-human/index.js frontend/src/composables/useRealtimeChat.js frontend/tests/pcm-audio.test.js`

Expected: exit code 0.

---

### Task 3: 确定性转写快速路径

**Files:**
- Modify: `src/lingjing_ai/realtime/conversation.py`
- Test: `tests/test_realtime_conversation.py`

**Interfaces:**
- Produces: `_requires_voice_model(correction: TranscriptCorrection) -> bool`.
- Preserves: `normalize_transcript(transcript: str, visitor_id: str, session_id: str) -> VoiceQuestionUnderstanding` and the low-confidence confirmation contract.

- [ ] **Step 1: Add test doubles and failing fast-path tests**

Use a `StaticTranscriptNormalizer` that returns a complete `TranscriptCorrection` and a `RecordingVoiceExpander` that records calls while returning a complete `VoiceQuestionUnderstanding`. Add these doubles and table-driven tests with literal expectations:

```python
class StaticTranscriptNormalizer:
    def __init__(self, correction: TranscriptCorrection) -> None:
        self.correction = correction

    def normalize(self, text: str) -> TranscriptCorrection:
        assert text == self.correction.original_text
        return self.correction


class RecordingVoiceExpander:
    def __init__(self, result: VoiceQuestionUnderstanding) -> None:
        self.result = result
        self.calls = []

    def understand_voice(self, original, candidates, history, max_candidates):
        self.calls.append((original, list(candidates), list(history), max_candidates))
        return self.result


@pytest.mark.parametrize(
    ("correction", "expected_text"),
    [
        (TranscriptCorrection("灵山几点开放", "灵山几点开放", "none", 0.0, [], []), "灵山几点开放"),
        (TranscriptCorrection("灵山大服怎么走", "灵山大佛怎么走", "high", 1.0, ["灵山大佛怎么走"], ["灵山大佛"]), "灵山大佛怎么走"),
    ],
)
def test_clear_voice_transcripts_skip_the_context_model(
    tmp_path: Path,
    pg_dsn: str,
    conversations_schema: str,
    correction: TranscriptCorrection,
    expected_text: str,
):
    settings = replace(AppSettings.for_workspace(tmp_path), question_expansion_enabled=True)
    store = ConversationStore(pg_dsn, schema=conversations_schema)
    expander = RecordingVoiceExpander(
        VoiceQuestionUnderstanding(normalized_question=correction.corrected_text)
    )
    service = RealtimeConversationService(
        settings,
        store,
        FakeAgentExecutor(),
        question_expander=expander,
        transcript_normalizer=StaticTranscriptNormalizer(correction),
    )

    result = service.normalize_transcript(correction.original_text, "visitor_a", "")
    assert result.normalized_question == expected_text
    assert expander.calls == []
    assert result.expanded_questions == []
```

The production mutation caught by this test is restoring the unconditional `understand_voice` call.

- [ ] **Step 2: Run the fast-path test and verify RED**

Run: `pytest tests/test_realtime_conversation.py -k "clear_voice_transcripts_skip" -q`

Expected: FAIL because the current implementation always invokes the expander when configured.

- [ ] **Step 3: Implement the minimal fast-path predicate**

Return `False` for `none`; return `False` for `high` only when its unique non-empty candidate count is at most one; return `True` for `medium`, `low`, or multiple effective candidates. In `normalize_transcript`, return the deterministic correction with an empty expansion list when the predicate is false. Preserve existing model exception fallback.

- [ ] **Step 4: Run the fast-path test and verify GREEN**

Run: `pytest tests/test_realtime_conversation.py -k "clear_voice_transcripts_skip" -q`

Expected: PASS.

- [ ] **Step 5: Write failing ambiguous and fallback tests**

Add literal cases proving:

- a two-candidate `high` correction calls the model;
- `medium` calls the model and accepts only a deterministic candidate;
- `low` calls the model but remains `low` when confidence does not justify promotion;
- an expander exception returns the deterministic correction without exposing the exception.

Assert the returned understanding and user-visible correction fields. Record call inputs only to prove the ambiguous branch receives the expected complete candidate set; do not assert a mock merely exists.

- [ ] **Step 6: Run ambiguous-path tests and verify RED/GREEN**

Run before minimal implementation: `pytest tests/test_realtime_conversation.py -k "voice_model or voice_expander_failure" -q`

Expected before implementation: at least the multi-candidate branch fails if the predicate is incomplete.

Run after implementation: same command.

Expected after implementation: PASS.

- [ ] **Step 7: Run related backend regression tests**

Run: `pytest tests/test_realtime_conversation.py tests/test_realtime_session.py tests/test_question_expansion.py -q`

Expected: PASS.

- [ ] **Step 8: Review Task 3 diff without staging shared files**

Run: `git diff --check -- src/lingjing_ai/realtime/conversation.py tests/test_realtime_conversation.py`

Expected: exit code 0.

---

### Task 4: 分阶段实时延迟日志

**Files:**
- Create: `src/lingjing_ai/realtime/latency.py`
- Modify: `src/lingjing_ai/realtime/session.py`
- Create: `tests/test_realtime_latency.py`
- Modify: `tests/test_realtime_session.py`

**Interfaces:**
- Produces: `RealtimeLatencyTracker(clock=time.perf_counter)`.
- Produces: `start(turn_id: str, stage: str) -> None`, `finish(turn_id: str, stage: str) -> float | None`, and `clear(turn_id: str) -> None`.
- Stage keys: `transcript`, `normalization`, `evidence`, `response_request`, `first_delta`.

- [ ] **Step 1: Write failing tracker unit tests**

Create `tests/test_realtime_latency.py` with an injected deterministic clock:

```python
def test_latency_tracker_finishes_each_stage_once_and_clears_turn():
    ticks = iter([1.0, 1.125, 2.0, 2.050])
    tracker = RealtimeLatencyTracker(clock=lambda: next(ticks))

    tracker.start("turn_1", "transcript")
    assert tracker.finish("turn_1", "transcript") == pytest.approx(125.0)
    assert tracker.finish("turn_1", "transcript") is None
    tracker.start("turn_1", "evidence")
    tracker.clear("turn_1")
    assert tracker.finish("turn_1", "evidence") is None
```

- [ ] **Step 2: Run tracker tests and verify RED**

Run: `pytest tests/test_realtime_latency.py -q`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the focused tracker module**

Store starts under `(turn_id, stage)` keys. Reject blank keys by doing nothing, consume a start on the first `finish`, clamp elapsed milliseconds to at least zero, and remove all matching keys in `clear`. Keep the module independent of logging and session classes so it remains below 100 lines.

- [ ] **Step 4: Run tracker tests and verify GREEN**

Run: `pytest tests/test_realtime_latency.py -q`

Expected: PASS.

- [ ] **Step 5: Write the failing session instrumentation test**

Extend the existing fake-session scenario to drive these real boundaries in order:

1. `audio.start` and `audio.commit`;
2. `input_audio_transcription.completed`;
3. evidence preparation and `response.create`;
4. two answer delta events.

Use `caplog` and assert each metric name is present once for the turn:

```python
for metric in (
    "audio_committed_to_transcript_ms",
    "transcript_normalization_ms",
    "evidence_prepare_ms",
    "response_request_ms",
    "response_first_delta_ms",
):
    assert caplog.text.count(f"metric={metric}") == 1
assert "turn_id=turn_latency" in caplog.text
```

This catches missing event hooks and duplicate first-delta logging; it does not assert exact wall-clock milliseconds.

- [ ] **Step 6: Run the session instrumentation test and verify RED**

Run: `pytest tests/test_realtime_session.py -k "records_voice_latency_stages" -q`

Expected: FAIL because the session has no latency instrumentation.

- [ ] **Step 7: Integrate the tracker at existing event boundaries**

Instantiate one tracker per `VisitorRealtimeSession`. Start/finish stages at these exact points:

- `_commit_audio`: start `transcript` immediately before the upstream commit.
- completed transcription event: finish `transcript` before normalization.
- `_handle_completed_transcript`: measure only `normalize_transcript` as `normalization`.
- `_reserve_question`: measure only `service.prepare_turn` as `evidence`.
- `_start_question`: measure `inject_evidence` plus `create_response` as `response_request`, then start `first_delta` after the response request completes.
- first non-empty `_is_answer_delta`: finish `first_delta` before forwarding it.

Log through one private helper with format `realtime_latency turn_id=%s metric=%s value_ms=%.1f`. Clear the turn on completion, cancellation and terminal fallback. Do not log when `finish` returns `None`.

Comments at integration points must state what lifecycle boundary is measured and why that boundary makes the value actionable.

- [ ] **Step 8: Run latency and session tests and verify GREEN**

Run: `pytest tests/test_realtime_latency.py tests/test_realtime_session.py -q`

Expected: PASS.

- [ ] **Step 9: Check file size and diff hygiene**

Run: `(Get-Content 'src/lingjing_ai/realtime/latency.py').Count; (Get-Content 'src/lingjing_ai/realtime/session.py').Count; git diff --check -- src/lingjing_ai/realtime/latency.py src/lingjing_ai/realtime/session.py tests/test_realtime_latency.py tests/test_realtime_session.py`

Expected: latency module below 100 lines and no whitespace errors. The existing session file is already 813 lines; keep integration changes minimal and do not add independent timing logic to that file.

---

### Task 5: Documentation, full verification and daily record

**Files:**
- Modify: `docs/qwen_audio_realtime.md`
- Create or modify: `daily-modify/2026-08-02.md`

**Interfaces:**
- Documents only verified behavior and actual command results.

- [ ] **Step 1: Update realtime audio documentation**

Replace the fixed “100ms 分片、松开后 300ms” description with:

- 约 60ms 分片；
- 按真实块时长统计有效语音；
- 静音句尾 160ms、活动句尾或异常指标 240ms；
- `none`/唯一 `high` 走确定性快速路径，疑难候选才调用问题理解模型。

Explain why the low-confidence confirmation remains.

- [ ] **Step 2: Run complete frontend verification**

Run: `cd frontend; npm test`

Expected: all Node tests pass.

Run: `cd frontend; npm run build`

Expected: Vite production build exits 0. Existing non-blocking bundle-size warnings may be recorded but must not be presented as new failures.

- [ ] **Step 3: Run related and full backend verification**

Run: `pytest tests/test_realtime_latency.py tests/test_realtime_conversation.py tests/test_realtime_session.py tests/test_question_expansion.py tests/test_frontend.py -q`

Expected: PASS.

Run: `pytest -q`

Expected: PASS. Record passed/skipped/warning counts exactly as printed.

- [ ] **Step 4: Verify compatibility and inspect only task diffs**

Run: `git diff --check`

Run: `git status --short`

Review only the files listed in this plan. Do not revert, delete, stage or summarize unrelated user changes as part of this task.

- [ ] **Step 5: Write the daily modification record**

Append one entry to `daily-modify/2026-08-02.md` using the `daily-modify` skill format. List only files actually changed for this task, why each changed, exact test/build commands and any remaining limitation such as the need for a real microphone/network latency check.

- [ ] **Step 6: Final verification before completion**

Invoke `superpowers:verification-before-completion`, rerun the smallest commands that directly support every final claim, and cite their fresh outputs. Do not claim real-world millisecond savings beyond the deterministic 60ms/160–240ms policies unless a live upstream benchmark was actually run.

---

## Plan Self-Review

- Spec coverage: audio chunking, real-duration quality, adaptive tail, deterministic correction fast path, ambiguous correction protection, internal metrics, compatibility, documentation and full regression each map to a task.
- Placeholder scan: the plan contains no deferred implementation placeholders or incomplete code blocks.
- Type consistency: the front-end tail resolver consumes the existing quality snapshot; the backend fast path preserves `VoiceQuestionUnderstanding`; latency stages and metric names have one explicit mapping.
- Scope: no supplier/model change, speculative retrieval, UI redesign, new dependency or answer-length work is included.
