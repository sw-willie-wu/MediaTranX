<script setup lang="ts">
defineProps<{
  progress: number
  message?: string
  showPercentage?: boolean
}>()
</script>

<template>
  <div class="progress-wrapper">
    <div class="progress-track">
      <div
        class="progress-fill"
        :class="{ done: progress >= 1 }"
        :style="{ width: `${Math.min(progress * 100, 100)}%` }"
      ></div>
    </div>
    <div class="progress-info" v-if="message || showPercentage">
      <span class="progress-message" v-if="message">{{ message }}</span>
      <span class="progress-percentage" v-if="showPercentage">
        {{ Math.round(progress * 100) }}%
      </span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.progress-wrapper {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.progress-track {
  width: 100%;
  height: 6px;
  background: var(--input-border, rgba(255, 255, 255, 0.1));
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary, #60a5fa), #818cf8);
  border-radius: 3px;
  transition: width 0.4s ease;

  &.done {
    background: linear-gradient(90deg, #34d399, #10b981);
  }
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.78rem;
}

.progress-message {
  color: var(--text-muted);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-percentage {
  color: var(--text-secondary);
  flex-shrink: 0;
  margin-left: 0.5rem;
  font-weight: 500;
}
</style>
