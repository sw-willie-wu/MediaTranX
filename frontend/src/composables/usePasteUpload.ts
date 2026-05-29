/**
 * usePasteUpload — adds clipboard-paste as a third file-ingest entry point
 * (alongside drag-drop and click-select).
 *
 * Supports two clipboard sources:
 *   (a) image blobs (screenshots / copied images) → renamed pasted-image-*.ext
 *   (b) files copied in the OS file manager (clipboardData.files)
 *
 * Pasted content has no source path (Chromium strips File.path), so it
 * always flows through the HTTP-upload path (sourceDir undefined). That is
 * inherent and acceptable — see spec §2.
 *
 * Guards (skip + let native paste happen):
 *   1. focus is in an editable element (INPUT/TEXTAREA/SELECT/contenteditable)
 *   2. the agent chat panel is open (bubbleExpanded)
 *
 * The decision logic is a pure function (resolvePaste) for testability;
 * the composable only wires it to the window 'paste' event + lifecycle.
 */
import { onActivated, onDeactivated } from 'vue'
import { bubbleExpanded } from '@/composables/useBubbleVisibility'

const MIME_EXT: Record<string, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
  'image/bmp': 'bmp',
  'image/gif': 'gif',
}

export function mimeToExt(mime: string): string {
  return MIME_EXT[mime] ?? 'png'
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

export function pastedImageName(mime: string, date: Date): string {
  const ts =
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}` +
    `-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
  return `pasted-image-${ts}.${mimeToExt(mime)}`
}

export function isEditableTarget(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName
  // Mirror AppFilmstrip.vue:37-39 precedent (INPUT/TEXTAREA/SELECT + isContentEditable).
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if ((el as HTMLElement).isContentEditable) return true
  return false
}

/** Pull File[] from a paste event: copied files first, else image blobs. */
export function extractClipboardFiles(e: ClipboardEvent): File[] {
  const dt = e.clipboardData
  if (!dt) return []
  // OS-copied files already have real names — return as-is, NEVER rename.
  if (dt.files && dt.files.length > 0) return Array.from(dt.files)

  // Image blobs (screenshots) have no name — rename only in THIS branch.
  const out: File[] = []
  const items = dt.items
  if (items) {
    for (let i = 0; i < items.length; i++) {
      const it = items[i]
      if (it.kind === 'file' && it.type.startsWith('image/')) {
        const blob = it.getAsFile()
        if (blob) {
          out.push(new File([blob], pastedImageName(it.type, new Date()), { type: it.type }))
        }
      }
    }
  }
  return out
}

/** Pure decision: returns File[] to ingest, or null to ignore the paste. */
export function resolvePaste(
  e: ClipboardEvent,
  opts: { expanded: boolean; activeElement: Element | null },
): File[] | null {
  if (opts.expanded) return null
  if (isEditableTarget(opts.activeElement)) return null
  const files = extractClipboardFiles(e)
  return files.length > 0 ? files : null
}

/**
 * Wire window 'paste' → onPaste(files). Active only while the host page is
 * the current (visible) route. Mirrors usePendingFileListener: uses ONLY
 * onActivated/onDeactivated. App.vue wraps <RouterView> in <KeepAlive>, so
 * both call sites (ToolLayout, HomeView) receive activate/deactivate; this
 * also prevents simultaneously-cached tool pages from double-firing. No
 * onMounted/onUnmounted needed.
 */
export function usePasteUpload(onPaste: (files: File[]) => void): void {
  function handler(e: ClipboardEvent): void {
    // resolvePaste is fully synchronous — no await before preventDefault,
    // or preventDefault would no-op and the browser may also paste text.
    const files = resolvePaste(e, {
      expanded: bubbleExpanded.value,
      activeElement: document.activeElement,
    })
    if (!files) return
    e.preventDefault()
    onPaste(files)
  }
  onActivated(() => window.addEventListener('paste', handler))
  onDeactivated(() => window.removeEventListener('paste', handler))
}
