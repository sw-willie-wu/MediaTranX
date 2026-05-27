/**
 * useViewHost — registers a view handle in the view registry while mounted.
 *
 * Call from `<script setup>` inside each domain view (ImageView, VideoView,
 * AudioView, SettingsView, etc.).  The view owns its `currentFunction` ref
 * and exposes a setter; this composable simply wires the mount/unmount
 * lifecycle to the module-level viewRegistry Map.
 *
 * NOTE: KeepAlive is active in App.vue, but views re-register on every
 * onMounted (each :key="$route.fullPath" forces a fresh instance), so
 * onActivated/onDeactivated are intentionally omitted here.
 */
import { onMounted, onUnmounted } from 'vue'
import { viewRegistry, type ViewHandle } from '@/stores/viewRegistry'

export function useViewHost(viewId: string, handle: ViewHandle): void {
  onMounted(() => viewRegistry.register(viewId, handle))
  onUnmounted(() => viewRegistry.unregister(viewId))
}
