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
import { useModelStore } from '@/stores/models'
import { useModelGuard } from '@/composables/useModelGuard'
import type { PanelFieldSchema, PanelAgentSchema } from '@/stores/panelRegistry'
import { PARAM_COMPONENTS, METAS } from './index'
import { isModelInstalled } from './modelGuardUtils'
import type { SubmitSpec, AgentCompositeField } from './types'

const props = defineProps<{
  toolKey: string
  panelId: string // 由掛載點傳入（panelIdFor），host 不自行推導
  fileId: string | null
  currentFileName: string
  isMultiSelect?: boolean
  fileInfo?: Record<string, unknown> | null
  /**
   * 選配：覆蓋 getSubmitSpec().labelKey（連帶覆蓋 execute() 送出任務的顯示名稱）。
   * 首用場景（批 4 Task 4.2）：image.filter 同 tool-key 掛兩次（adjust/filter 兩個 panelId），
   * 共用一份 META（meta.labelKey 固定 'image.filter.task_label'）——adjust 掛載點傳
   * label-key='image.adjust.task_label' 才能讓工具頁單筆執行/批次 submitToAll 的任務名稱
   * 正確顯示「圖片 · 調整」而非「圖片 · 濾鏡」；filter 掛載點不傳，沿 meta.labelKey 原值。
   */
  labelKey?: string
  /**
   * 選配：覆蓋 agentSchema.execute.label（agent 執行時顯示的動作標籤，經 useAgentState.ts:90
   * 真實轉發給 agent）。鏡射上面 labelKey prop 的分流模式——首用場景（批 4 Task 4.2 修復）：
   * image.filter 同 tool-key 掛兩次（adjust/filter 兩個 panelId），META 只有單一
   * meta.agentExecuteLabel（未設，退回 meta.labelKey 'image.filter.task_label'），兩掛載點的
   * agent 執行標籤因此塌成同一個「圖片 · 濾鏡」；舊 per-panel 標籤 'panel.adjust.execute'
   * （套用調整）/'panel.filter.execute'（套用濾鏡）改由掛載點各自傳這個 prop 復原。
   */
  agentExecuteLabel?: string
}>()
const emit = defineEmits<{ submit: [taskId: string] }>()

// 副檔名 guard 的警示 div 讓 template 變 fragment → 關閉自動 attr 繼承；顯式接管 $attrs
// 轉發到子參數元件（crop 覆蓋層 props/OCR persist-key/adjust field-group 等靠此 fallthrough）。
defineOptions({ inheritAttrs: false })

const { t } = useI18n()
const toast = useToast()
const { submitTask, isProcessing } = useSubmitTask()
const modelStore = useModelStore()
const { guardModelReady } = useModelGuard()

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
  const spec = meta.buildSubmit?.(params.value) ?? {
    apiPath: meta.apiPath,
    payload: { ...params.value },
    taskType: meta.taskType,
    labelKey: meta.labelKey,
  }
  // props.labelKey 選配覆蓋（見 props 型別註解）；execute() 內部也讀 spec.labelKey，故此處
  // 覆蓋同時涵蓋「批次 getSubmitSpec() 呼叫端」與「單筆 execute() 送出的任務顯示名稱」兩處。
  return props.labelKey ? { ...spec, labelKey: props.labelKey } : spec
}

async function execute(): Promise<{ task_id?: string }> {
  // 執行順序沿 spec §6：META.validate → modelRequirement × useModelGuard → buildSubmit → submitTask
  const errKey = meta.validate?.(params.value)
  if (errKey) {
    toast.show(t(errKey), { type: 'error', icon: 'bi-x-circle' })
    return {}
  }
  if (!(await preflight())) return {}
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

// ─── preflight：modelRequirement × useModelGuard（批 1 Task 1.5 接線）──────────
// slot → 設定頁「模型與資源下載」分類 tab 對照（沿各舊 panel 硬編 category 字面值；
// 例如舊 DocumentTranslatePanel 傳 'llm'）。slot 是 modelRequirement 的語意識別（未來
// GPU VRAM 協調也用得到），與設定頁 tab 分類是兩件事，故此處另建對照表、非直接複用 slot。
// 首用 translate→llm；批 2 Task 2.3 補 interpolate→video（舊 VideoInterpolatePanel.preflight
// 傳 'video'）、enhance→image（舊 VideoEnhancePanel.preflight 傳 'image'，realesrgan 屬影像 tab）；
// 批 2 Task 2.4 補 whisper/separate/align→audio、llm/vlm→llm（舊 VideoSummaryPanel.preflight
// 五道 guard 依序皆傳 'audio'/'llm'，見該檔 preflight()）。批 3 Task 3.4 補
// summarize→llm（舊 AudioTranscribePanel.execute() 的 summarize guard 傳 'llm'，見
// transcribe.meta.ts modelRequirements 註解）。批 4 Task 4.4 補 upscale→image（舊
// ImageUpscalePanel.execute() guardModelReady 傳 'image'；face_restore 第二道需求沿用同一
// slot 'upscale'，見 upscale.meta.ts modelRequirements 註解）、ocr→llm（舊
// ImageOcrPanel/DocumentOcrPanel.execute() guardModelReady 皆傳 'llm'）。
const SLOT_GUARD_CATEGORY: Record<string, string> = {
  translate: 'llm',
  interpolate: 'video',
  enhance: 'image',
  whisper: 'audio',
  separate: 'audio',
  align: 'audio',
  llm: 'llm',
  vlm: 'llm',
  summarize: 'llm',
  upscale: 'image',
  ocr: 'llm',
}

// 複數模型需求逐一過 guard（批 2 Task 2.4 host 擴充）：meta.modelRequirements 優先於單數
// meta.modelRequirement（兩者互斥——同一 META 不應兩者並設，若都設則以複數為準）；單數
// 存在時包成單元素陣列走同一迴圈，行為與批 1 完全相容。逐一檢查、第一個未就緒即回傳
// false（導航到該 slot 對應分類 tab）並中止後續檢查——沿舊 VideoSummaryPanel.preflight
// 的「依序 guard、第一個卡住就 return」語意。
async function preflight(): Promise<boolean> {
  const plural = meta.modelRequirements?.(params.value)
  const singular = meta.modelRequirement?.(params.value)
  const reqs = plural ?? (singular ? [singular] : [])
  for (const req of reqs) {
    const ready = isModelInstalled(modelStore.models, req)
    if (!(await guardModelReady(ready, SLOT_GUARD_CATEGORY[req.slot] ?? req.slot))) return false
  }
  return true
}

// ─── 副檔名 guard（v1.7.1 F）────────────────────────────────────────────────
// META 未設 supportedExts 的工具零行為變化（formatUnsupported 恆 false）。
const currentExt = computed(() => {
  const name = props.currentFileName
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i + 1).toLowerCase() : ''
})
const formatUnsupported = computed(
  () => !!props.fileId && !!meta.supportedExts && !meta.supportedExts.includes(currentExt.value),
)

// ─── isDisabled / isLoading / outputFormat ─────────────────────────────────
const isLoading = isProcessing
const isDisabled = computed(
  () => !props.fileId || isProcessing.value || formatUnsupported.value || meta.validate?.(params.value) != null,
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
    // dict/list 欄位不進 agent 面板欄位——scalar set_field 無法表達；agent 要用 dict 走
    // create_pipeline（字串硬塞進 dict 欄位會讓後端 422）。這些欄位仍留在 meta.schema／
    // params 全集裡，只是不曝光給 agent 的 set_field 介面；getCurrentValues／execute
    // payload 不受影響，工具頁 UI（textarea 等）照常可編輯。
    .filter((f) => f.type !== 'dict' && f.type !== 'list')
    .map((f) => ({
      name: f.name,
      type: (f.type === 'boolean' ? 'bool' : f.type) as PanelFieldSchema['type'],
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
  // requiresConfirm 批 0 起固定 true（寧可多一次確認，不放過 GPU 任務誤觸）；label 預設借用
  // meta.labelKey，但 interpolate/enhance 等舊 panel 的 agentSchema.execute.label 是獨立字串
  // （'panel.interpolate.execute' ≠ 'video.interpolate.task_label'）——第一個不同者出現時
  // （批 2 Task 2.3）加 meta.agentExecuteLabel 選配欄位承接，未設時退回 labelKey（既有工具不變）。
  // requiresConfirm 第一個不同者是 audio.volume（批 3 Task 3.1）——舊 AudioVolumePanel.agentSchema
  // .execute.requiresConfirm 為 false（音量調整非破壞性/低風險，免二次確認）；加
  // meta.agentRequiresConfirm 選配欄位承接，未設時退回 true（既有工具不變）。
  execute: {
    requiresConfirm: meta.agentRequiresConfirm ?? true,
    // props.agentExecuteLabel 選配覆蓋（見 props 型別註解）優先於 meta 兩層 fallback。
    label: props.agentExecuteLabel ?? meta.agentExecuteLabel ?? meta.labelKey,
  },
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
  <div v-if="formatUnsupported" class="info-box info-box--warn">
    <i class="bi bi-info-circle"></i>
    <span>{{ t(`${props.toolKey}.format_not_supported`) }}</span>
  </div>
  <component
    :is="PARAM_COMPONENTS[props.toolKey]"
    ref="paramComponentRef"
    v-bind="$attrs"
    :params="params"
    :context="'tool'"
    :file-info="fileInfo ?? null"
    @update:params="onParamsUpdate"
  />
</template>

<style scoped>
@use '@/styles/tool-panels-shared';
/* 共用 .info-box 不帶 margin——與參數元件間留距 */
.info-box { margin-bottom: 0.75rem; }
</style>
