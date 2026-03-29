<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import type { VideoMediaInfo } from '@/composables/useVideoWorkspace'

const props = defineProps<{
  previewUrl: string | null
  mediaInfo: VideoMediaInfo | null
  currentFunction: string
  startTime: string
  endTime: string
}>()

const emit = defineEmits<{
  'update:startTime': [v: string]
  'update:endTime': [v: string]
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const trackRef = ref<HTMLDivElement | null>(null)
const dragging = ref<'start' | 'end' | null>(null)
const playheadPercent = ref(0)

function parseTimeToSeconds(time: string): number {
  const parts = time.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return Number(time) || 0
}

function secondsToTimeString(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

const startPercent = computed(() => {
  if (!props.mediaInfo) return 0
  return (parseTimeToSeconds(props.startTime) / props.mediaInfo.duration) * 100
})

const endPercent = computed(() => {
  if (!props.mediaInfo) return 100
  return (parseTimeToSeconds(props.endTime) / props.mediaInfo.duration) * 100
})

const selectionStyle = computed(() => ({
  left: startPercent.value + '%',
  width: (endPercent.value - startPercent.value) + '%',
}))

function startDrag(handle: 'start' | 'end', e: MouseEvent | TouchEvent) {
  dragging.value = handle
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
  document.addEventListener('touchmove', onDragMove)
  document.addEventListener('touchend', onDragEnd)
}

function onDragMove(e: MouseEvent | TouchEvent) {
  if (!dragging.value || !trackRef.value || !props.mediaInfo) return
  const rect = trackRef.value.getBoundingClientRect()
  const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
  const percent = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
  const seconds = (percent / 100) * props.mediaInfo.duration

  if (dragging.value === 'start') {
    const endSec = parseTimeToSeconds(props.endTime)
    emit('update:startTime', secondsToTimeString(Math.min(seconds, endSec - 1)))
  } else {
    const startSec = parseTimeToSeconds(props.startTime)
    emit('update:endTime', secondsToTimeString(Math.max(seconds, startSec + 1)))
  }

  if (videoRef.value) videoRef.value.currentTime = seconds
}

function onDragEnd() {
  dragging.value = null
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  document.removeEventListener('touchmove', onDragMove)
  document.removeEventListener('touchend', onDragEnd)
}

function onTrackMouseDown(e: MouseEvent) {
  if (!trackRef.value || !props.mediaInfo) return
  const rect = trackRef.value.getBoundingClientRect()
  const percent = ((e.clientX - rect.left) / rect.width) * 100
  const seconds = (percent / 100) * props.mediaInfo.duration
  if (videoRef.value) videoRef.value.currentTime = seconds
}

function onTrackTouchStart(e: TouchEvent) {
  if (!trackRef.value || !props.mediaInfo) return
  const rect = trackRef.value.getBoundingClientRect()
  const percent = ((e.touches[0].clientX - rect.left) / rect.width) * 100
  const seconds = (percent / 100) * props.mediaInfo.duration
  if (videoRef.value) videoRef.value.currentTime = seconds
}

function onVideoTimeUpdate() {
  if (!videoRef.value || !props.mediaInfo) return
  playheadPercent.value = (videoRef.value.currentTime / props.mediaInfo.duration) * 100
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
  document.removeEventListener('touchmove', onDragMove)
  document.removeEventListener('touchend', onDragEnd)
})

</script>

<template>
  <div class="preview-display">
    <div class="video-wrapper">
      <div class="video-container">
        <video
          ref="videoRef"
          :src="previewUrl ?? undefined"
          controls
          class="video-player"
          @timeupdate="onVideoTimeUpdate"
        />
        <div v-if="currentFunction === 'cut' && mediaInfo" class="cut-timeline">
          <div
            ref="trackRef"
            class="timeline-track"
            @mousedown="onTrackMouseDown"
            @touchstart.prevent="onTrackTouchStart"
          >
            <div class="timeline-selection" :style="selectionStyle" />
            <div
              class="timeline-handle start"
              :style="{ left: startPercent + '%' }"
              @mousedown.stop="startDrag('start', $event)"
              @touchstart.stop.prevent="startDrag('start', $event)"
            />
            <div
              class="timeline-handle end"
              :style="{ left: endPercent + '%' }"
              @mousedown.stop="startDrag('end', $event)"
              @touchstart.stop.prevent="startDrag('end', $event)"
            />
            <div class="timeline-playhead" :style="{ left: playheadPercent + '%' }" />
            <div class="timeline-times">
              <span :style="{ left: startPercent + '%' }">{{ startTime }}</span>
              <span :style="{ left: endPercent + '%' }">{{ endTime }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<style lang="scss" scoped>
.preview-display {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.video-wrapper {
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}

.video-container {
  position: relative;
  display: flex;
  max-width: 100%;
  max-height: 100%;
  overflow: visible;
}

.video-player {
  display: block;
  max-width: 100%;
  max-height: 100%;
}

.cut-timeline {
  position: absolute;
  bottom: 12px;
  left: 0;
  right: 0;
  padding: 0 calc(0.75rem + 2px);
  z-index: 3;
}

.timeline-times {
  position: absolute;
  left: 0;
  right: 0;
  top: 100%;
  margin-top: 4px;

  span {
    position: absolute;
    font-size: 0.85rem;
    color: var(--text-primary);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    transform: translateX(-50%);
  }
}

.timeline-track {
  position: relative;
  height: 20px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  cursor: pointer;
}

.timeline-selection {
  position: absolute;
  top: 0;
  height: 100%;
  background: rgba(124, 111, 173, 0.4);
  border-radius: 4px;
  pointer-events: none;
}

.timeline-handle {
  position: absolute;
  top: -2px;
  width: 6px;
  height: 24px;
  background: var(--color-primary);
  border-radius: 3px;
  cursor: ew-resize;
  transform: translateX(-50%);
  z-index: 2;
  transition: background 0.15s ease;

  &:hover, &:active {
    background: var(--color-accent);
    box-shadow: 0 0 8px rgba(124, 111, 173, 0.6);
  }
}

.timeline-playhead {
  position: absolute;
  top: 0;
  width: 2px;
  height: 100%;
  background: rgba(255, 255, 255, 0.7);
  pointer-events: none;
  z-index: 1;
  transform: translateX(-50%);
}
</style>
