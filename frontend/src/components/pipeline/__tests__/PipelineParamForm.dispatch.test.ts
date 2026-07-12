/**
 * PipelineParamForm dispatcher 測試（統一參數元件案批 0 Task 0.7）。
 * dispatcher 規則：node.toolKey 有在 PARAM_COMPONENTS 註冊 → mount 參數元件；
 * 否則走既有 registry paramSchema 直出的 legacy 表單（過渡期漸次遷移）。
 *
 * 覆蓋 PARAM_COMPONENTS['video.cut'] 為同步 stub 元件（避免真拉 defineAsyncComponent
 * 包的 CutParams.vue，測試才能同步斷言、不必 await 元件載入）；'video.subtitle' 已於
 * 批 2 Task 2.5 註冊（SubtitleParams.vue）。
 *
 * legacy fallback 反例（test 3）策略改造（批 4 Task 4.1，dispatch 反例斷崖 finding）：
 * 批 4 遷完後 registry 每個 toolKey 都會有對應參數元件，天然找不到「已註冊但無元件」的
 * 反例。改為 beforeEach 主動 `delete PARAM_COMPONENTS['image.remove_bg']`／afterEach 還原
 * （存原值恢復——仿本檔既有 video.cut stub 手法），節點續用 image.remove_bg（registry 的
 * mode 欄位是非 advanced 的 enum，legacy 表單一定渲染 .app-select-trigger，斷言不受影響）。
 * 此後批 4 各工具遷移（含 image.remove_bg 自己日後遷移時）都不必再動這個測試檔。
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
// image.remove_bg 反例 fixture：存掛載時的原值（本測試檔執行當下可能已註冊、也可能尚未
// 註冊——batch 4 尚未遷到它），beforeEach 主動刪除、afterEach 依存值精準還原（有則放回、
// 無則保持刪除），確保本檔對其他測試檔的 PARAM_COMPONENTS 狀態零副作用。
const ORIGINAL_IMAGE_REMOVE_BG = PARAM_COMPONENTS['image.remove_bg']

beforeEach(() => {
  PARAM_COMPONENTS['video.cut'] = StubParamComponent
  delete PARAM_COMPONENTS['image.remove_bg']
})

afterEach(() => {
  PARAM_COMPONENTS['video.cut'] = ORIGINAL_VIDEO_CUT
  if (ORIGINAL_IMAGE_REMOVE_BG) {
    PARAM_COMPONENTS['image.remove_bg'] = ORIGINAL_IMAGE_REMOVE_BG
  } else {
    delete PARAM_COMPONENTS['image.remove_bg']
  }
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

// image.remove_bg：不論它是否已在 PARAM_COMPONENTS 註冊，beforeEach 都主動刪除該 entry
// （見上方 fixture），確保這裡走 legacy 分支。paramSchema 唯一欄位 mode 是非 advanced 的
// enum，確保 legacy 表單一定渲染 .app-select-trigger（image.compress/image.convert 等批 4
// 已遷工具全欄位皆 number/boolean/enum-with-visibleWhen 組合複雜，不適合當這個斷言的反例）。
const imageRemoveBgNode: RecipeNode = {
  id: 'n2',
  kind: 'tool',
  toolKey: 'image.remove_bg',
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

  it('3. toolKey 無參數元件（image.remove_bg）→ legacy 表單渲染、stub testid 不存在', () => {
    const w = mountForm(imageRemoveBgNode)
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
