/**
 * image.upscale 參數 META（統一參數元件 spec §4；批 4 Task 4.4）。
 * schema 準繩＝後端 ImageUpscaleRequest 全集（backend/app/api/routes/image/upscale.py）。
 *
 * ⚠ modelRequirement 用 id 型比對（modelGuardUtils.ts 批 4 Task 4.4 新增的第四種比對形狀）：
 * 後端 model_id/face_restore_model_id 送的是 modelStore 的 `id` 欄位字面值（如
 * 'realesrgan-x4plus'，見 backend/app/services/setup/model_metadata_service.py
 * `id=f"{model_family}-{variant_name}"`），不是單獨的 family 或 variant——upscale 類別橫跨
 * 五個家族（realesrgan/swinir/bsrgan/real-cugan/waifu2x），variant token 在跨家族時不保證
 * 唯一（雖然目前註冊表沒有實際撞名），用「family-variant」組成的 id 直接比對才是唯一且正確
 * 的識別方式；既有 variant 分支要求 `m.variant === req.variant`，把完整 id 塞進 variant
 * 欄位對不上（m.variant 只是 id 去掉 family 前綴的那段），故不採「Req 沿用 variant 欄位塞
 * model_id」的權宜作法，改為在 modelGuardUtils 加一個正規的 id 比對形狀（第一個使用者）。
 *
 * face_fix 為 false 時 face_restore_model_id 明確送 null（鏡射舊 ImageUpscalePanel.getParams()
 * 的 `faceRestore.value && selectedFaceModelId.value ? selectedFaceModelId.value : null`——
 * 即使 params 裡殘留舊選過的 face model id，buildSubmit 仍在送出前把它歸零，不送半殘值）。
 *
 * face_fix 為 true 時追加第二道模型需求（face_restore_model_id，slot 仍用 'upscale'——見
 * SLOT_GUARD_CATEGORY 內只有一個 upscale→image 對照即可涵蓋兩道 guard）：這是舊
 * ImageUpscalePanel.execute() 沒有的新行為（舊碼只 guard 主模型 selectedUpscaleModel，未
 * guard face_restore 模型；即使 face_fix=true 且 face 模型未下載，舊碼仍會送出任務讓後端
 * 出錯）——統一參數元件案的 modelRequirements 陣列天然支援多道 guard（見批 2 Task 2.4
 * summary.meta.ts 先例），順手補上這個既有缺口比刻意繞過它更正確，記於此供 review 核對。
 */
import type { ToolParamMeta } from '../types'

export const META: ToolParamMeta = {
  toolKey: 'image.upscale',
  apiPath: '/image/upscale',
  labelKey: 'image.upscale.task_label',
  taskType: 'image.upscale',
  schema: [
    // model_id 跨家族（realesrgan/swinir/bsrgan/real-cugan/waifu2x）動態模型系，不列 options
    // （picker 走 composite 即時清單，見 UpscaleParams.vue）
    { name: 'model_id', type: 'string', default: 'realesrgan-x4plus', advanced: true },
    { name: 'scale', type: 'number', min: 2, max: 4, step: 1, default: 4 },
    { name: 'sharpen', type: 'boolean', default: false },
    { name: 'face_fix', type: 'boolean', default: false },
    { name: 'face_restore_model_id', type: 'string', advanced: true, visibleWhen: (p) => p.face_fix === true },
    { name: 'face_restore_upscale', type: 'number', min: 1, max: 4, step: 1, default: 2, advanced: true, visibleWhen: (p) => p.face_fix === true },
  ],
  defaults() {
    const d: Record<string, unknown> = {}
    for (const f of this.schema) if (f.default !== undefined) d[f.name] = f.default
    return d
  },
  // face_fix=false 時 face_restore_model_id 明確送 null（見檔頭註解，鏡射舊 getParams 三元式）。
  buildSubmit(params) {
    const payload: Record<string, unknown> = { ...params }
    if (!(params.face_fix === true && payload.face_restore_model_id)) {
      payload.face_restore_model_id = null
    }
    return {
      apiPath: this.apiPath,
      payload,
      taskType: this.taskType,
      labelKey: this.labelKey,
    }
  },
  // id 型模型需求（見檔頭註解）：主模型恆需求；face_fix=true 且已選 face 模型時追加第二道。
  modelRequirements(params) {
    const reqs: Array<{ slot: string; id?: string }> = [
      { slot: 'upscale', id: String(params.model_id ?? '') },
    ]
    if (params.face_fix === true && params.face_restore_model_id) {
      reqs.push({ slot: 'upscale', id: String(params.face_restore_model_id) })
    }
    return reqs
  },
  // 舊 ImageView.handleMultiExecute 的 'upscale' case 已支援批次（submitToAll）——沿舊行為。
  multiSelect: true,
  // 舊 ImageUpscalePanel.agentSchema.execute.label 是 'panel.upscale.execute'，與
  // labelKey('image.upscale.task_label') 不同——見 ToolParamHost.vue agentSchema.execute 註解。
  agentExecuteLabel: 'panel.upscale.execute',
  persistedModelFields: ['model_id', 'face_restore_model_id'],
}
