# MediaTranX 工具面板排版指南

> 規範所有工具右側設定面板（`components/{image,video,audio,document}/panels/*.vue` 與 `video/SubtitlePanel.vue`）的版面組織方式。**新增或重構面板時必須遵循本指南。** 本文件為「準則 + 逐面板符合度對照」，現有面板的逐步收斂另開實作輪。
>
> 來源：2026-06-11 工具面板一致性稽核第三層（③）。前兩層＝① i18n label 正規化、② 後端參數正名（已完成）。

---

## 1. 兩條正交軸

面板版面由**兩條互不相干的軸**決定。釐清這點可消除過去「同樣是『進階』卻意義相反」的混亂——很多看似不一致其實只是混用了兩條軸的詞彙。

### 軸 A — 條件顯示（Progressive Disclosure）
某欄位**只有在前一個選擇成立時才有意義** → 該欄位在觸發它的控制項**正下方 inline 出現**。

- 例：翻譯開關 ON → 才顯示「目標語言 / 翻譯模型」；解析度=自訂 → 才顯示寬/高；音量模式=調整 → 才顯示音量滑桿；格式=JPEG → 才顯示品質。
- 這是**好設計、與基本/進階無關**，本指南**保留不動**。
- 規範：條件欄位 inline 緊接其觸發者，不要丟到面板別處或進階區（除非該子欄位本身屬「調教」、見軸 B）。

### 軸 B — 基本 / 進階（Basic vs Advanced）
是否把**少數人才調的次要選項**收進可摺疊的「進階選項」區。**這條軸過去最不一致**，本指南用單一判準統一（§2）。

> ⚠️ 兩軸可疊加：一個欄位可以同時是「進階」且「條件顯示」（例：翻譯的某個微調選項，只有翻譯開且展開進階才看得到）。

---

## 2. 核心判準：產出（Output）vs 調教（Tuning）

**基本區 = 決定「你拿到什麼」；進階區 = 決定「怎麼把它做出來」。**

| | 基本區（永遠可見） | 進階區（預設摺疊） |
|---|---|---|
| **語意** | 產出（deliverable）：決定輸出的**內容與檔案本身** | 調教（tuning）：在輸出**有合理預設**下微調品質/方式 |
| **誰會動** | 一般使用者完成任務的必要選擇 | 進階使用者偶爾微調 |

### 四類選項的歸位（解「進階意義相反」矛盾）

| 類別 | 歸區 | 內容 | 理由 |
|---|---|---|---|
| **核心控制** | **基本** | 模型選擇、主模式（如摘要 bullets/narrative）、來源語言 | 任務的必要輸入 |
| **工具主目的的調整**（見下 tie-breaker） | **基本** | adjust 的亮度/對比/飽和度、filter 的濾鏡強度、crop 的裁切範圍、cut 的起訖、volume 的音量 | 這些「調整」**就是工具存在的目的**、非次要選項 |
| **主輸出格式** | **基本** | 檔案類型/容器：MP4/MKV、MP3/WAV、SRT/VTT、PNG/JPEG、md/txt、LRC/TXT | **決定交付物本身**＝產出 |
| **輸出尺寸/解析度** | **基本** | 解析度枚舉(1080p…)、寬/高、裁切尺寸 | 決定產出的**維度**＝產出（注意：重採樣**演算法**屬調教→進階） |
| **多產出交付物的功能開關** | **基本** | 翻譯、摘要大綱、生成 MIDI、額外音軌(stem) | **產出新東西**；開關放基本，其必要子欄位（目標語言等）依軸 A 條件顯示緊接其下 |
| **編碼調教** | **進階** | codec(H.264/H.265/VP9)、CRF/品質、bitrate、sample-rate、縮放(重採樣)演算法 | 決定**怎麼編碼**＝調教（格式/尺寸已在基本決定產出） |
| **模型推理參數** | **進階** | Whisper VAD threshold / beam / word-timestamps / min-silence / independent-segments | 微調 AI 行為、有合理預設 |
| **品質預處理開關** | **進階** | 人聲分離(vocal separation)、對齊(align)、臉部修復(face restore) | **調教現有輸出的品質**、非新交付物 |

**判準（兩步，順序很重要）：**
1. **這個控制是否「附屬於面板中另一個主交付物」（格式/檔案/尺寸/轉錄文字…），只是決定那個交付物『怎麼做出來』？**
   - **否**（此控制本身就是交付物定義、或這工具整個就是在「調」這件事、沒有另一個主產出）→ **基本**。例：ImageAdjust 的亮度（調整就是交付物）、AudioVolume 的音量、Crop 的範圍。
   - **是**（附屬於另一個主產出、只影響怎麼做）→ 進第 2 步。例：transcode 的 codec 附屬於「轉檔」、transcribe 的 VAD 附屬於「轉錄文字」。
2. **它改變我會拿到的檔案/交付物（產出），還是只是調教既有輸出的品質/編碼/AI 行為（調教）？** 產出→**基本**、調教→**進階**。

> **操作測試（界定標準，2026-06-19 codify）**：一欄進進階 ⟺ ①（產出 vs 調教，上面兩步）它只決定「現有交付物怎麼做」非「換哪個交付物」**且** ②（安全前提）有安全預設、不調也正確。
> ⚠️ 「不調也正確」**不是判別線**——基本欄位也多半有預設（Output Format 預設 MP4、Model 有預設），不調也能出片。它是「預設摺疊安全」的**前提**：唯有調教欄位都有安全預設，才能安全地預設收起。**落地驗收：任何被搬進預設摺疊進階區的欄位，實作時必須逐一確認其 code 預設值能產出正確輸出；沒有安全預設的不准搬（或先補預設）。**

> ⚠️ 第 1 步是 tie-breaker：避免把「調整類工具」（ImageAdjust/ImageFilter）的核心控制誤判成「調教→進階」。**真正的判別子＝「面板裡有沒有另一個主產出，而這個控制只是服務它」**——有才可能進進階。對不在下方範例清單的新面板，用這條判別子、別只憑「感覺是不是主目的」。

> 範例對照：
> - **ImageAdjust 亮度/對比** → 調整就是這工具的目的 → **基本**（第 1 步命中）。**transcode 的 codec** → 附屬於「轉檔」這個主產出的編碼調教 → **進階**（第 2 步）。
> - **翻譯** → 多產出一份譯文 → **基本**。**人聲分離** → 只是讓轉錄更準的預處理 → **進階**。
> - **輸出格式 MP4 / 解析度 1080p** → 決定拿到什麼檔、什麼尺寸 → **基本**。**video codec H.265 / 縮放演算法** → 同一個檔怎麼壓/怎麼重採樣 → **進階**。
>
> ⚠️ **「人聲」會落不同區、不是矛盾**：AudioSeparate 的 vocals stem＝**選哪個音軌當交付物**（產出）→ 基本；Transcribe/Subtitle/Summary 的 vocal separation＝**轉錄前的預處理、讓文字更準**（調教既有產出）→ 進階。同一個字、判準第 2 步分流。

---

## 3. 機制規範（版面「怎麼做」也要一致）

判準決定**什麼**進進階；本節規範**怎麼呈現**，避免機制本身各自為政。

> ✅ **（Wave 1～2.1 已收斂）曾有三套機制並存**（歷史記錄；各 Wave 已全數統一）：
> (a) `settings-collapsible` + chevron header + localStorage（AudioTranscribe、Subtitle、Lyrics；原鍵 `transcribe_advanced`/`subtitle_advanced`/`lyrics_advanced`，**Wave 2 已正規化**為 `audio_transcribe_advanced`/`video_subtitle_advanced`/`audio_lyrics_advanced`）；
> (b) 自寫 `.advanced-toggle` scoped div、`showAdvanced=ref(false)`、**無 localStorage 記憶**（VideoEnhance、VideoInterpolate → **Wave 1 已換 `SettingsCollapsible`**）；
> (c) 子元件 `WhisperAdvancedSettings` 用 `AppToggle` 當摺疊、**無持久化**（**Wave 2.1 改以 `embedded` prop 攤進單一 panel 進階區**，AppToggle 不渲染）。

1. **單一「進階選項」摺疊樣式**：panel-level 進階區一律用同一個可摺疊區塊（label＝`common.advanced_options`「進階選項」），**預設摺疊**、統一用 localStorage 記憶。**標準容器＝`components/common/SettingsCollapsible.vue`**（Wave 1 新增；props `storageKey`/`title?`、自帶 localStorage + `aria-expanded`/`aria-controls`、預設 slot 放進階 body）。**取代** (b) 的自寫無記憶版。
   > **localStorage key 規範**：`<domain>_<function>_advanced`（domain 前綴**必要**——`cut`/`transcode`/`convert` 等功能名跨 image/video/audio 會撞，如 AudioCut vs VideoCut）。Wave 1 採 `video_enhance_advanced` / `video_interpolate_advanced` / `image_convert_advanced` / `image_upscale_advanced` / `video_cut_advanced` / `audio_transcode_advanced`。既有 (a) 的 `transcribe_advanced`/`subtitle_advanced`/`lyrics_advanced`，**Wave 2 已正規化**為 `audio_transcribe_advanced`/`video_subtitle_advanced`/`audio_lyrics_advanced`。
   > **Wave 1 已用 `SettingsCollapsible` 收斂的面板**：VideoEnhance / VideoInterpolate（同時把 (b) 自寫無記憶摺疊換掉）、ImageConvert / ImageUpscale / VideoCut / AudioTranscode。**Wave 2 done**：AudioTranscribe / Subtitle / Lyrics 的 (a) inline 版已改用 `SettingsCollapsible` wrapper（鍵已正規化，見上方）。
2. **重用共用子元件**，不要各面板散寫：
   - `WhisperAdvancedSettings.vue` — 模型推理參數。**凡有 Whisper STT 的面板**（Transcribe / Subtitle / Summary）都應嵌入它，不要各自重寫那 5 個欄位。
     > ⚠️ **Wave 2.1 更新（2026-06-20）**：凡面板已有 panel 進階區者，`WhisperAdvancedSettings` **以 `embedded` prop 攤進同一個「進階選項」**（與 vocal-sep 等調教同桶），元件自帶「分句設定」小標題分組，**不另立第二個摺疊**（避免雙層、單一進階入口）。`embedded` 模式下元件自身的 AppToggle 不渲染，由外層 `SettingsCollapsible` 統一控制展收。**「勿雙層摺疊」精神不變，現以 embedded 達成單層。**
   - `TranslationOptionsPanel.vue` — 翻譯功能（**enable 開關 + 條件子欄位綁成單一元件、不可只搬開關**）。**凡有翻譯功能的面板**（Subtitle / Transcribe / Lyrics / Document Translate）應重用它。
     > ⚠️ 因為它把開關和子欄位綁在一起，「翻譯=基本」的落地方式＝**整個 TranslationOptionsPanel 放在基本區**（enable 開關可見＝產出類功能；其 target language / model / style / keep-names / glossary 子欄位依軸 A 條件顯示在開關下）。**不是**把開關抽出來、子欄位留進階（那會拆元件、非零風險）。
3. **條件顯示 inline**（軸 A）：條件子欄位緊接觸發它的控制項，不丟到面板別處。
4. **面板內順序**：基本區（核心控制 → 主輸出格式/尺寸 → 功能開關/翻譯元件）→ 最後是**單一 panel「進階選項」摺疊**（內含 vocal-sep 等調教 + embedded `WhisperAdvancedSettings`）。⚠️ Wave 2.1 後 WhisperAdvancedSettings **不再**放在基本區末尾當獨立 sibling，改以 `embedded` 歸入 panel 進階區。
5. **說明文字**：hint 用 `<small class="form-hint">` 放欄位下方，不佔主要視覺空間。

---

## 4. 明文例外

- **AudioMidiEditPanel 分頁（Edit / Effects / Export）**：MIDI 編輯器是**編輯器類工具**（互動式、非單次轉換），其 Edit/Effects/Export 分頁是正當的工作流設計，**不強制收斂成基本/進階**。Effects tab 的 EQ/Compressor/Delay/Reverb 屬即時效果鏈、亦非本指南的「進階摺疊」範疇。本面板**豁免**軸 B 規範（軸 A 條件顯示與機制一致性仍適用）。

---

## 5. 附錄：逐面板符合度對照表

> 「待改」項供日後實作輪逐面板收斂用；本輪（③）只產出本指南、不改 code。
> 圖例：✅ 符合準則／🔧 待改（附改法）／➖ 例外或不適用。
> 「待改」涵蓋**兩種**問題：**[歸位]** 軸 B 基本/進階分錯（§2）、**[機制]** 摺疊機制不一致（§3，如自寫無記憶摺疊、雙層摺疊）。兩者可並存於同一面板。**Wave 1～2.1 後「自寫無記憶摺疊」及「雙層摺疊」問題已全數解決，現無面板帶有 [機制] 待改項。**

### Image（8）
| 面板 | 現況 | 判定 | 待改 |
|---|---|---|---|
| ImageAdjust | 平鋪 6 滑桿 | ✅ | 皆核心調整、無次要選項 |
| ImageFilter | 平鋪 5 滑桿 | ✅ | 同上 |
| ImageRemoveBg | 平鋪 1 下拉 | ✅ | 極簡 |
| ImageCrop | 平鋪（比例/位置/尺寸） | ✅ | 皆核心、含軸 A 聯動 |
| ImageAiRemove | 工具選擇 + 條件顯示 | ✅ | 軸 A 正確 |
| ImageConvert | 基本[格式/Resize] + lossy-gated 進階[Quality] | ✅ | **Wave 1 done**：Quality 移入 lossy 條件下的 `SettingsCollapsible`（`image_convert_advanced`）；PNG 等非 lossy 不渲染進階區（不留空展開器）；getParams 仍恆送 quality（未耦合 UI） |
| ImageOcr | 平鋪（模型/格式） | ✅ | 皆基本 |
| ImageUpscale | 基本[模型/倍率] + 進階[銳化/Face Restore+子參] | ✅ | **Wave 1 done**：Sharpen + Face Restore（含子參）移入 `SettingsCollapsible`（`image_upscale_advanced`）；wire key `face_fix` 不變 |

### Video（7）
| 面板 | 現況 | 判定 | 待改 |
|---|---|---|---|
| VideoCrop | 平鋪 | ✅ | 同 ImageCrop |
| VideoCut | 基本[起訖] + 進階[串流複製] | ✅ | **Wave 1 done**：Stream Copy 移入 `SettingsCollapsible`（`video_cut_advanced`）；保留與 VideoView 父層 prop/emit 綁定 |
| VideoEnhance | 基本[模型/解析度/格式] + 進階[codec] | ✅ | **Wave 1 done**：格式上移基本、codec 進 `SettingsCollapsible`（`video_enhance_advanced`）；自寫無記憶摺疊已換掉 |
| VideoInterpolate | 基本[模型/模式/fps/格式] + 進階[codec] | ✅ | **Wave 1 done**：同 VideoEnhance（`video_interpolate_advanced`） |
| VideoTranscode | 基本[格式/解析度] + 進階[codec/CRF/縮放演算法/bitrate] | ✅ | **Wave 2 done**：codec/CRF/縮放/bitrate 收入 content-gated `SettingsCollapsible`（`video_transcode_advanced`）；格式/解析度留基本 |
| VideoSummary | 基本[模式/whisper/LLM/VLM] + 單一 panel 進階區[vocal-sep + embedded WhisperAdvanced（分句設定群）] | ✅ | **Wave 2.1 done**：vocal-sep 移入 panel 進階✅（調教）；WhisperAdvancedSettings 以 `embedded` 攤進同一進階區，單一「進階選項」入口，無雙層摺疊 |
| SubtitlePanel | 基本[來源語言/whisper/格式 + TranslationOptionsPanel] + 單一 panel 進階區[vocal-sep + embedded WhisperAdvanced（分句設定群）] | ✅ | **Wave 2.1 done**：翻譯移基本✅（TranslationOptionsPanel）；vocal-sep 留進階✅（調教）；WhisperAdvancedSettings 以 `embedded` 攤進同一進階區，雙層摺疊問題已解 |

### Audio（7）
| 面板 | 現況 | 判定 | 待改 |
|---|---|---|---|
| AudioCut | 平鋪（起訖） | ✅ | |
| AudioVolume | 模式按鈕 + 條件音量 | ✅ | 軸 A 正確 |
| AudioTranscode | 基本[格式] + 進階[bitrate/sample-rate] | ✅ | **Wave 1 done**：bitrate（仍條件 lossy）+ sample-rate 移入 `SettingsCollapsible`（`audio_transcode_advanced`） |
| AudioSeparate | 平鋪（6 stem 開關/格式/生MIDI） | ✅ | stem=選**哪些音軌當產出**（≠Transcribe 的人聲分離預處理，故同樣是「人聲」卻歸基本——判準第 2 步：這裡人聲是交付物）、格式=產出、生MIDI=多產出 → **全屬基本、正確**（先前「複雜平鋪需修」判斷有誤） |
| AudioLyrics | 基本[模型/格式 + TranslationOptionsPanel] + 進階[align] | ✅ | **Wave 2 done**：翻譯改用 TranslationOptionsPanel 移基本✅；align 留進階（調教）；`SettingsCollapsible`（`audio_lyrics_advanced`） |
| AudioTranscribe | 基本[whisper/來源語言/格式 + TranslationOptionsPanel + 摘要開關] + 單一 panel 進階區[vocal-sep + embedded WhisperAdvanced（分句設定群，含 align）] | ✅ | **Wave 2.1 done**：翻譯/摘要移基本✅；vocal-sep 留進階✅；WhisperAdvancedSettings 以 `embedded` 攤進單一進階區（已嵌入，align 去重—散寫 align 開關已移除，改用元件內的） |
| AudioMidiEdit | 分頁 Edit/Effects/Export | ➖ | 編輯器類、豁免（見 §4） |

### Document（4）
| 面板 | 現況 | 判定 | 待改 |
|---|---|---|---|
| DocumentOcr | 平鋪（模型/格式） | ✅ | 皆基本 |
| DocumentPdfConvert | 平鋪（格式） | ✅ | 極簡 |
| DocumentSplit | 平鋪（頁碼範圍） | ✅ | |
| DocumentTranslate | 平鋪（模型/來源/目標/風格/詞彙表） | ✅／🔧 | 模型/來源/目標/風格=核心翻譯控制=基本✅；**glossary=選用精修、條件/選用顯示於基本**（與 TranslationOptionsPanel 一致——翻譯本就是此工具主目的、整組在基本）。本面板是「純翻譯」工具、無附屬主產出，不需另設進階區；唯一 🔧＝可評估與 TranslationOptionsPanel 共用以免兩套翻譯 UI |

### 共用子元件
| 元件 | 角色 | 規範 |
|---|---|---|
| WhisperAdvancedSettings.vue | 模型推理參數；支援 `embedded` prop | 凡 Whisper 面板都嵌入、勿重寫；**以 `embedded` prop 攤進單一 panel 進階區（與 vocal-sep 等其他調教同桶）**，自帶「分句設定」小標題分組，**不另立第二摺疊**（§3.2，Wave 2.1 更新） |
| TranslationOptionsPanel.vue | 翻譯功能；**enable 開關 + 條件子欄位綁成單一元件** | 凡翻譯面板都重用；落地「翻譯=基本」＝**整個元件放基本區**（開關可見、子欄位條件顯示），**不可只搬開關、子欄位留進階**（§3.2） |

---

## 6. 收斂紀錄（Wave 1～2.1 已全數完成）

> 本節原為「給日後實作輪參考」的優先序；Wave 1（2026-06-19 merged `ba62c46`）＋Wave 2＋Wave 2.1（branch `feat/tool-panel-layout-wave2`）已全數完成，以下保留做完成紀錄。

1. ✅ **Wave 1 done（低風險純搬移）**：VideoEnhance/Interpolate 的格式上移基本（搬一個欄位）；AudioTranscribe/Lyrics 的「摘要開關」上移基本（搬開關）。
2. ✅ **Wave 2＋2.1 done（元件搬遷/重構）**：
   - Subtitle/Lyrics/Transcribe 的翻譯＝**整個 TranslationOptionsPanel 搬到基本區**（含重構散寫成元件）✅ Wave 2。
   - AudioTranscribe 補嵌 WhisperAdvancedSettings＋**去重既有 align 開關**✅ Wave 2；`/audio/transcribe` route 已擴充接受 4 個新 Whisper payload key（word_timestamps / condition_on_previous_text / min_silence / vad_threshold）✅ Wave 2 backend；WhisperAdvancedSettings 以 `embedded` 攤進單一進階區✅ Wave 2.1。
   - Subtitle 拆掉「WhisperAdvanced 被包進 panel 進階」的雙層摺疊✅ Wave 2（外層翻譯改 TranslationOptionsPanel 在基本）；Wave 2.1 進一步以 `embedded` 完成單入口。
3. ✅ **Wave 1 done（機制收斂）**：VideoEnhance/Interpolate 自寫無記憶摺疊→改統一 `進階選項`＋localStorage（`video_enhance_advanced` / `video_interpolate_advanced`）。
4. ✅ **Wave 2＋2.1 done（VideoSummary vocal-sep）**：vocal-sep 收入 panel 進階 `SettingsCollapsible`（`video_summary_advanced`）；WhisperAdvancedSettings 以 `embedded` 攤進同一進階區（Wave 2.1），單一「進階選項」入口，無雙層摺疊。
5. ✅ **Wave 2 done（VideoTranscode 重排）**：VideoTranscode 新建 panel 進階摺疊（`video_transcode_advanced`），codec/CRF/縮放/bitrate 收入 content-gated `SettingsCollapsible`。
6. ✅ **每輪均已驗**：軸 A 條件顯示、後端 payload（key 正名後不因版面搬移改變；新增 key 均已擴充 route 接受）、雙語系 label 不受影響。

> 注意：本指南為設計準則，實作前仍須以各面板現行 code 為準（控制項、軸 A 邏輯可能隨功能演進）。
