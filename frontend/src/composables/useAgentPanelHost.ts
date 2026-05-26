/**
 * useAgentPanelHost — registers a panel handle in the panel registry.
 *
 * Call from `<script setup>` inside each agent-aware panel component.
 * The composable:
 *   - creates the `isMounted` reactive ref
 *   - merges it with the caller-supplied handle fields into a full PanelHandle
 *   - registers / unregisters in the module-level panelRegistry on lifecycle hooks
 *   - tracks KeepAlive activate/deactivate cycles so `isMounted` stays accurate
 *     (App.vue wraps views in <KeepAlive>, so panels inside views may be
 *     deactivated rather than unmounted when switching routes)
 */
import { onMounted, onActivated, onDeactivated, onUnmounted, ref } from 'vue'
import { panelRegistry, type PanelHandle } from '@/stores/panelRegistry'

export function useAgentPanelHost(
  panelId: string,
  handle: Omit<PanelHandle, 'isMounted'>,
): void {
  const isMounted = ref(false)
  const fullHandle: PanelHandle = { ...handle, isMounted }

  onMounted(() => {
    isMounted.value = true
    panelRegistry.register(panelId, fullHandle)
  })

  onActivated(() => {
    isMounted.value = true
  })

  onDeactivated(() => {
    isMounted.value = false
  })

  onUnmounted(() => {
    isMounted.value = false
    panelRegistry.unregister(panelId)
  })
}
