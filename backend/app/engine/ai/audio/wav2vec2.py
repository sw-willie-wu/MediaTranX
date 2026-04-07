"""
Wav2Vec2 Forced Alignment 引擎
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
用 Wav2Vec2 phoneme 模型對 Whisper 的轉錄結果做 forced alignment，
產生精確的 word-level timestamps。

不繼承 Runtime — 這是後處理工具，用完即釋放。
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable, Any

import numpy as np
import soundfile as sf
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

logger = logging.getLogger(__name__)



@dataclass
class AlignedWord:
    """對齊後的單字"""
    word: str
    start: float
    end: float
    score: float  # alignment 信心分數


# 每個語言對應的 HuggingFace Wav2Vec2 model ID
LANG_MODELS: dict[str, str] = {
    "en": "jonatasgrosman/wav2vec2-large-xlsr-53-english",
    "zh": "jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn",
    "ja": "jonatasgrosman/wav2vec2-large-xlsr-53-japanese",
    "ko": "kresnik/wav2vec2-large-xlsr-korean",
    "fr": "jonatasgrosman/wav2vec2-large-xlsr-53-french",
    "de": "jonatasgrosman/wav2vec2-large-xlsr-53-german",
    "es": "jonatasgrosman/wav2vec2-large-xlsr-53-spanish",
    "pt": "jonatasgrosman/wav2vec2-large-xlsr-53-portuguese",
    "it": "jonatasgrosman/wav2vec2-large-xlsr-53-italian",
    "nl": "jonatasgrosman/wav2vec2-large-xlsr-53-dutch",
    "pl": "jonatasgrosman/wav2vec2-large-xlsr-53-polish",
    "ru": "jonatasgrosman/wav2vec2-large-xlsr-53-russian",
    "ar": "jonatasgrosman/wav2vec2-large-xlsr-53-arabic",
    "fi": "jonatasgrosman/wav2vec2-large-xlsr-53-finnish",
    "hu": "jonatasgrosman/wav2vec2-large-xlsr-53-hungarian",
    "el": "jonatasgrosman/wav2vec2-large-xlsr-53-greek",
}

# Wav2Vec2 模型的取樣率
_WAV2VEC2_SR = 16000


class AlignmentEngine:
    """
    Wav2Vec2 Forced Alignment 引擎

    職責：
    1. 載入語言對應的 Wav2Vec2 模型
    2. 對 Whisper segments 做 CTC forced alignment
    3. 回傳精確的 word-level timestamps
    """

    def __init__(self):
        self._model: Any = None
        self._processor: Any = None
        self._loaded_lang: Optional[str] = None
        self._device: str = "cpu"

    def is_language_supported(self, language: str) -> bool:
        """檢查語言是否有對應的 alignment 模型"""
        return language in LANG_MODELS

    def get_supported_languages(self) -> list[str]:
        """取得支援的語言列表"""
        return list(LANG_MODELS.keys())

    def align(
        self,
        audio_path: str,
        segments: list,
        language: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> list:
        """
        對 Whisper 的 segments 做 forced alignment

        Args:
            audio_path: 音訊檔案路徑
            segments: Whisper TranscribeSegment 列表
            language: 語言代碼（en, zh, ja...）
            on_progress: 進度回調

        Returns:
            校正後的 TranscribeSegment 列表（帶 words 屬性）
        """
        if not self.is_language_supported(language):
            logger.warning(f"Language '{language}' not supported for alignment, returning original segments")
            return segments

        if not segments:
            return segments

        # 選擇 device
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            # 載入模型
            if on_progress:
                on_progress(0.0, "task.progress.loading_alignment")
            self._ensure_model(language)

            # 讀取完整音訊
            if on_progress:
                on_progress(0.1, "task.progress.reading_audio")
            full_waveform = self._load_audio(audio_path)

            # 逐 segment 分段推論（避免一次送入整段長音訊導致 OOM/卡頓）
            from app.engine.ai.audio.whisper import TranscribeSegment

            aligned_segments: list[TranscribeSegment] = []
            total = len(segments)
            pad_sec = 0.5  # 前後各多取 0.5 秒做 context

            for i, seg in enumerate(segments):
                if on_progress:
                    progress = 0.15 + 0.8 * (i / total)
                    on_progress(progress, f"task.progress.aligning_segment|{i+1}|{total}")

                # 擷取 segment 對應的音訊片段（含前後 padding）
                start_sample = max(0, int((seg.start - pad_sec) * _WAV2VEC2_SR))
                end_sample = min(len(full_waveform), int((seg.end + pad_sec) * _WAV2VEC2_SR))
                seg_waveform = full_waveform[start_sample:end_sample]

                if len(seg_waveform) < 160:  # 太短跳過
                    aligned_segments.append(seg)
                    continue

                # 限制單次推論長度（超過 15 秒的 segment 跳過對齊，避免卡住）
                max_samples = int(15 * _WAV2VEC2_SR)
                if len(seg_waveform) > max_samples:
                    logger.info(f"Segment {i+1} too long ({len(seg_waveform) / _WAV2VEC2_SR:.1f}s), skipping alignment")
                    aligned_segments.append(seg)
                    continue

                # 對這段音訊做推論
                with torch.no_grad():
                    inputs = self._processor(
                        seg_waveform,
                        sampling_rate=_WAV2VEC2_SR,
                        return_tensors="pt",
                        padding=True,
                    )
                    input_values = inputs.input_values.to(self._device)
                    logits = self._model(input_values).logits[0]
                    seg_log_probs = torch.log_softmax(logits, dim=-1).cpu()

                # frame duration 基於這段音訊
                seg_samples = len(seg_waveform)
                seg_frames = seg_log_probs.shape[0]
                frame_duration = seg_samples / (_WAV2VEC2_SR * seg_frames)

                # 計算 padding 偏移（alignment 結果時間需加回去）
                actual_start = start_sample / _WAV2VEC2_SR

                # 嘗試 forced alignment
                words = self._align_segment(
                    seg_log_probs, seg.text, actual_start, frame_duration
                )

                if words:
                    new_seg = TranscribeSegment(
                        start=words[0].start,
                        end=words[-1].end,
                        text=seg.text,
                    )
                    new_seg.words = words  # type: ignore
                    aligned_segments.append(new_seg)
                else:
                    aligned_segments.append(seg)

            if on_progress:
                on_progress(1.0, "task.progress.align_complete")

            return aligned_segments

        finally:
            self._unload_model()

    def _ensure_model(self, language: str) -> None:
        """載入或切換語言模型"""
        if self._loaded_lang == language and self._model is not None:
            return

        self._unload_model()

        from app.init.configs import SETTINGS

        model_id = LANG_MODELS[language]
        models_dir = SETTINGS.path.models
        models_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = str(models_dir / "alignment")

        logger.info(f"Loading alignment model: {model_id} on {self._device}")
        self._processor = Wav2Vec2Processor.from_pretrained(model_id, cache_dir=cache_dir)
        self._model = Wav2Vec2ForCTC.from_pretrained(model_id, cache_dir=cache_dir)
        self._model.to(self._device)
        self._model.eval()
        self._loaded_lang = language

    def _unload_model(self) -> None:
        """釋放模型"""
        if self._model is not None:
            del self._model
            del self._processor
            self._model = None
            self._processor = None
            self._loaded_lang = None
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info("Alignment model unloaded")

    def _load_audio(self, audio_path: str) -> list[float]:
        """讀取音訊並 resample 到 16kHz mono"""
        from app.init.container import get_container
        ffmpeg_path = get_container().ffmpeg().ffmpeg_path

        # 用 ffmpeg 轉成 16kHz mono PCM
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            subprocess.run(
                [ffmpeg_path, "-y", "-i", audio_path,
                 "-ar", str(_WAV2VEC2_SR), "-ac", "1",
                 "-f", "wav", tmp.name],
                capture_output=True, check=True
            )
            data, sr = sf.read(tmp.name, dtype="float32")
            return data.tolist()
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def _align_segment(
        self,
        log_probs,  # torch.Tensor (frames, vocab)
        text: str,
        segment_start: float,
        frame_duration: float,
    ) -> list[AlignedWord]:
        """
        對單一 segment 做 CTC forced alignment

        使用 Viterbi algorithm 找最佳路徑，
        將文字 token 對齊到 frame-level phoneme probabilities。
        """
        if not text.strip():
            return []

        # Tokenize text
        vocab = self._processor.tokenizer.get_vocab()
        inv_vocab = {v: k for k, v in vocab.items()}

        # 取得 CTC blank token
        blank_id = self._processor.tokenizer.pad_token_id
        if blank_id is None:
            blank_id = 0

        # 將文字轉成 token IDs
        text_clean = text.strip().upper()
        tokens = self._processor.tokenizer.encode(text_clean)
        if not tokens:
            return []

        # 簡化的 CTC forced alignment：
        # 用 greedy decode 找每個 token 的最佳位置
        num_frames = log_probs.shape[0]
        if num_frames == 0:
            return []

        # 建構 token-to-frame mapping
        # 策略：用 log_probs 找每個 token 最高機率的 frame 區間
        token_frames = self._ctc_align(log_probs, tokens, blank_id)

        if not token_frames:
            return []

        # 將 token 合併回 words
        words = self._tokens_to_words(
            token_frames, tokens, segment_start, frame_duration, inv_vocab
        )

        return words

    def _ctc_align(
        self,
        log_probs,  # (frames, vocab)
        tokens: list[int],
        blank_id: int,
    ) -> list[tuple[int, int, int, float]]:
        """
        CTC forced alignment 核心

        用動態規劃找 tokens 在 frames 中的最佳位置。
        回傳 [(token_id, start_frame, end_frame, score), ...]
        """
        num_frames = log_probs.shape[0]
        num_tokens = len(tokens)

        if num_frames < num_tokens:
            return []

        # 建構擴展序列：blank, t1, blank, t2, blank, ...
        expanded = [blank_id]
        for t in tokens:
            expanded.append(t)
            expanded.append(blank_id)
        num_labels = len(expanded)

        # Viterbi forward pass
        # dp[t][s] = 到 frame t、label s 的最大 log probability
        NEG_INF = float('-inf')
        dp = [[NEG_INF] * num_labels for _ in range(num_frames)]
        bp = [[0] * num_labels for _ in range(num_frames)]  # backpointer

        # 初始化第一幀
        dp[0][0] = log_probs[0][expanded[0]].item()
        if num_labels > 1:
            dp[0][1] = log_probs[0][expanded[1]].item()

        # Forward
        for t in range(1, num_frames):
            for s in range(num_labels):
                # 可以從 s（自環）或 s-1（前進一步）轉移
                candidates = [(dp[t-1][s], s)]
                if s > 0:
                    candidates.append((dp[t-1][s-1], s-1))
                # 如果當前不是 blank 且前前個也不是同一個 token，可以跳 blank
                if s > 1 and expanded[s] != expanded[s-2]:
                    candidates.append((dp[t-1][s-2], s-2))

                best_val, best_src = max(candidates, key=lambda x: x[0])
                dp[t][s] = best_val + log_probs[t][expanded[s]].item()
                bp[t][s] = best_src

        # Backtrack
        # 結束時必須在最後一個或倒數第二個 label
        if dp[num_frames-1][num_labels-1] >= dp[num_frames-1][num_labels-2]:
            s = num_labels - 1
        else:
            s = num_labels - 2

        path = [0] * num_frames
        path[num_frames-1] = s
        for t in range(num_frames - 2, -1, -1):
            s = bp[t+1][path[t+1]]
            path[t] = s

        # 從 path 提取每個 non-blank token 的 frame 範圍
        result: list[tuple[int, int, int, float]] = []
        token_idx = 0
        in_token = False
        start_frame = 0

        for t, s in enumerate(path):
            label = expanded[s]
            if label != blank_id:
                if not in_token:
                    start_frame = t
                    in_token = True
            else:
                if in_token:
                    # token 結束
                    # 計算 score（該區間的平均 log prob）
                    token_id = expanded[path[start_frame]]
                    score_sum = sum(
                        log_probs[f][token_id].item()
                        for f in range(start_frame, t)
                    )
                    score = score_sum / max(1, t - start_frame)
                    result.append((token_id, start_frame, t - 1, score))
                    in_token = False

        # 處理最後一個 token（如果 path 結尾不是 blank）
        if in_token:
            token_id = expanded[path[start_frame]]
            score_sum = sum(
                log_probs[f][token_id].item()
                for f in range(start_frame, num_frames)
            )
            score = score_sum / max(1, num_frames - start_frame)
            result.append((token_id, start_frame, num_frames - 1, score))

        return result

    def _tokens_to_words(
        self,
        token_frames: list[tuple[int, int, int, float]],
        tokens: list[int],
        segment_start: float,
        frame_duration: float,
        inv_vocab: dict,
    ) -> list[AlignedWord]:
        """將 token-frame mapping 合併為 words"""
        if not token_frames:
            return []

        words: list[AlignedWord] = []
        current_word = ""
        word_start = -1.0
        word_end = -1.0
        word_scores: list[float] = []

        for token_id, sf, ef, score in token_frames:
            char = inv_vocab.get(token_id, "")
            # 清理特殊 token 前綴
            char = char.replace("▁", " ").replace("|", " ")

            t_start = segment_start + sf * frame_duration
            t_end = segment_start + (ef + 1) * frame_duration

            if char.startswith(" ") and current_word:
                # 新 word 開始，保存上一個
                words.append(AlignedWord(
                    word=current_word.strip(),
                    start=round(word_start, 3),
                    end=round(word_end, 3),
                    score=round(sum(word_scores) / len(word_scores), 3) if word_scores else 0.0,
                ))
                current_word = char
                word_start = t_start
                word_end = t_end
                word_scores = [score]
            else:
                if word_start < 0:
                    word_start = t_start
                current_word += char
                word_end = t_end
                word_scores.append(score)

        # 保存最後一個 word
        if current_word.strip():
            words.append(AlignedWord(
                word=current_word.strip(),
                start=round(word_start, 3),
                end=round(word_end, 3),
                score=round(sum(word_scores) / len(word_scores), 3) if word_scores else 0.0,
            ))

        return words


# ═══════════════════════════════════════════════════════════
# 單例工廠函數
# ═══════════════════════════════════════════════════════════
_engine: Optional[AlignmentEngine] = None


def get_alignment_engine() -> AlignmentEngine:
    """取得 AlignmentEngine 單例"""
    global _engine
    if _engine is None:
        _engine = AlignmentEngine()
    return _engine
