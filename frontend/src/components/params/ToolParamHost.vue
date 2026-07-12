<script setup lang="ts">
/**
 * ToolParamHost — 工具頁側通用 host（統一參數元件 spec §6）。
 * 依 toolKey 懶載參數元件，統管 params state / file seeding / submit 分流 / agent 兩層 schema 合成。
 * 之後 27 個工具頁 panel 的共通職責全收斂於此；批 0 只有 video.cut 掛得上（PARAM_COMPONENTS/METAS 尚未補齊）。
 */
import { computed, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSubmitTask } from '@/composables/useSubmitTask'
import { useToast } from '@/composables/useToast'
import { useAgentPanelHost } from '@/composables/useAgentPanelHost'
import type { PanelFieldSchema, PanelAgentSchema } from '@/stores/panelRegistry'
import { PARAM_COMPONENTS, METAS } from './index'
import type { SubmitSpec, AgentCompositeField } from './types'

const props = defineProps<{
  toolKey: string
  panelId: string // 由掛載點傳入（panelIdFor），host 不自行推導
  fileId: string | null
  currentFileName: string
  isMultiSelect?: boolean
  fileInfo?: Record<string, unknown> | null
}>()
const emit = defineEmits<{ submit: [taskId: string] }>()

const { t } = useI18n()
const toast = useToast()
const { submitTask, isProcessing } = useSubmitTask()

// META 不存在 → dev 階段直接 throw（訊息含 toolKey，方便定位掛載點打錯 toolKey）
const meta = METAS[props.toolKey]
if (!meta) {
  throw new Error(`ToolParamHost: unknown toolKey "${props.toolKey}" (not registered in METAS)`)
}

// ─── params state ───────────────────────────────────────────────────────────
const params = ref<Record<string, unknown>>(meta.defaults())

function onParamsUpdate(p: Record<string, unknown>): void {
  params.value = p
}

// ─── file seeding：檔案載入/切換時把 fileInfo 衍生的初值 merge 進 params ──────
watch(
  () => props.fileInfo,
  (info) => {
    const patch = meta.seedOnFileChange?.(info ?? null, params.value)
    if (patch) params.value = { ...params.value, ...patch }
  },
  { immediate: true },
)

// ─── submit spec / execute ──────────────────────────────────────────────────
function getSubmitSpec(): SubmitSpec {
  return (
    meta.buildSubmit?.(params.value) ?? {
      apiPath: meta.apiPath,
      payload: { ...params.value },
      taskType: meta.taskType,
      labelKey: meta.labelKey,
    }
  )
}

async function execute(): Promise<{ task_id?: string }> {
  const errKey = meta.validate?.(params.value)
  if (errKey) {
    toast.show(t(errKey), { type: 'error', icon: 'bi-x-circle' })
    return {}
  }
  if (!props.fileId) return {}

  const spec = getSubmitSpec()
  const taskId = await submitTask(
    spec.apiPath,
    { file_id: props.fileId, ...spec.payload },
    t(spec.labelKey),
    spec.taskType,
    props.currentFileName,
  )
  if (taskId) emit('submit', taskId)
  return { task_id: taskId ?? undefined }
}

// ─── preflight：批 0 無 meta 宣告 modelRequirement，此路徑目前不會走到 ────────
async function preflight(): Promise<boolean> {
  const req = meta.modelRequirement?.(params.value)
  if (!req) return true
  // 批 1 Task 1.4/1.5 接 useModelGuard（現行下載引導）；本批先 warn 放行，不阻塞流程
  console.warn(
    `[ToolParamHost] toolKey="${props.toolKey}" 宣告了 modelRequirement，但 preflight 尚未接 useModelGuard（見批 1 Task 1.4/1.5）`,
  )
  return true
}

// ─── isDisabled / isLoading / outputFormat ─────────────────────────────────
const isLoading = isProcessing
const isDisabled = computed(
  () => !props.fileId || isProcessing.value || meta.validate?.(params.value) != null,
)
const outputFormat = computed<string | undefined>(() =>
  meta.downloadFormatField ? String(params.value[meta.downloadFormatField] ?? '') : undefined,
)

// ─── setField / setParams / resetToDefaults ────────────────────────────────
function setField(name: string, value: unknown): unknown {
  const c = composites.value.find((x) => x.name === name)
  if (c) {
    params.value = { ...params.value, ...c.set(String(value)) }
    return c.get(params.value)
  }

  const field = meta.schema.find((f) => f.name === name)
  if (!field) throw new Error(`ToolParamHost: unknown field "${name}"`)

  if (field.type === 'number') {
    const n = Number(value)
    if (!Number.isFinite(n)) return params.value[name] // 非有限數 → 回現值不寫
    params.value = { ...params.value, [name]: n }
    return n
  }
  if (field.type === 'boolean') {
    const b = Boolean(value)
    params.value = { ...params.value, [name]: b }
    return b
  }
  if (field.type === 'enum') {
    const opts = field.options ?? []
    if (!opts.includes(String(value))) return params.value[name] // 非法值 → 回現值不寫
    params.value = { ...params.value, [name]: value }
    return value
  }
  // string / dict / list：直寫
  params.value = { ...params.value, [name]: value }
  return value
}

function setParams(obj: Record<string, unknown>): void {
  params.value = { ...obj } // 整顆替換，未列欄位被清除
}

function resetToDefaults(): void {
  setParams(meta.defaults())
}

// ─── notify：host → 參數元件的 inbound 事件通道 ─────────────────────────────
// 選擇：透過掛載點的 template ref 呼叫參數元件 defineExpose 的 notify() 方法（若有）。
// 理由：參數元件本來就經 defineExpose 曝露方法給父層（Vue 慣例），比另建 provide/inject
// 事件匯流簡單且型別直觀；批 0 無使用者（唯一真實使用者是批 1 的 AudioCut trim range），
// 機制先備好、可測即可——測試以 stub 元件 defineExpose({ notify }) 驗證轉呼。
const paramComponentRef = ref<{ notify?: (channel: string, payload: unknown) => void } | null>(
  null,
)
function notify(channel: string, payload: unknown): void {
  paramComponentRef.value?.notify?.(channel, payload)
}

// ─── composite 註冊（model picker 等元件用 inject 回呼註冊覆蓋欄位） ─────────
const composites = ref<AgentCompositeField[]>([])
provide('registerComposite', (c: AgentCompositeField) => {
  composites.value.push(c)
  return () => {
    const idx = composites.value.findIndex((x) => x.name === c.name)
    if (idx !== -1) composites.value.splice(idx, 1)
  }
})

// ─── agentSchema：兩層合成（一般欄位 from meta.schema，覆蓋欄位由 composite 取代）──
const agentFields = computed<PanelFieldSchema[]>(() => {
  const covered = new Set(composites.value.flatMap((c) => c.covers))
  const base = meta.schema
    .filter((f) => !covered.has(f.name))
    .map((f) => ({
      name: f.name,
      type: (f.type === 'boolean' ? 'bool' : f.type === 'dict' || f.type === 'list' ? 'string' : f.type) as PanelFieldSchema['type'],
      ...(f.options ? { options: () => f.options! } : {}),
      ...(f.min !== undefined ? { min: f.min } : {}),
      ...(f.max !== undefined ? { max: f.max } : {}),
      ...(f.step !== undefined ? { step: f.step } : {}),
      ...(f.visibleWhen ? { visibleWhen: () => f.visibleWhen!(params.value) } : {}),
      ...(f.agentHint ? { description: f.agentHint } : {}),
    }))
  const comp = composites.value.map((c) => ({
    name: c.name,
    type: 'enum' as const,
    options: c.options,
  }))
  return [...base, ...comp]
})

function getCurrentValues(): Record<string, unknown> {
  const covered = new Set(composites.value.flatMap((c) => c.covers))
  const result: Record<string, unknown> = {}
  for (const key of Object.keys(params.value)) {
    if (!covered.has(key)) result[key] = params.value[key]
  }
  for (const c of composites.value) result[c.name] = c.get(params.value)
  return result
}

// agentSchema 選擇響應式包裝：PanelHandle.agentSchema 型別是 plain object（PanelAgentSchema），
// 非 getter 函式；useAgentPanelHost 在 onMounted 時把 handle 存進 module-level Map 一次，
// 之後 registry 端只是持有同一個物件參照。要讓 registry 讀到的 fields 跟著 composites 變動更新，
// 用「物件字面量的 accessor property（get fields()）」而非把 computed 展開成一次性陣列快照——
// 每次外部讀 handle.agentSchema.fields 時才觸發 computed getter，天然反映當下 composites/params。
// （若 PanelAgentSchema.fields 改型別為 () => PanelFieldSchema[] 會更直觀，但那是既有介面，
// 本 task 不得改動，故選相容的 accessor property 做法。）
const agentSchema: PanelAgentSchema = {
  panelId: props.panelId,
  get fields() {
    return agentFields.value
  },
  actions: [],
  // requiresConfirm/label 目前無 meta 欄位可查（ToolParamMeta 未宣告，見報告）；
  // 批 0 唯一在案例 video.cut 舊 panel 原值為 requiresConfirm:true，故採保守預設：
  // 一律 requiresConfirm:true（寧可多一次確認，不放過 GPU 任務誤觸）；label 借用
  // meta.labelKey（唯一可用的語意字串，沿用舊 panel「不轉譯、直傳 i18n key」的慣例）。
  execute: { requiresConfirm: true, label: meta.labelKey },
}

useAgentPanelHost(props.panelId, {
  agentSchema,
  getCurrentValues,
  setField,
  openField: () => {},
  execute,
  isMultiSelect: () => props.isMultiSelect ?? false,
})

defineExpose({
  execute,
  getParams: () => ({ ...params.value }),
  getSubmitSpec,
  isDisabled,
  isLoading,
  preflight,
  outputFormat,
  params, // 唯讀語意：勿直接改，走 setField/setParams（不做 readonly() 包裝以免解包歧義）
  setField,
  setParams,
  resetToDefaults,
  notify,
})
</script>

<template>
  <component
    :is="PARAM_COMPONENTS[props.toolKey]"
    ref="paramComponentRef"
    :params="params"
    :context="'tool'"
    :file-info="fileInfo ?? null"
    @update:params="onParamsUpdate"
  />
</template>
