/**
 * image.filter 參數 META（統一參數元件 spec §4；批 4 Task 4.2 ⭐合併 task）。
 * schema 準繩＝後端 ImageFilterRequest（backend/app/api/routes/image/filter.py）11 欄全集：
 * brightness/contrast/saturation/hue/sharpness/warmth（舊 image.adjust）＋
 * grayscale/sepia/invert/blur/vignette（舊 image.filter）（file_id/suppress_results 由 host 注入）。
 *
 * ⭐ 合併裁決（batch4-recon.md §3／Surprise 3，批 4 最大結構決策）：兩個舊 panel
 * （ImageAdjustPanel/ImageFilterPanel）打同一後端 /image/filter、registry 只有一條
 * image.filter（11 欄聯集）。本 task 合併為單一 META＋單一 FilterParams.vue，
 * ImageView 同 tool-key 掛兩個 <ToolParamHost>（panel-id 分別沿舊 'image.adjust'/
 * 'image.filter'，host 用 props.panelId 當 useAgentPanelHost 鍵——雙 agent 面板保留）。
 *
 * min/max/step/default 逐欄沿 registry 現值（= 後端尺度，非 UI 尺度）：
 * brightness/contrast/saturation/sharpness：0~3，step 0.05，default 1.0（UI 0-300%）
 * hue：-180~180，step 1，default 0（UI 度數，原值直傳，無尺度轉換）
 * warmth：-1~1，step 0.05，default 0（UI -100~100，/100 轉換）
 * grayscale/sepia/invert/vignette：0~1，step 0.05，default 0（UI 0-100%，/100 轉換）
 * blur：0~100，step 0.5，default 0（UI px 直傳，UI 滑桿沿舊 panel 侷限 0-20，見
 * FilterParams.vue；後端/registry 上限較寬，UI 保守值不影響 schema 本身）
 *
 * agentRequiresConfirm=false：舊 ImageAdjustPanel／ImageFilterPanel 的 agentSchema.execute
 * 皆為 { requiresConfirm: false }（CPU-only、非破壞性可逆調整），合併後兩個 panelId 沿用同一
 * 語意，故設在共用 META 上。
 *
 * ✅（批 4 Task 4.2 修復）agentExecuteLabel per-panel 分流：上述 concern 已解——ToolParamHost
 * 新增 props.agentExecuteLabel 選配欄位（鏡射 labelKey prop 分流模式），ImageView 的 adjust/
 * filter 兩掛載點各自傳 agent-execute-label="panel.adjust.execute"/"panel.filter.execute"
 * 復原舊 per-panel 動作標籤（不再塌成共用 meta.labelKey 'image.filter.task_label'）。本 META
 * 仍不設 agentExecuteLabel（META 層級欄位無法表達 per-panel 差異，覆蓋改在掛載點做）。
 *
 * ⭐ 曝露面變化（Surprise 3 附帶決策，接受並記報告）：舊兩 panel 的 agentSchema.fields 各自只有
 * 6/5 欄；合併後兩個 panelId 的 agent 面板皆透過 host 衍生 meta.schema 全 11 欄曝出（agent 可
 * 透過任一 panelId 呼叫另一半欄位的 set_field）。
 *
 * FilterPreview WebGL 即時預覽的 UI↔後端尺度轉換與「自己組值＋另一組中性值」組裝邏輯在
 * FilterParams.vue（依 fieldGroup 分流），本 META 不參與（meta 禁止 import Vue/元件）。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'image.filter',
  apiPath: '/image/filter',
  labelKey: 'image.filter.task_label',
  taskType: 'image.filter',
  schema: [
    { name: 'brightness', type: 'number', min: 0, max: 3, step: 0.05, default: 1.0 },
    { name: 'contrast', type: 'number', min: 0, max: 3, step: 0.05, default: 1.0 },
    { name: 'saturation', type: 'number', min: 0, max: 3, step: 0.05, default: 1.0 },
    { name: 'hue', type: 'number', min: -180, max: 180, step: 1, default: 0 },
    { name: 'sharpness', type: 'number', min: 0, max: 3, step: 0.05, default: 1.0 },
    { name: 'warmth', type: 'number', min: -1, max: 1, step: 0.05, default: 0 },
    { name: 'grayscale', type: 'number', min: 0, max: 1, step: 0.05, default: 0 },
    { name: 'sepia', type: 'number', min: 0, max: 1, step: 0.05, default: 0 },
    { name: 'invert', type: 'number', min: 0, max: 1, step: 0.05, default: 0 },
    { name: 'blur', type: 'number', min: 0, max: 100, step: 0.5, default: 0 },
    { name: 'vignette', type: 'number', min: 0, max: 1, step: 0.05, default: 0 },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  agentRequiresConfirm: false,
  multiSelect: true,
}
