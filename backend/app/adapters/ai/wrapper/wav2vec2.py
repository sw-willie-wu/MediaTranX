"""
Wav2Vec2 Forced Alignment engine.
Uses Wav2Vec2 phoneme models to perform forced alignment on Whisper
transcription results, producing precise word-level timestamps.

Does not inherit Runtime -- this is a post-processing tool, released after use.
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
    """An aligned word with timing information."""
    word: str
    start: float
    end: float
    score: float  # alignment confidence score


# HuggingFace Wav2Vec2 model ID for each language
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

# Wav2Vec2 model sample rate
_WAV2VEC2_SR = 16000


class AlignmentEngine:
    """
    Wav2Vec2 Forced Alignment engine.

    Responsibilities:
    1. Load language-specific Wav2Vec2 models
    2. Perform CTC forced alignment on Whisper segments
    3. Return precise word-level timestamps
    """

    def __init__(self):
        self._model: Any = None
        self._processor: Any = None
        self._loaded_lang: Optional[str] = None
        self._device: str = "cpu"

    def is_language_supported(self, language: str) -> bool:
        """Check if the language has a corresponding alignment model."""
        return language in LANG_MODELS

    def get_supported_languages(self) -> list[str]:
        """Get the list of supported languages."""
        return list(LANG_MODELS.keys())

    def align(
        self,
        audio_path: str,
        segments: list,
        language: str,
        on_progress: Optional[Callable[[float, str], None]] = None,
        *,
        ffmpeg_path: str,  # required, kw-only
    ) -> list:
        """
        Perform forced alignment on Whisper segments.

        Args:
            audio_path: Audio file path.
            segments: List of Whisper TranscribeSegment.
            language: Language code (en, zh, ja...).
            on_progress: Progress callback.
            ffmpeg_path: Path to ffmpeg binary (required).

        Returns:
            Corrected TranscribeSegment list (with words attribute).
        """
        if not self.is_language_supported(language):
            logger.warning(f"Language '{language}' not supported for alignment, returning original segments")
            return segments

        if not segments:
            return segments

        # Select device
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

        try:
            # Load model
            if on_progress:
                on_progress(0.0, "task.progress.loading_alignment")
            self._ensure_model(language)

            # Read full audio
            if on_progress:
                on_progress(0.1, "task.progress.reading_audio")
            full_waveform = self._load_audio(audio_path, ffmpeg_path=ffmpeg_path)

            # Per-segment inference (avoid sending entire long audio at once to prevent OOM/stalls)
            from app.adapters.ai.wrapper.whisper import TranscribeSegment

            aligned_segments: list[TranscribeSegment] = []
            total = len(segments)
            pad_sec = 0.5  # extra 0.5s context on each side

            for i, seg in enumerate(segments):
                if on_progress:
                    progress = 0.15 + 0.8 * (i / total)
                    on_progress(progress, f"task.progress.aligning_segment|{i+1}|{total}")

                # Extract segment audio clip (with padding on both sides)
                start_sample = max(0, int((seg.start - pad_sec) * _WAV2VEC2_SR))
                end_sample = min(len(full_waveform), int((seg.end + pad_sec) * _WAV2VEC2_SR))
                seg_waveform = full_waveform[start_sample:end_sample]

                if len(seg_waveform) < 160:  # too short, skip
                    aligned_segments.append(seg)
                    continue

                # Limit single inference length (skip alignment for segments >15s to avoid stalling)
                max_samples = int(15 * _WAV2VEC2_SR)
                if len(seg_waveform) > max_samples:
                    logger.info(f"Segment {i+1} too long ({len(seg_waveform) / _WAV2VEC2_SR:.1f}s), skipping alignment")
                    aligned_segments.append(seg)
                    continue

                # Run inference on this audio segment
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

                # frame duration based on this audio segment
                seg_samples = len(seg_waveform)
                seg_frames = seg_log_probs.shape[0]
                frame_duration = seg_samples / (_WAV2VEC2_SR * seg_frames)

                # Calculate padding offset (alignment result times need to be adjusted)
                actual_start = start_sample / _WAV2VEC2_SR

                # Attempt forced alignment
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
        """Load or switch language model."""
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
        """Unload model."""
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

    def _load_audio(self, audio_path: str, ffmpeg_path: str) -> list[float]:
        """Read audio and resample to 16kHz mono. ffmpeg_path is required."""

        # Use ffmpeg to convert to 16kHz mono PCM
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
        Perform CTC forced alignment on a single segment.

        Uses the Viterbi algorithm to find the optimal path,
        aligning text tokens to frame-level phoneme probabilities.
        """
        if not text.strip():
            return []

        # Tokenize text
        vocab = self._processor.tokenizer.get_vocab()
        inv_vocab = {v: k for k, v in vocab.items()}

        # Get CTC blank token
        blank_id = self._processor.tokenizer.pad_token_id
        if blank_id is None:
            blank_id = 0

        # Convert text to token IDs
        text_clean = text.strip().upper()
        tokens = self._processor.tokenizer.encode(text_clean)
        if not tokens:
            return []

        # Simplified CTC forced alignment:
        # Use greedy decode to find the best position for each token
        num_frames = log_probs.shape[0]
        if num_frames == 0:
            return []

        # Build token-to-frame mapping
        # Strategy: find the frame range with highest probability for each token
        token_frames = self._ctc_align(log_probs, tokens, blank_id)

        if not token_frames:
            return []

        # Merge tokens back into words
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
        CTC forced alignment core.

        Uses dynamic programming to find the optimal position of tokens in frames.
        Returns [(token_id, start_frame, end_frame, score), ...]
        """
        num_frames = log_probs.shape[0]
        num_tokens = len(tokens)

        if num_frames < num_tokens:
            return []

        # Build expanded sequence: blank, t1, blank, t2, blank, ...
        expanded = [blank_id]
        for t in tokens:
            expanded.append(t)
            expanded.append(blank_id)
        num_labels = len(expanded)

        # Viterbi forward pass
        # dp[t][s] = max log probability reaching frame t, label s
        NEG_INF = float('-inf')
        dp = [[NEG_INF] * num_labels for _ in range(num_frames)]
        bp = [[0] * num_labels for _ in range(num_frames)]  # backpointer

        # Initialize the first frame
        dp[0][0] = log_probs[0][expanded[0]].item()
        if num_labels > 1:
            dp[0][1] = log_probs[0][expanded[1]].item()

        # Forward
        for t in range(1, num_frames):
            for s in range(num_labels):
                # Can transition from s (self-loop) or s-1 (advance one step)
                candidates = [(dp[t-1][s], s)]
                if s > 0:
                    candidates.append((dp[t-1][s-1], s-1))
                # If current is not blank and two positions back is not the same token, can skip blank
                if s > 1 and expanded[s] != expanded[s-2]:
                    candidates.append((dp[t-1][s-2], s-2))

                best_val, best_src = max(candidates, key=lambda x: x[0])
                dp[t][s] = best_val + log_probs[t][expanded[s]].item()
                bp[t][s] = best_src

        # Backtrack
        # Must end at the last or second-to-last label
        if dp[num_frames-1][num_labels-1] >= dp[num_frames-1][num_labels-2]:
            s = num_labels - 1
        else:
            s = num_labels - 2

        path = [0] * num_frames
        path[num_frames-1] = s
        for t in range(num_frames - 2, -1, -1):
            s = bp[t+1][path[t+1]]
            path[t] = s

        # Extract frame range for each non-blank token from path
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
                    # Token ended
                    # Calculate score (average log prob over the interval)
                    token_id = expanded[path[start_frame]]
                    score_sum = sum(
                        log_probs[f][token_id].item()
                        for f in range(start_frame, t)
                    )
                    score = score_sum / max(1, t - start_frame)
                    result.append((token_id, start_frame, t - 1, score))
                    in_token = False

        # Handle the last token (if path does not end with blank)
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
        """Merge token-frame mapping into words."""
        if not token_frames:
            return []

        words: list[AlignedWord] = []
        current_word = ""
        word_start = -1.0
        word_end = -1.0
        word_scores: list[float] = []

        for token_id, sf, ef, score in token_frames:
            char = inv_vocab.get(token_id, "")
            # Clean special token prefixes
            char = char.replace("▁", " ").replace("|", " ")

            t_start = segment_start + sf * frame_duration
            t_end = segment_start + (ef + 1) * frame_duration

            if char.startswith(" ") and current_word:
                # New word starts, save the previous one
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

        # Save the last word
        if current_word.strip():
            words.append(AlignedWord(
                word=current_word.strip(),
                start=round(word_start, 3),
                end=round(word_end, 3),
                score=round(sum(word_scores) / len(word_scores), 3) if word_scores else 0.0,
            ))

        return words


# ═══════════════════════════════════════════════════════════
# Singleton factory
# ═══════════════════════════════════════════════════════════
_engine: Optional[AlignmentEngine] = None


def get_alignment_engine() -> AlignmentEngine:
    """Get the AlignmentEngine singleton."""
    global _engine
    if _engine is None:
        _engine = AlignmentEngine()
    return _engine
