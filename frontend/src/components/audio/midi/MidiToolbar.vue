<script setup lang="ts">
const props = defineProps<{
  isPlaying: boolean
  currentBeat: number
  totalBeats: number
  loopEnabled: boolean
  tempo: number
}>()

const emit = defineEmits<{
  play: []
  pause: []
  stop: []
  'toggle-loop': []
}>()

function formatTime(beats: number): string {
  const seconds = Math.floor(beats / (props.tempo / 60))
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
</script>

<template>
  <div class="midi-playback-controls">
    <button class="midi-play-btn" @click="isPlaying ? emit('pause') : emit('play')">
      <i class="bi" :class="isPlaying ? 'bi-pause-fill' : 'bi-play-fill'" />
    </button>
    <button class="midi-play-btn" @click="emit('stop')">
      <i class="bi bi-stop-fill" />
    </button>
    <button
      class="midi-play-btn"
      :class="{ 'is-active': loopEnabled }"
      @click="emit('toggle-loop')"
    >
      <i class="bi bi-arrow-repeat" />
    </button>
    <span class="midi-time-display">{{ formatTime(currentBeat) }} / {{ formatTime(totalBeats) }}</span>
  </div>
</template>

<style lang="scss">
.midi-playback-controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.4rem 0.75rem;
  flex-shrink: 0;
  border-top: 1px solid var(--panel-border);
  background: rgba(0, 0, 0, 0.1);
  border-radius: 0 0 8px 8px;
}

.midi-play-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: var(--panel-bg);
  color: var(--text-primary);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  font-size: 0.9rem;

  &:hover {
    background: var(--panel-bg-hover);
  }

  &.is-active {
    background: var(--color-primary);
    color: var(--text-on-primary, #fff);
  }
}

.midi-time-display {
  font-family: monospace;
  font-size: 0.82rem;
  color: var(--text-secondary);
  user-select: none;
  margin-left: 0.25rem;
}
</style>
