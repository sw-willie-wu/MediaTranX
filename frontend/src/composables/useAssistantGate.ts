import { useRouter } from 'vue-router'
import { useAgentSettingsStore } from '@/stores/agentSettings'

/**
 * 開啟智慧助手前的「無模型」守門。
 *
 * 沒選模型時助手其實不能用（送出會後端失敗），與其開一個空對話，
 * 不如把使用者導去設定的「智慧助手」分頁先選模型。
 *
 * 注意：內部用 `useRouter()`，只能在元件 setup 內呼叫（呼叫端：TitlebarChatBubbleButton、ChatBubble）。
 */
export function useAssistantGate() {
  const router = useRouter()
  const settings = useAgentSettingsStore()

  /**
   * @returns true 表示已攔截（導向設定），呼叫端應中止原本的開啟/展開動作；
   *          false 表示有模型，照常開啟。
   */
  function redirectIfNoModel(): boolean {
    if (!settings.modelChoice) {
      void router.push({ path: '/settings', query: { tab: 'agent' } })
      return true
    }
    return false
  }

  return { redirectIfNoModel }
}
