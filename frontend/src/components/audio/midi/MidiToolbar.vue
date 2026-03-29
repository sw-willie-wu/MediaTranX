<script setup lang="ts">
const props = defineProps<{
  isPlaying: boolean
  currentBeat: number
  totalBeats: number
  loopEnabled: boolean
  toolMode: 'select' | 'draw' | 'erase'
  tempo: number
}>()

const emit = defineEmits<{
  play: []
  pause: []
  stop: []
  'toggle-loop': []
  'set-tool': [mode: 'select' | 'draw' | 'erase']
}>()

function formatTime(beats: number): string {
  const seconds = Math.floor(beats / (props.tempo / 60))
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
</script>

<template>
  <div class="midi-toolbar">
    <!-- Transport controls -->
    <div class="toolbar-group">
      <button
        class="toolbar-btn"
        :title="isPlaying ? 'Pause' : 'Play'"
        @click="isPlaying ? emit('pause') : emit('play')"
      >
        <i :class="isPlaying ? 'bi-pause-fill' : 'bi-play-fill'" />
      </button>
      <button class="toolbar-btn" title="Stop" @click="emit('stop')">
        <i class="bi-stop-fill" />
      </button>
      <button
        class="toolbar-btn"
        :class="{ 'is-active': loopEnabled }"
        title="Loop"
        @click="emit('toggle-loop')"
      >
        <i class="bi-arrow-repeat" />
      </button>
    </div>

    <span class="divider" />

    <!-- Time display -->
    <span class="time-display">
      {{ formatTime(currentBeat) }} / {{ formatTime(totalBeats) }}
    </span>

    <span class="divider" />

    <!-- Tool mode buttons -->
    <div class="toolbar-group">
      <button
        class="toolbar-btn"
        :class="{ 'is-active': toolMode === 'select' }"
        title="Select"
        @click="emit('set-tool', 'select')"
      >
        <i class="bi-cursor" />
      </button>
      <button
        class="toolbar-btn"
        :class="{ 'is-active': toolMode === 'draw' }"
        title="Draw"
        @click="emit('set-tool', 'draw')"
      >
        <i class="bi-pencil" />
      </button>
      <button
        class="toolbar-btn"
        :class="{ 'is-active': toolMode === 'erase' }"
        title="Erase"
        @click="emit('set-tool', 'erase')"
      >
        <i class="bi-eraser" />
      </button>
    </div>
  </div>
</template>

<style lang="scss">
@use '@/styles/tool-panels-shared';

.midi-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 8px;
  background: var(--panel-bg);
  border-bottom: 1px solid var(--panel-border);
}

.toolbar-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 28px;
  min-width: 28px;
  padding: 0 6px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;

  &:hover {
    background: var(--panel-bg-hover);
  }

  &.is-active {
    background: var(--color-primary);
    color: #fff;
  }
}

.divider {
  width: 1px;
  height: 20px;
  margin: 0 4px;
  background: var(--panel-border);
}

.time-display {
  font-family: monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
  user-select: none;
}
</style>
