/**
 * Toggle for the floating chat bubble.
 *
 * Default: hidden. The titlebar button is always visible and is the
 * only way to bring the bubble onto the page. State persists in
 * localStorage so the user's choice survives reloads.
 *
 * Singleton ref so the titlebar button and the ChatBubble component
 * read/write the same source of truth.
 */

import { ref, watch } from 'vue'

const LS_KEY = 'chat-bubble-visible'

function loadInitial(): boolean {
  try {
    const raw = localStorage.getItem(LS_KEY)
    if (raw === null) return false
    return raw === '1'
  } catch {
    return false
  }
}

export const bubbleVisible = ref<boolean>(loadInitial())

watch(bubbleVisible, (v) => {
  try {
    localStorage.setItem(LS_KEY, v ? '1' : '0')
  } catch {
    // quota / private mode — ignore; in-memory state still works
  }
})

export function toggleBubbleVisible(): void {
  bubbleVisible.value = !bubbleVisible.value
}
