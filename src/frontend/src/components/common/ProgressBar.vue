<script setup lang="ts">
defineProps<{
  progress: number
  message?: string
  showPercentage?: boolean
}>()
</script>

<template>
  <div class="progress-wrapper">
    <div class="progress" style="height: 8px">
      <div
        class="progress-bar progress-bar-striped progress-bar-animated"
        :class="{
          'bg-success': progress >= 1,
          'bg-primary': progress < 1,
        }"
        role="progressbar"
        :style="{ width: `${Math.min(progress * 100, 100)}%` }"
        :aria-valuenow="progress * 100"
        aria-valuemin="0"
        aria-valuemax="100"
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
}

.progress {
  background-color: rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar {
  transition: width 0.3s ease;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.7);
}

.progress-message {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-percentage {
  margin-left: 8px;
  font-weight: 500;
}
</style>
