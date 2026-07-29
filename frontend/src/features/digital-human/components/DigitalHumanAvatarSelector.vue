<script setup>
import { AVATAR_PROFILES } from "../lib/live2dCharacters.js";

defineProps({
  avatarId: { type: String, default: "mao_pro" },
  pendingAvatarId: { type: String, default: "" },
  avatarReady: { type: Boolean, default: true },
});

const emit = defineEmits(["avatar-change"]);
</script>

<template>
  <div class="digital-human-selector" role="group" aria-label="选择数字人形象">
    <button
      v-for="profile in AVATAR_PROFILES"
      :key="profile.id"
      type="button"
      :class="{
        active: profile.id === avatarId,
        loading: profile.id === pendingAvatarId,
      }"
      :aria-pressed="profile.id === avatarId"
      :disabled="!avatarReady"
      @click="emit('avatar-change', profile.id)"
    >
      <span>{{ profile.label }}</span>
      <small>
        {{ profile.roleLabel }}
        <template v-if="profile.id === pendingAvatarId"> · 同步中</template>
      </small>
    </button>
  </div>
</template>

<style scoped>
.digital-human-selector {
  display: flex;
  justify-content: center;
  gap: 6px;
}

button {
  display: grid;
  gap: 1px;
  min-width: 88px;
  border: 1px solid rgba(47, 118, 109, 0.2);
  border-radius: 12px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.7);
  color: #45615a;
  cursor: pointer;
  backdrop-filter: blur(12px);
}

button.active {
  border-color: var(--guide-accent, #2f7d78);
  background: var(--guide-accent, #2f7d78);
  color: #fff;
}

button.loading { cursor: progress; }
button:disabled { cursor: not-allowed; opacity: 0.72; }

button:focus-visible {
  outline: 3px solid rgba(47, 118, 109, 0.28);
  outline-offset: 2px;
}

span { font-size: 12px; font-weight: 800; }
small { font-size: 9px; opacity: 0.82; }

@media (max-width: 900px) {
  .digital-human-selector { width: 100%; }
  button { min-width: 0; flex: 1; max-width: 126px; }
}
</style>
