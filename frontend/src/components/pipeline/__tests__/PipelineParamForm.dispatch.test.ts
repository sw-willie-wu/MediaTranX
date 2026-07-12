/**
 * PipelineParamForm dispatcher 測試（統一參數元件案批 0 Task 0.7）。
 * dispatcher 規則：node.toolKey 有在 PARAM_COMPONENTS 註冊 → mount 參數元件；
 * 否則走既有 registry paramSchema 直出的 legacy 表單（過渡期漸次遷移）。
 *
 * 覆蓋 PARAM_COMPONENTS['video.cut'] 為同步 stub 元件（避免真拉 defineAsyncComponent
 * 包的 CutParams.vue，測試才能同步斷言、不必 await 元件載入）；'video.enhance'
 * 未在 PARAM_COMPONENTS 中註冊（批 1 Task 1.2 起 video.transcode 已註冊，改用
 * video.enhance 天然驗證 legacy fallback 路徑；paramSchema 含 enum 欄位以維持
 * .app-select-trigger 斷言有意義）。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, type PropType } from 'vue'
import type { RecipeNode } from '@/pipeline/types'
import { PARAM_COMPONENTS } from '@/components/params'

// ─── vue-i18n mock（沿用既有慣例：t 回傳 key 本身） ──────────────────────────
import { vi } from 'vitest'
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (k: string) => k }),
}))

import PipelineParamForm from '@/components/pipeline/PipelineParamForm.vue'

// ─── stub 參數元件（testid 可辨識、emit update:params 可驗轉呼） ────────────
const StubParamComponent = defineComponent({
  name: 'StubParamComponent',
  props: {
    params: { type: Object as PropType<Record<string, unknown>>, required: true },
    context: { type: String, required: true },
    fileInfo: { type: null as unknown as PropType<Record<string, unknown> | null>, default: null },
  },
  emits: ['update:params'],
  setup(props, { emit }) {
    return () =>
      h(
        'button',
        {
          'data-testid': 'stub-param-component',
          onClick: () => emit('update:params', { start_time: 9 }),
        },
        `stub:${props.context}`,
      )
  },
})

// 保留原 PARAM_COMPONENTS['video.cut']（真 async 元件），測試結束後還原，
// 避免污染同進程跑的其他測試檔（module-level singleton）。
const ORIGINAL_VIDEO_CUT = PARAM_COMPONENTS['video.cut']

beforeEach(() => {
  PARAM_COMPONENTS['video.cut'] = StubParamComponent
})

afterEach(() => {
  PARAM_COMPONENTS['video.cut'] = ORIGINAL_VIDEO_CUT
})

function mountForm(node: RecipeNode, preview?: boolean) {
  return mount(PipelineParamForm, {
    props: { node, ...(preview !== undefined ? { preview } : {}) },
    global: {
      mocks: { $t: (k: string) => k },
    },
  })
}

const cutNode: RecipeNode = {
  id: 'n1',
  kind: 'tool',
  toolKey: 'video.cut',
  params: { start_time: 5 },
}

const enhanceNode: RecipeNode = {
  id: 'n2',
  kind: 'tool',
  toolKey: 'video.enhance',
  params: {},
}

const inputNode: RecipeNode = {
  id: 'n3',
  kind: 'input',
  params: {},
}

describe('PipelineParamForm — dispatcher', () => {
  it('1. toolKey 有參數元件（video.cut）→ 渲染 stub 元件、legacy 欄位段不存在', () => {
    const w = mountForm(cutNode)
    expect(w.find('[data-testid="stub-param-component"]').exists()).toBe(true)
    // legacy 欄位段（非 keep-output 的 form-group）不應存在
    expect(w.findAll('.form-group:not(.keep-output)').length).toBe(0)
    expect(w.find('.app-select-trigger').exists()).toBe(false)
  })

  it('2. stub 元件 emit update:params → PipelineParamForm 原樣轉發 update-params', async () => {
    const w = mountForm(cutNode)
    await w.find('[data-testid="stub-param-component"]').trigger('click')
    expect(w.emitted('update-params')).toEqual([[{ start_time: 9 }]])
  })

  it('3. toolKey 無參數元件（video.enhance）→ legacy 表單渲染、stub testid 不存在', () => {
    const w = mountForm(enhanceNode)
    expect(w.find('[data-testid="stub-param-component"]').exists()).toBe(false)
    expect(w.find('.app-select-trigger').exists()).toBe(true)
  })

  it('4. dispatcher 路徑 + preview=true → 顯示 preview_hint、keep-output/remove 不渲染', () => {
    const w = mountForm(cutNode, true)
    expect(w.text()).toContain('pipeline.preview_hint')
    expect(w.find('.keep-output').exists()).toBe(false)
    expect(w.find('.remove-btn').exists()).toBe(false)
  })

  it('5. dispatcher 路徑 + preview 未設 → keep-output checkbox 與 remove 鈕存在', () => {
    const w = mountForm(cutNode)
    expect(w.find('.keep-output input[type="checkbox"]').exists()).toBe(true)
    expect(w.find('.remove-btn').exists()).toBe(true)
  })

  it('6. node.kind === "input" → input hint 分支不受影響（不進 dispatcher/legacy 任一路徑）', () => {
    const w = mountForm(inputNode)
    expect(w.text()).toContain('pipeline.input_node_hint')
    expect(w.find('[data-testid="stub-param-component"]').exists()).toBe(false)
    expect(w.find('.app-select-trigger').exists()).toBe(false)
  })
})
