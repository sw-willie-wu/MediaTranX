import { ref, computed } from 'vue'
import type { VideoMediaInfo } from './useVideoWorkspace'

export function useVideoCutTimeline(mediaInfo: Readonly<{ value: VideoMediaInfo | null }>) {
  const trackRef = ref<HTMLDivElement | null>(null)
  const videoRef = ref<HTMLVideoElement | null>(null)
  const dragging = ref<'start' | 'end' | null>(null)
  const playheadPercent = ref(0)

  const cutStartTime = ref('00:00:00')
  const cutEndTime = ref('00:00:00')
  const cutStreamCopy = ref(true)

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

  function initEndTime() {
    if (mediaInfo.value) {
      cutEndTime.value = secondsToTimeString(mediaInfo.value.duration)
    }
  }

  const startPercent = computed(() => {
    if (!mediaInfo.value) return 0
    return (parseTimeToSeconds(cutStartTime.value) / mediaInfo.value.duration) * 100
  })

  const endPercent = computed(() => {
    if (!mediaInfo.value) return 100
    return (parseTimeToSeconds(cutEndTime.value) / mediaInfo.value.duration) * 100
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
    if (!dragging.value || !trackRef.value || !mediaInfo.value) return
    const rect = trackRef.value.getBoundingClientRect()
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
    const percent = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100))
    const seconds = (percent / 100) * mediaInfo.value.duration

    if (dragging.value === 'start') {
      const endSec = parseTimeToSeconds(cutEndTime.value)
      cutStartTime.value = secondsToTimeString(Math.min(seconds, endSec - 1))
    } else {
      const startSec = parseTimeToSeconds(cutStartTime.value)
      cutEndTime.value = secondsToTimeString(Math.max(seconds, startSec + 1))
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
    if (!trackRef.value || !mediaInfo.value) return
    const rect = trackRef.value.getBoundingClientRect()
    const percent = ((e.clientX - rect.left) / rect.width) * 100
    const seconds = (percent / 100) * mediaInfo.value.duration
    if (videoRef.value) videoRef.value.currentTime = seconds
  }

  function onTrackTouchStart(e: TouchEvent) {
    if (!trackRef.value || !mediaInfo.value) return
    const rect = trackRef.value.getBoundingClientRect()
    const percent = ((e.touches[0].clientX - rect.left) / rect.width) * 100
    const seconds = (percent / 100) * mediaInfo.value.duration
    if (videoRef.value) videoRef.value.currentTime = seconds
  }

  function onVideoTimeUpdate() {
    if (!videoRef.value || !mediaInfo.value) return
    playheadPercent.value = (videoRef.value.currentTime / mediaInfo.value.duration) * 100
  }

  function cleanup() {
    document.removeEventListener('mousemove', onDragMove)
    document.removeEventListener('mouseup', onDragEnd)
    document.removeEventListener('touchmove', onDragMove)
    document.removeEventListener('touchend', onDragEnd)
  }

  return {
    trackRef,
    videoRef,
    cutStartTime,
    cutEndTime,
    cutStreamCopy,
    startPercent,
    endPercent,
    selectionStyle,
    playheadPercent,
    initEndTime,
    startDrag,
    onTrackMouseDown,
    onTrackTouchStart,
    onVideoTimeUpdate,
    cleanup,
  }
}
