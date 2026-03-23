/**
 * useModelOptions
 *
 * 合併本地模型 + 雲端啟用模型為 AppSelect 的分組選項。
 * - 只有本地模型時：平鋪（不顯示 group header）
 * - 有雲端模型時：分組顯示（本地端 / Ollama / OpenAI / Gemini）
 *
 * @param capability - 篩選雲端模型的能力標籤（'text' | 'vision' | 'tools'）
 * @param localOptions - 本地模型選項（ref 或 computed）
 */
import { computed, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRemoteModelStore } from '@/stores/remoteModels'
import type { SelectOption, SelectGroup, SelectItem } from '@/components/common/AppSelect.vue'

const _PROVIDER_LABELS: Record<string, string> = {
  ollama: 'Ollama',
  openai: 'OpenAI',
  gemini: 'Gemini',
}

export function useModelOptions(
  capability: string,
  localOptions: Ref<SelectOption[]>,
) {
  const { t } = useI18n()
  const remoteStore = useRemoteModelStore()

  const mergedOptions = computed<SelectItem[]>(() => {
    // 取得符合 capability 且啟用的雲端模型
    const remoteModels = remoteStore.byCapability(capability)

    // 沒有雲端模型：直接回傳本地（平鋪，AppSelect 會自動處理單 group）
    if (remoteModels.length === 0) {
      return localOptions.value
    }

    // 有雲端模型：分組
    const groups: SelectItem[] = []

    // 本地端 group
    if (localOptions.value.length > 0) {
      groups.push({
        group: t('settings.models.local'),
        options: localOptions.value,
      } as SelectGroup)
    }

    // 按 provider 分組雲端模型
    const byProvider = new Map<string, SelectOption[]>()
    for (const m of remoteModels) {
      const key = m.provider
      if (!byProvider.has(key)) byProvider.set(key, [])
      byProvider.get(key)!.push({
        value: `remote:${m.provider}:${m.connId}:${m.modelId}`,
        label: m.name,
      })
    }

    for (const [provider, opts] of byProvider) {
      groups.push({
        group: _PROVIDER_LABELS[provider] || provider,
        options: opts,
      } as SelectGroup)
    }

    return groups
  })

  return { mergedOptions }
}

/**
 * 解析選中的模型值
 * - 本地模型：直接回傳 value
 * - 雲端模型：value 格式為 "remote:provider:connId:modelId"
 */
export function parseModelValue(value: string): {
  isRemote: boolean
  provider?: string
  connId?: number
  modelId: string
} {
  if (typeof value === 'string' && value.startsWith('remote:')) {
    const parts = value.split(':')
    // remote:provider:connId:modelId (modelId 可能含 :)
    return {
      isRemote: true,
      provider: parts[1],
      connId: parseInt(parts[2], 10),
      modelId: parts.slice(3).join(':'),
    }
  }
  return { isRemote: false, modelId: value }
}
