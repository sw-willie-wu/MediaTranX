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

> ⚠️ **現況：摺疊機制本身就有三套並存**（待收斂、§5 會逐面板標）：
> (a) `settings-collapsible` + chevron header + localStorage（AudioTranscribe `transcribe_advanced`、Subtitle `subtitle_advanced`、Lyrics `lyrics_advanced`）；
> (b) 自寫 `.advanced-toggle` scoped div、`showAdvanced=ref(false)`、**無 localStorage 記憶**（VideoEnhance、VideoInterpolate）；
> (c) 子元件 `WhisperAdvancedSettings` 用 `AppToggle` 當摺疊、**無持久化**。
> 本節 1.~2. 是收斂目標。

1. **單一「進階選項」摺疊樣式**：panel-level 進階區一律用同一個可摺疊區塊（label＝`common.advanced_options`「進階選項」），**預設摺疊**、統一用 localStorage 記憶（key `<tool>_advanced`）。**取代** (b) 的自寫無記憶版。
2. **重用共用子元件**，不要各面板散寫：
   - `WhisperAdvancedSettings.vue` — 模型推理參數。**凡有 Whisper STT 的面板**（Transcribe / Subtitle / Summary）都應嵌入它，不要各自重寫那 5 個欄位。
     > ⚠️ 它**本身自帶一層摺疊**（AppToggle）＝即為「模型推理參數」這組的進階容器。因此**直接放在基本區末尾當一個 sibling 即可、不要再外包一層 panel `進階選項` 摺疊**（否則變雙層摺疊、使用者要點兩次）。Subtitle 目前把它包進 panel 進階摺疊＝雙層、待修（§5）。
   - `TranslationOptionsPanel.vue` — 翻譯功能（**enable 開關 + 條件子欄位綁成單一元件、不可只搬開關**）。**凡有翻譯功能的面板**（Subtitle / Transcribe / Lyrics / Document Translate）應重用它。
     > ⚠️ 因為它把開關和子欄位綁在一起，「翻譯=基本」的落地方式＝**整個 TranslationOptionsPanel 放在基本區**（enable 開關可見＝產出類功能；其 target language / model / style / keep-names / glossary 子欄位依軸 A 條件顯示在開關下）。**不是**把開關抽出來、子欄位留進階（那會拆元件、非零風險）。
3. **條件顯示 inline**（軸 A）：條件子欄位緊接觸發它的控制項，不丟到面板別處。
4. **面板內順序**：基本區（核心控制 → 主輸出格式/尺寸 → 功能開關/翻譯元件 → WhisperAdvancedSettings）→ 最後才是 panel-level「進階選項」摺疊（放編碼調教等）。
5. **說明文字**：hint 用 `<small class="form-hint">` 放欄位下方，不佔主要視覺空間。

---

## 4. 明文例外

- **AudioMidiEditPanel 分頁（Edit / Effects / Export）**：MIDI 編輯器是**編輯器類工具**（互動式、非單次轉換），其 Edit/Effects/Export 分頁是正當的工作流設計，**不強制收斂成基本/進階**。Effects tab 的 EQ/Compressor/Delay/Reverb 屬即時效果鏈、亦非本指南的「進階摺疊」範疇。本面板**豁免**軸 B 規範（軸 A 條件顯示與機制一致性仍適用）。

---

## 5. 附錄：逐面板符合度對照表

> 「待改」項供日後實作輪逐面板收斂用；本輪（③）只產出本指南、不改 code。
> 圖例：✅ 符合準則／🔧 待改（附改法）／➖ 例外或不適用。
> 「待改」涵蓋**兩種**問題：**[歸位]** 軸 B 基本/進階分錯（§2）、**[機制]** 摺疊機制不一致（§3，如自寫無記憶摺疊、雙層摺疊）。兩者可並存於同一面板。

### Image（8）
| 面板 | 現況 | 判定 | 待改 |
|---|---|---|---|
| ImageAdjust | 平鋪 6 滑桿 | ✅ | 皆核心調整、無次要選項 |
| ImageFilter | 平鋪 5 滑桿 | ✅ | 同上 |
| ImageRemoveBg | 平鋪 1 下拉 | ✅ | 極簡 |
| ImageCrop | 平鋪（比例/位置/尺寸） | ✅ | 皆核心、含軸 A 聯動 |
| ImageAiRemove | 工具選擇 + 條件顯示 | ✅ | 軸 A 正確 |
| ImageConvert | 條件顯示（格式→品質/縮放） | 🔧 | 格式=基本✅；**Quality(JPEG/WebP) 屬編碼調教→可移進階**（仍條件於 lossy 格式） |
| ImageOcr | 平鋪（模型/格式） | ✅ | 皆基本 |
| ImageUpscale | 模型/倍率/銳化 + Face Restore 條件展開 | 🔧 | Face Restore=品質預處理✅在進階；**銳化(sharpen) 屬調教→宜移進階**（次要） |

### Video（7）
| 面板 | 現況 | 判定 | 待改 |
|---|---|---|---|
| VideoCrop | 平鋪 | ✅ | 同 ImageCrop |
| VideoCut | 平鋪（起訖/串流複製） | 🔧 | 串流複製(stream copy)=編碼調教→宜移進階（次要、有預設） |
| VideoEnhance | 自寫 `.advanced-toggle` 摺疊放 [格式+codec]、無 localStorage | 🔧 | **[歸位]** 格式上移基本（產出）、codec 留進階；**[機制]** 自寫無記憶摺疊→改用統一 `進階選項`+localStorage（§3.1） |
| VideoInterpolate | 同 VideoEnhance（自寫摺疊無記憶） | 🔧 | **[歸位]** 格式上移基本、codec 留進階；**[機制]** 同上 |
| VideoTranscode | 複雜條件平鋪（格式/codec/解析度/CRF/縮放/bitrate） | 🔧 | **[歸位]** 格式/解析度=基本（產出維度）✅；**codec/CRF/縮放演算法/bitrate 屬編碼調教→收進「進階選項」摺疊**（目前無 panel 進階區，需新建） |
| VideoSummary | **全平鋪**（模式/whisper/vocal-sep + WhisperAdvanced 子元件 + LLM/VLM，無 panel 進階區） | 🔧 | **[歸位]** vocal separation→屬調教，但本面板無 panel 進階區、WhisperAdvanced 也平鋪；**模式/模型=基本✅**；WhisperAdvanced 自帶摺疊＝其進階容器（§3.2，可平鋪當 sibling、勿外包） |
| SubtitlePanel | 基本[來源語言/whisper/vocal-sep/格式] + panel 進階摺疊內含 [WhisperAdvanced + Translation] | 🔧 | **[歸位]** vocal-sep→屬調教（可移進 panel 進階或併入 WhisperAdvanced 群）；**翻譯→整個 TranslationOptionsPanel 移基本**（產出，§3.2）；**[機制]** WhisperAdvanced 自帶摺疊卻又被包進 panel 進階＝**雙層摺疊、待拆**（WhisperAdvanced 當 sibling 即可，§3.2） |

### Audio（7）
| 面板 | 現況 | 判定 | 待改 |
|---|---|---|---|
| AudioCut | 平鋪（起訖） | ✅ | |
| AudioVolume | 模式按鈕 + 條件音量 | ✅ | 軸 A 正確 |
| AudioTranscode | 格式 + 條件 bitrate + sample-rate | 🔧 | 格式=基本✅；**bitrate/sample-rate 屬編碼調教→移進階**（bitrate 仍條件於 lossy） |
| AudioSeparate | 平鋪（6 stem 開關/格式/生MIDI） | ✅ | stem=選**哪些音軌當產出**（≠Transcribe 的人聲分離預處理，故同樣是「人聲」卻歸基本——判準第 2 步：這裡人聲是交付物）、格式=產出、生MIDI=多產出 → **全屬基本、正確**（先前「複雜平鋪需修」判斷有誤） |
| AudioLyrics | 基本[模型/格式] + panel 進階摺疊[align/translate→子欄位] | 🔧 | **[歸位]** align=品質預處理✅留進階；**翻譯→整個 TranslationOptionsPanel 移基本**（產出，§3.2），取代現有散寫 |
| AudioTranscribe | 基本[whisper/來源語言/格式] + panel 進階摺疊[vocal-sep/align/translate/summarize 散寫] | 🔧 | **[歸位]** vocal-sep✅留進階；**翻譯、摘要→開關上移基本**（產出）；**[重構]** 翻譯改用 TranslationOptionsPanel（整個移基本）、**補嵌 WhisperAdvancedSettings**（目前缺）——⚠️ 但本面板已自帶獨立 `align` 開關，而 WhisperAdvancedSettings 內**也含 align**，補嵌時須**擇一去重**（移除散寫的 align、改用元件內的） |
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
| WhisperAdvancedSettings.vue | 模型推理參數；**自帶一層摺疊** | 凡 Whisper 面板都嵌入、勿重寫；當其組的進階容器、**平鋪當 sibling、勿再外包 panel 進階摺疊**（§3.2） |
| TranslationOptionsPanel.vue | 翻譯功能；**enable 開關 + 條件子欄位綁成單一元件** | 凡翻譯面板都重用；落地「翻譯=基本」＝**整個元件放基本區**（開關可見、子欄位條件顯示），**不可只搬開關、子欄位留進階**（§3.2） |

---

## 6. 收斂優先序（給日後實作輪參考）

1. **低風險、純搬移**：VideoEnhance/Interpolate 的格式上移基本（搬一個欄位）；AudioTranscribe/Lyrics 的「摘要開關」上移基本（搬開關）。
2. **中等：元件搬遷/重構**（**非零風險**，因 TranslationOptionsPanel/WhisperAdvancedSettings 是整塊綁定元件）：
   - Subtitle/Lyrics/Transcribe 的翻譯＝**整個 TranslationOptionsPanel 搬到基本區**（含重構散寫成元件，Transcribe/Lyrics 目前是散寫）。
   - AudioTranscribe 補嵌 WhisperAdvancedSettings＋**去重既有 align 開關**（§5）。⚠️ 補嵌會帶入 4 個新 Whisper 參數（word_timestamps/condition_on_previous_text/min_silence/vad_threshold），**須先確認 `/audio/transcribe` route 接受這些 payload key**（否則 ②的 `extra='ignore'` 會靜默丟棄）；不接受就不要補嵌、或先擴後端。
   - Subtitle 拆掉「WhisperAdvanced 被包進 panel 進階」的雙層摺疊（§3.2）。
3. **機制收斂**：VideoEnhance/Interpolate 自寫無記憶摺疊→改統一 `進階選項`+localStorage（§3.1）。
4. **VideoSummary 的 vocal separation**：本面板無 panel 進階區、目前平鋪。兩條路擇一——(a) 比照 Subtitle 新建 panel 進階區收 vocal-sep；(b) 若不想為單一開關建進階區，**明文視為可接受平鋪**（vocal-sep 雖屬調教、但此面板無其他次要選項可一起收）。實作輪決定，本指南不硬性要求。
5. **較大重排**：VideoTranscode 新建 panel 進階摺疊、把 codec/CRF/縮放/bitrate 收進去。
6. 每次重排都應驗證**軸 A 條件顯示**、**後端 payload**（②已正名、payload key 不可因搬版面而變；新增控制項須確認 route 接受其 key）、**雙語系 label**不受影響。

> 注意：本指南為設計準則，實作前仍須以各面板現行 code 為準（控制項、軸 A 邏輯可能隨功能演進）。
