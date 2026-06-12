"""
AI model registry (Three-Layer Architecture V2).

Uses a "format-first" tree structure: FORMAT -> FAMILY -> SPECS.
This is the Single Source of Truth for the system.
"""

# ═══════════════════════════════════════════════════════════
# Format Constants
# ═══════════════════════════════════════════════════════════
FORMAT_PKG = "PKG"     # Package-managed models (Whisper, Demucs)
FORMAT_GGUF = "GGUF"   # llama-cpp-python single-file (LLM)
FORMAT_PTH = "PTH"     # PyTorch weight files (CV)
FORMAT_ONNX = "ONNX"   # in-process onnxruntime models (face/SAM/wav2vec2/LaMa/rembg)
FORMAT_NCNN = "NCNN"   # ncnn-vulkan CLI sidecar models (SR/RIFE): .param + .bin pair

# ═══════════════════════════════════════════════════════════
# Slot Constants
# ═══════════════════════════════════════════════════════════
SLOT_WHISPER = "whisper"
SLOT_LLM = "llm"      # Shared LLM slot (only one loaded at a time)
SLOT_PTH = "pth"      # Shared PTH slot (only one loaded at a time)
SLOT_DEMUCS = "demucs"  # Audio source separation (only one loaded at a time)
SLOT_BASIC_PITCH = "basic_pitch"  # Audio-to-MIDI (basic-pitch)
SLOT_RIFE = "rife"
SLOT_SEGMENT = "segment"  # Object segmentation (MobileSAM)

# ═══════════════════════════════════════════════════════════
# Soundfont Constants (MusyngKite GM — managed like a model, NOT a MODELS_REGISTRY FORMAT)
# soundfont 不屬任何 FORMAT；用 loose module-level 常數（比照 SLOT_*）。
# enumerate / download 兩處共用這些常數。
# ═══════════════════════════════════════════════════════════
SOUNDFONT_ID = "soundfont-musyngkite"
SOUNDFONT_LABEL = "MusyngKite GM Soundfont"
SOUNDFONT_SIZE_MB = 267  # 實測值（128 GM 樂器 + 鼓組）
SOUNDFONT_VERSION_TAG = "1"  # 對齊 electron/setup.js 既有 .version，舊使用者免重下
SOUNDFONT_BASE_URL = "https://raw.githubusercontent.com/gleitz/midi-js-soundfonts/gh-pages/MusyngKite"
SOUNDFONT_DRUM_BASE_URL = "https://surikov.github.io/webaudiofontdata/sound"

# ncnn-vulkan SR model files (.param/.bin) are re-hosted on our own release tag
# (D-P1-2: upstream realesrgan zip ships no LICENSE; bilibili real-cugan weights
# are unlicensed — R6). The download service builds each file's URL as
# f"{_NCNN_BASE_URL}/{filename}". See plan Task 1 (packager → ncnn-models-v1).
_NCNN_BASE_URL = "https://github.com/sw-willie-wu/MediaTranX/releases/download/ncnn-models-v1"

# 128 General MIDI instruments (移植自 electron/setup.js GM_INSTRUMENTS)
GM_INSTRUMENTS = [
    "acoustic_grand_piano", "bright_acoustic_piano", "electric_grand_piano", "honkytonk_piano",
    "electric_piano_1", "electric_piano_2", "harpsichord", "clavinet",
    "celesta", "glockenspiel", "music_box", "vibraphone", "marimba", "xylophone", "tubular_bells", "dulcimer",
    "drawbar_organ", "percussive_organ", "rock_organ", "church_organ", "reed_organ", "accordion", "harmonica", "tango_accordion",
    "acoustic_guitar_nylon", "acoustic_guitar_steel", "electric_guitar_jazz", "electric_guitar_clean",
    "electric_guitar_muted", "overdriven_guitar", "distortion_guitar", "guitar_harmonics",
    "acoustic_bass", "electric_bass_finger", "electric_bass_pick", "fretless_bass",
    "slap_bass_1", "slap_bass_2", "synth_bass_1", "synth_bass_2",
    "violin", "viola", "cello", "contrabass", "tremolo_strings", "pizzicato_strings", "orchestral_harp", "timpani",
    "string_ensemble_1", "string_ensemble_2", "synth_strings_1", "synth_strings_2",
    "choir_aahs", "voice_oohs", "synth_choir", "orchestra_hit",
    "trumpet", "trombone", "tuba", "muted_trumpet", "french_horn", "brass_section", "synth_brass_1", "synth_brass_2",
    "soprano_sax", "alto_sax", "tenor_sax", "baritone_sax", "oboe", "english_horn", "bassoon", "clarinet",
    "piccolo", "flute", "recorder", "pan_flute", "blown_bottle", "shakuhachi", "whistle", "ocarina",
    "lead_1_square", "lead_2_sawtooth", "lead_3_calliope", "lead_4_chiff",
    "lead_5_charang", "lead_6_voice", "lead_7_fifths", "lead_8_bass__lead",
    "pad_1_new_age", "pad_2_warm", "pad_3_polysynth", "pad_4_choir",
    "pad_5_bowed", "pad_6_metallic", "pad_7_halo", "pad_8_sweep",
    "fx_1_rain", "fx_2_soundtrack", "fx_3_crystal", "fx_4_atmosphere",
    "fx_5_brightness", "fx_6_goblins", "fx_7_echoes", "fx_8_scifi",
    "sitar", "banjo", "shamisen", "koto", "kalimba", "bagpipe", "fiddle", "shanai",
    "tinkle_bell", "agogo", "steel_drums", "woodblock", "taiko_drum", "melodic_tom", "synth_drum", "reverse_cymbal",
    "guitar_fret_noise", "breath_noise", "seashore", "bird_tweet",
    "telephone_ring", "helicopter", "applause", "gunshot",
]

# ═══════════════════════════════════════════════════════════
# Format-First Registry
# ═══════════════════════════════════════════════════════════

MODELS_REGISTRY = {
    # ───────────────────────────────────────────────────────
    # PKG format: Package-managed models (Whisper, Demucs)
    # ───────────────────────────────────────────────────────
    FORMAT_PKG: {
        "whisper": {
            "slot": SLOT_WHISPER,
            "label": "Whisper",
            "category": "stt",
            "description": "models.whisper",
            "variants": {
                "tiny": {
                    "label": "tiny",
                    "repo_id": "Systran/faster-whisper-tiny",
                    "size_mb": 75,
                    "vram_mb": 500,
                    "description": "models.whisper.tiny",
                },
                "base": {
                    "label": "base",
                    "repo_id": "Systran/faster-whisper-base",
                    "size_mb": 145,
                    "vram_mb": 700,
                    "description": "models.whisper.base",
                },
                "small": {
                    "label": "small",
                    "repo_id": "Systran/faster-whisper-small",
                    "size_mb": 465,
                    "vram_mb": 1500,
                    "description": "models.whisper.small",
                },
                "medium": {
                    "label": "medium",
                    "repo_id": "Systran/faster-whisper-medium",
                    "size_mb": 1534,
                    "vram_mb": 3000,
                    "description": "models.whisper.medium",
                },
                "large-v3": {
                    "label": "large-v3",
                    "repo_id": "Systran/faster-whisper-large-v3",
                    "size_mb": 3072,
                    "vram_mb": 5000,
                    "description": "models.whisper.large_v3",
                },
            },
        },
        # ▸ Demucs (audio source separation)
        "demucs": {
            "slot": SLOT_DEMUCS,
            "label": "HTDemucs",
            "category": "separate",
            "description": "models.demucs",
            "variants": {
                "htdemucs_6s": {
                    "label": "6-stem",
                    "model_name": "htdemucs_6s",
                    "size_mb": 320,
                    "vram_mb": 2000,
                    "sources": ["drums", "bass", "other", "vocals", "guitar", "piano"],
                    "sample_rate": 44100,
                },
            },
        },
        # ▸ Basic Pitch (audio-to-MIDI)
        "basic_pitch": {
            "slot": SLOT_BASIC_PITCH,
            "label": "Basic Pitch",
            "category": "midi",
            "description": "models.basic_pitch",
            "variants": {
                "default": {
                    "label": "ICASSP 2022",
                    "model_name": "basic_pitch",
                    "size_mb": 10,
                    "vram_mb": 0,
                },
            },
        },
        # ▸ RIFE (video frame interpolation)
        "rife": {
            "slot": SLOT_RIFE,
            "label": "RIFE",
            "category": "interpolate",
            "description": "models.rife",
            "variants": {
                "v4.26": {
                    "label": "v4.26",
                    "url": "https://huggingface.co/hzwer/RIFE/resolve/main/RIFEv4.26_0921.zip",
                    "zip_entry": "RIFEv4.26_0921/flownet.pkl",
                    "filename": "flownet-v4.26.pkl",
                    "size_mb": 23,
                    "vram_mb": 1500,
                },
            },
        },
    },

    # ───────────────────────────────────────────────────────
    # GGUF format: llama-server models (text + vision-language models)
    # ───────────────────────────────────────────────────────
    FORMAT_GGUF: {
        "qwen3": {
            "slot": SLOT_LLM,
            "label": "Qwen3",
            "capabilities": ["text", "tools"],
            "description": "models.qwen3",
            "inference": {
                "translate": {
                    "temperature": 0.1, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "qwen3", "thinking": False,
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 4, "max_tokens_cap": 16384,
                },
                "summarize": {
                    "temperature": 0.3, "top_k": 50, "top_p": 0.95,
                    "prompt_builder": "qwen3", "thinking": False,
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 0.5, "max_tokens_cap": 4096,
                },
            },
            "specs": {
                "1.7b": {
                    "layers": 28,
                    "n_ctx_min": 2048, "n_ctx_max": 32768, "n_ctx_default": 4096, "vram_per_ctx_token": 0.02, "max_srt_batch": 15,
                    "vram_overhead_mb": 300,
                    "variants": {
                        "Q8_0": {
                            "repo_id": "Qwen/Qwen3-1.7B-GGUF",
                            "filename": "Qwen3-1.7B-Q8_0.gguf",
                            "size_mb": 1830,
                        },
                    },
                },
                "4b": {
                    "layers": 36,
                    "n_ctx_min": 4096, "n_ctx_max": 32768, "n_ctx_default": 8192, "vram_per_ctx_token": 0.03, "max_srt_batch": 15,
                    "vram_overhead_mb": 400,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "Qwen/Qwen3-4B-GGUF",
                            "filename": "Qwen3-4B-Q4_K_M.gguf",
                            "size_mb": 2500,
                        },
                    },
                },
                "8b": {
                    "layers": 36,
                    "n_ctx_min": 4096, "n_ctx_max": 32768, "n_ctx_default": 16384, "vram_per_ctx_token": 0.04,
                    "vram_overhead_mb": 800,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "Qwen/Qwen3-8B-GGUF",
                            "filename": "Qwen3-8B-Q4_K_M.gguf",
                            "size_mb": 5030,
                        },
                    },
                },
                "14b": {
                    "layers": 40,
                    "n_ctx_min": 4096, "n_ctx_max": 32768, "n_ctx_default": 16384, "vram_per_ctx_token": 0.05,
                    "vram_overhead_mb": 1000,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "Qwen/Qwen3-14B-GGUF",
                            "filename": "Qwen3-14B-Q4_K_M.gguf",
                            "size_mb": 9000,
                        },
                        # --- Simplified: keep only Q4_K_M; lower quants save little VRAM but degrade quality ---
                        # "Q4_K_S": {
                        #     "repo_id": "unsloth/Qwen3-14B-GGUF",
                        #     "filename": "Qwen3-14B-Q4_K_S.gguf",
                        #     "size_mb": 8570,
                        # },
                        # "Q3_K_M": {
                        #     "repo_id": "unsloth/Qwen3-14B-GGUF",
                        #     "filename": "Qwen3-14B-Q3_K_M.gguf",
                        #     "size_mb": 7320,
                        # },
                        # "Q3_K_S": {
                        #     "repo_id": "unsloth/Qwen3-14B-GGUF",
                        #     "filename": "Qwen3-14B-Q3_K_S.gguf",
                        #     "size_mb": 6660,
                        # },
                    },
                },
            },
            "default_variant": {
                "1.7b": "Q8_0",
                "4b": "Q4_K_M",
                "8b": "Q4_K_M",
                "14b": "Q4_K_M",
            },
        },

        # ▸ Qwen3-VL
        "qwen3vl": {
            "slot": SLOT_LLM,
            "label": "Qwen3-VL",
            "capabilities": ["vision", "tools"],
            "description": "models.qwen3vl",
            "inference": {
                "ocr": {
                    "temperature": 0.0, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "context_ratio", "max_tokens_ratio": 0.5,
                },
                "frame_select": {
                    "temperature": 0.0, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "fixed", "max_tokens_cap": 16,
                    "max_image_edge": 768,  # Task-1 spike sweet spot (2026-05-19)
                },
            },
            "specs": {
                "2b": {
                    "layers": 28,
                    "n_ctx_min": 2048, "n_ctx_max": 32768, "n_ctx_default": 4096, "vram_per_ctx_token": 0.02,
                    "vram_overhead_mb": 500,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "Qwen/Qwen3-VL-2B-Instruct-GGUF",
                            "filename": "Qwen3VL-2B-Instruct-Q4_K_M.gguf",
                            "mmproj_repo_id": "Qwen/Qwen3-VL-2B-Instruct-GGUF",
                            "mmproj_filename": "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
                            "size_mb": 1110,
                            "mmproj_size_mb": 445,
                        },
                        # --- Simplified: small model Q8_0 is large with limited quality improvement ---
                        # "Q8_0": {
                        #     "repo_id": "Qwen/Qwen3-VL-2B-Instruct-GGUF",
                        #     "filename": "Qwen3VL-2B-Instruct-Q8_0.gguf",
                        #     "mmproj_repo_id": "Qwen/Qwen3-VL-2B-Instruct-GGUF",
                        #     "mmproj_filename": "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
                        #     "size_mb": 1830,
                        #     "mmproj_size_mb": 445,
                        # },
                    },
                },
                "4b": {
                    "layers": 36,
                    "n_ctx_min": 4096, "n_ctx_max": 32768, "n_ctx_default": 8192, "vram_per_ctx_token": 0.03,
                    "vram_overhead_mb": 600,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
                            "filename": "Qwen3VL-4B-Instruct-Q4_K_M.gguf",
                            "mmproj_repo_id": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
                            "mmproj_filename": "mmproj-Qwen3VL-4B-Instruct-Q8_0.gguf",
                            "size_mb": 2500,
                            "mmproj_size_mb": 454,
                        },
                        # --- Simplified: small model Q8_0 is large with limited quality improvement ---
                        # "Q8_0": {
                        #     "repo_id": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
                        #     "filename": "Qwen3VL-4B-Instruct-Q8_0.gguf",
                        #     "mmproj_repo_id": "Qwen/Qwen3-VL-4B-Instruct-GGUF",
                        #     "mmproj_filename": "mmproj-Qwen3VL-4B-Instruct-Q8_0.gguf",
                        #     "size_mb": 4280,
                        #     "mmproj_size_mb": 454,
                        # },
                    },
                },
                "8b": {
                    "layers": 36,
                    "n_ctx_min": 4096, "n_ctx_max": 32768, "n_ctx_default": 16384, "vram_per_ctx_token": 0.04,
                    "vram_overhead_mb": 800,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "Qwen/Qwen3-VL-8B-Instruct-GGUF",
                            "filename": "Qwen3VL-8B-Instruct-Q4_K_M.gguf",
                            "mmproj_repo_id": "Qwen/Qwen3-VL-8B-Instruct-GGUF",
                            "mmproj_filename": "mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf",
                            "size_mb": 5030,
                            "mmproj_size_mb": 752,
                        },
                    },
                },
            },
            "default_variant": {
                "2b": "Q4_K_M",
                "4b": "Q4_K_M",
                "8b": "Q4_K_M",
            },
        },

        # ▸ InternVL2.5
        "internvl2.5": {
            "slot": SLOT_LLM,
            "label": "InternVL2.5",
            "capabilities": ["text", "vision"],
            "description": "models.internvl2_5",
            "inference": {
                "translate": {
                    "temperature": 0.1, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 4, "max_tokens_cap": 16384,
                },
                "summarize": {
                    "temperature": 0.3, "top_k": 50, "top_p": 0.95,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 0.5, "max_tokens_cap": 4096,
                },
                "ocr": {
                    "temperature": 0.0, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "context_ratio", "max_tokens_ratio": 0.5,
                },
                "frame_select": {
                    "temperature": 0.0, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "fixed", "max_tokens_cap": 16,
                    "max_image_edge": 1024,  # conservative; un-measured (per-family tuning = follow-up)
                },
            },
            "specs": {
                "1b": {
                    "layers": 24,
                    "n_ctx_min": 2048, "n_ctx_max": 8192, "n_ctx_default": 4096, "vram_per_ctx_token": 0.02, "max_srt_batch": 15,
                    "vram_overhead_mb": 400,
                    "variants": {
                        "Q8_0": {
                            "repo_id": "ggml-org/InternVL2_5-1B-GGUF",
                            "filename": "InternVL2_5-1B-Q8_0.gguf",
                            "mmproj_repo_id": "ggml-org/InternVL2_5-1B-GGUF",
                            "mmproj_filename": "mmproj-InternVL2_5-1B-Q8_0.gguf",
                            "size_mb": 675,
                            "mmproj_size_mb": 333,
                        },
                    },
                },
                "4b": {
                    "layers": 36,
                    "n_ctx_min": 4096, "n_ctx_max": 8192, "n_ctx_default": 8192, "vram_per_ctx_token": 0.03, "max_srt_batch": 15,
                    "vram_overhead_mb": 600,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "ggml-org/InternVL2_5-4B-GGUF",
                            "filename": "InternVL2_5-4B-Q4_K_M.gguf",
                            "mmproj_repo_id": "ggml-org/InternVL2_5-4B-GGUF",
                            "mmproj_filename": "mmproj-InternVL2_5-4B-Q8_0.gguf",
                            "size_mb": 2100,
                            "mmproj_size_mb": 341,
                        },
                        # --- Simplified: small model Q8_0 is large with limited quality improvement ---
                        # "Q8_0": {
                        #     "repo_id": "ggml-org/InternVL2_5-4B-GGUF",
                        #     "filename": "InternVL2_5-4B-Q8_0.gguf",
                        #     "mmproj_repo_id": "ggml-org/InternVL2_5-4B-GGUF",
                        #     "mmproj_filename": "mmproj-InternVL2_5-4B-Q8_0.gguf",
                        #     "size_mb": 3610,
                        #     "mmproj_size_mb": 341,
                        # },
                    },
                },
            },
            "default_variant": {
                "1b": "Q8_0",
                "4b": "Q4_K_M",
            },
        },

        # ▸ Gemma 3
        "gemma3": {
            "slot": SLOT_LLM,
            "label": "Gemma3",
            "capabilities": ["text"],
            "description": "models.gemma3",
            "inference": {
                "translate": {
                    "temperature": 0.1, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "gemma",
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 4, "max_tokens_cap": 16384,
                },
                "summarize": {
                    "temperature": 0.3, "top_k": 50, "top_p": 0.95,
                    "prompt_builder": "gemma",
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 0.5, "max_tokens_cap": 4096,
                },
            },
            "specs": {
                "4b": {
                    "layers": 34,
                    "n_ctx_min": 2048, "n_ctx_max": 32768, "n_ctx_default": 8192, "vram_per_ctx_token": 0.03, "max_srt_batch": 15,
                    "vram_overhead_mb": 600,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "ggml-org/gemma-3-4b-it-GGUF",
                            "filename": "gemma-3-4b-it-Q4_K_M.gguf",
                            "mmproj_repo_id": "ggml-org/gemma-3-4b-it-GGUF",
                            "mmproj_filename": "mmproj-gemma3-4b-f16.gguf",
                            "mmproj_remote_filename": "mmproj-model-f16.gguf",
                            "size_mb": 2490,
                            "mmproj_size_mb": 851,
                        },
                    },
                },
                "12b": {
                    "layers": 46,
                    "n_ctx_min": 4096, "n_ctx_max": 32768, "n_ctx_default": 16384, "vram_per_ctx_token": 0.05,
                    "vram_overhead_mb": 800,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "ggml-org/gemma-3-12b-it-GGUF",
                            "filename": "gemma-3-12b-it-Q4_K_M.gguf",
                            "mmproj_repo_id": "ggml-org/gemma-3-12b-it-GGUF",
                            "mmproj_filename": "mmproj-gemma3-12b-f16.gguf",
                            "mmproj_remote_filename": "mmproj-model-f16.gguf",
                            "size_mb": 7300,
                            "mmproj_size_mb": 854,
                        },
                    },
                },
            },
            "default_variant": {
                "4b": "Q4_K_M",
                "12b": "Q4_K_M",
            },
        },

        # ▸ Gemma 4 (Expert MoE architecture: E2B, E4B, 26B-A4B)
        "gemma4": {
            "slot": SLOT_LLM,
            "label": "Gemma4",
            "capabilities": ["text", "vision", "tools"],
            "description": "models.gemma4",
            "inference": {
                "translate": {
                    "temperature": 0.1, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "gemma",
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 4, "max_tokens_cap": 16384,
                },
                "summarize": {
                    "temperature": 0.3, "top_k": 50, "top_p": 0.95,
                    "prompt_builder": "gemma",
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 0.5, "max_tokens_cap": 4096,
                },
                "ocr": {
                    "temperature": 0.0, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "gemma",
                    "max_tokens_strategy": "context_ratio", "max_tokens_ratio": 0.5,
                },
                "frame_select": {
                    "temperature": 0.0, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "gemma",
                    "max_tokens_strategy": "fixed", "max_tokens_cap": 16,
                    "max_image_edge": 1024,  # conservative; un-measured (per-family tuning = follow-up)
                },
            },
            "specs": {
                "e2b": {
                    "layers": 26,
                    "n_ctx_min": 2048, "n_ctx_max": 131072, "n_ctx_default": 8192, "vram_per_ctx_token": 0.02, "max_srt_batch": 15,
                    "vram_overhead_mb": 500,
                    "variants": {
                        # HF repo paths are case-sensitive — must use uppercase E2B
                        # (matches the repo's actual filenames). Lowercase forms 404.
                        "Q8_0": {
                            "repo_id": "ggml-org/gemma-4-E2B-it-GGUF",
                            "filename": "gemma-4-E2B-it-Q8_0.gguf",
                            "mmproj_repo_id": "ggml-org/gemma-4-E2B-it-GGUF",
                            "mmproj_filename": "mmproj-gemma-4-E2B-it-bf16.gguf",
                            "size_mb": 5090,
                            "mmproj_size_mb": 987,
                        },
                    },
                },
                "e4b": {
                    "layers": 34,
                    "n_ctx_min": 4096, "n_ctx_max": 131072, "n_ctx_default": 16384, "vram_per_ctx_token": 0.03, "max_srt_batch": 15,
                    "vram_overhead_mb": 600,
                    "variants": {
                        # HF repo paths are case-sensitive — must use uppercase E4B
                        # (matches the repo's actual filenames). Lowercase forms 404.
                        "Q4_K_M": {
                            "repo_id": "ggml-org/gemma-4-E4B-it-GGUF",
                            "filename": "gemma-4-E4B-it-Q4_K_M.gguf",
                            "mmproj_repo_id": "ggml-org/gemma-4-E4B-it-GGUF",
                            "mmproj_filename": "mmproj-gemma-4-E4B-it-bf16.gguf",
                            "size_mb": 5470,
                            "mmproj_size_mb": 992,
                        },
                    },
                },
                "26b": {
                    "layers": 46,
                    "n_ctx_min": 8192, "n_ctx_max": 131072, "n_ctx_default": 32768, "vram_per_ctx_token": 0.06,
                    "vram_overhead_mb": 1200,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "ggml-org/gemma-4-26B-A4B-it-GGUF",
                            "filename": "gemma-4-26B-A4B-it-Q4_K_M.gguf",
                            "mmproj_repo_id": "ggml-org/gemma-4-26B-A4B-it-GGUF",
                            "mmproj_filename": "mmproj-gemma-4-26B-A4B-it-f16.gguf",
                            "size_mb": 17203,
                            "mmproj_size_mb": 1219,
                        },
                    },
                },
            },
            "default_variant": {
                "e2b": "Q8_0",
                "e4b": "Q4_K_M",
                "26b": "Q4_K_M",
            },
        },

        # ▸ Qwen3.5
        "qwen3.5": {
            "slot": SLOT_LLM,
            "label": "Qwen3.5",
            "capabilities": ["text", "vision", "tools"],
            "description": "models.qwen3_5",
            "inference": {
                "translate": {
                    "temperature": 0.1, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 4, "max_tokens_cap": 16384,
                },
                "summarize": {
                    "temperature": 0.3, "top_k": 50, "top_p": 0.95,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "input_ratio", "max_tokens_ratio": 0.5, "max_tokens_cap": 4096,
                },
                "ocr": {
                    "temperature": 0.0, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "context_ratio", "max_tokens_ratio": 0.5,
                },
                "frame_select": {
                    "temperature": 0.0, "top_k": 40, "top_p": 0.9,
                    "prompt_builder": "default",
                    "max_tokens_strategy": "fixed", "max_tokens_cap": 16,
                    "max_image_edge": 1024,  # conservative; un-measured (per-family tuning = follow-up)
                },
            },
            "specs": {
                "4b": {
                    "layers": 36,
                    "n_ctx_min": 4096, "n_ctx_max": 131072, "n_ctx_default": 8192, "vram_per_ctx_token": 0.03, "max_srt_batch": 15,
                    "vram_overhead_mb": 500,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "unsloth/Qwen3.5-4B-GGUF",
                            "filename": "Qwen3.5-4B-Q4_K_M.gguf",
                            "mmproj_repo_id": "unsloth/Qwen3.5-4B-GGUF",
                            "mmproj_filename": "mmproj-F16.gguf",
                            "size_mb": 2610,
                            "mmproj_size_mb": 641,
                        },
                    },
                },
                "9b": {
                    "layers": 48,
                    "n_ctx_min": 4096, "n_ctx_max": 131072, "n_ctx_default": 16384, "vram_per_ctx_token": 0.04,
                    "vram_overhead_mb": 600,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "unsloth/Qwen3.5-9B-GGUF",
                            "filename": "Qwen3.5-9B-Q4_K_M.gguf",
                            "mmproj_repo_id": "unsloth/Qwen3.5-9B-GGUF",
                            "mmproj_filename": "mmproj-F16.gguf",
                            "size_mb": 5420,
                            "mmproj_size_mb": 876,
                        },
                    },
                },
                "27b": {
                    "layers": 64,
                    "n_ctx_min": 8192, "n_ctx_max": 131072, "n_ctx_default": 32768, "vram_per_ctx_token": 0.06,
                    "vram_overhead_mb": 800,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "unsloth/Qwen3.5-27B-GGUF",
                            "filename": "Qwen3.5-27B-Q4_K_M.gguf",
                            "mmproj_repo_id": "unsloth/Qwen3.5-27B-GGUF",
                            "mmproj_filename": "mmproj-F16.gguf",
                            "size_mb": 15970,
                            "mmproj_size_mb": 885,
                        },
                    },
                },
            },
            "default_variant": {
                "4b": "Q4_K_M",
                "9b": "Q4_K_M",
                "27b": "Q4_K_M",
            },
        },
    },

    # ───────────────────────────────────────────────────────
    # PTH format: PyTorch image processing models
    # ───────────────────────────────────────────────────────
    FORMAT_PTH: {
        # ▸ Real-ESRGAN series
        "realesrgan": {
            "slot": "realesrgan",
            "label": "Real-ESRGAN",
            "category": "upscale",
            "description": "models.realesrgan",
            "variants": {
                "x2plus": {
                    "label": "2x",
                    "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
                    "filename": "RealESRGAN_x2plus.pth",
                    "size_mb": 64,
                    "vram_mb": 1500,
                    "scale": 2,
                    "arch": "RRDBNet",
                },
                "x4plus": {
                    "label": "4x",
                    "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
                    "filename": "RealESRGAN_x4plus.pth",
                    "size_mb": 64,
                    "vram_mb": 2000,
                    "scale": 4,
                    "arch": "RRDBNet",
                },
                "x4plus-anime": {
                    "label": "4x - anime",
                    "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth",
                    "filename": "RealESRGAN_x4plus_anime_6B.pth",
                    "size_mb": 18,
                    "vram_mb": 2000,
                    "scale": 4,
                    "arch": "RRDBNet",
                },
                "animevideov3": {
                    "label": "4x - video",
                    "url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth",
                    "filename": "realesr-animevideov3.pth",
                    "size_mb": 2,
                    "vram_mb": 500,
                    "scale": 4,
                    "arch": "SRVGGNetCompact",
                    "subcategory": "video_enhance",
                },
            },
        },
        
        # ▸ SwinIR series
        "swinir": {
            "slot": "swinir",
            "label": "SwinIR",
            "category": "upscale",
            "description": "models.swinir",
            "variants": {
                "lightweight-x4": {
                    "label": "4x - lightweight",
                    "url": "https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/002_lightweightSR_DIV2K_s64w8_SwinIR-S_x4.pth",
                    "filename": "SwinIR-S_Lightweight_x4.pth",
                    "size_mb": 12,
                    "vram_mb": 1800,
                    "scale": 4,
                },
                "classical-x4": {
                    "label": "4x - classical",
                    "url": "https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/001_classicalSR_DIV2K_s48w8_SwinIR-M_x4.pth",
                    "filename": "SwinIR-M_Classical_x4.pth",
                    "size_mb": 28,
                    "vram_mb": 2500,
                    "scale": 4,
                },
                "realworld-x4": {
                    "label": "4x - realworld",
                    "url": "https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/003_realSR_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth",
                    "filename": "SwinIR-L_RealWorld_x4.pth",
                    "size_mb": 129,
                    "vram_mb": 3500,
                    "scale": 4,
                },
            },
        },
        
        # ▸ BSRGAN
        "bsrgan": {
            "slot": "bsrgan",
            "label": "BSRGAN",
            "category": "upscale",
            "description": "models.bsrgan",
            "variants": {
                "default": {
                    "label": "4x",
                    "url": "https://github.com/cszn/KAIR/releases/download/v1.0/BSRGAN.pth",
                    "filename": "BSRGAN.pth",
                    "size_mb": 64,
                    "vram_mb": 2200,
                    "scale": 4,
                },
            },
        },
        
        # ▸ Real-CUGAN series
        # Note: all variants come from the same archive and are auto-extracted after download
        # Archive structure: updated_weights/up{2,3,4}x-latest-{variant}.pth
        "real-cugan": {
            "slot": "real-cugan",
            "label": "Real-CUGAN",
            "category": "upscale",
            "description": "models.real_cugan",
            "variants": {
                "up2x-conservative": {
                    "label": "2x - conservative",
                    "url": "https://github.com/bilibili/ailab/releases/download/Real-CUGAN/updated_weights.zip",
                    "filename": "real-cugan-up2x-conservative.pth",
                    "unzip": True,
                    "archive_path": "updated_weights/up2x-latest-conservative.pth",
                    "size_mb": 16,
                    "vram_mb": 1200,
                    "scale": 2,
                    "denoise_level": 0,
                },
                # "up2x-denoise3x": {
                #     "url": "https://github.com/bilibili/ailab/releases/download/Real-CUGAN/updated_weights.zip",
                #     "filename": "real-cugan-up2x-denoise3x.pth",
                #     "unzip": True,
                #     "archive_path": "updated_weights/up2x-latest-denoise3x.pth",
                #     "size_mb": 16,
                #     "vram_mb": 1200,
                #     "scale": 2,
                #     "denoise_level": 3,
                # },
                # --- Simplified: conservative covers light denoising; no-denoise use case is rare ---
                # "up2x-no-denoise": {
                #     "url": "https://github.com/bilibili/ailab/releases/download/Real-CUGAN/updated_weights.zip",
                #     "filename": "real-cugan-up2x-no-denoise.pth",
                #     "unzip": True,
                #     "archive_path": "updated_weights/up2x-latest-no-denoise.pth",
                #     "size_mb": 16,
                #     "vram_mb": 1000,
                #     "scale": 2,
                #     "denoise_level": -1,
                # },
                "up3x-conservative": {
                    "label": "3x - conservative",
                    "url": "https://github.com/bilibili/ailab/releases/download/Real-CUGAN/updated_weights.zip",
                    "filename": "real-cugan-up3x-conservative.pth",
                    "unzip": True,
                    "archive_path": "updated_weights/up3x-latest-conservative.pth",
                    "size_mb": 16,
                    "vram_mb": 1500,
                    "scale": 3,
                    "denoise_level": 0,
                },
                # --- Simplified: conservative covers light denoising ---
                # "up3x-no-denoise": {
                #     "url": "https://github.com/bilibili/ailab/releases/download/Real-CUGAN/updated_weights.zip",
                #     "filename": "real-cugan-up3x-no-denoise.pth",
                #     "unzip": True,
                #     "archive_path": "updated_weights/up3x-latest-no-denoise.pth",
                #     "size_mb": 16,
                #     "vram_mb": 1300,
                #     "scale": 3,
                #     "denoise_level": -1,
                # },
                "up4x-conservative": {
                    "label": "4x - conservative",
                    "url": "https://github.com/bilibili/ailab/releases/download/Real-CUGAN/updated_weights.zip",
                    "filename": "real-cugan-up4x-conservative.pth",
                    "unzip": True,
                    "archive_path": "updated_weights/up4x-latest-conservative.pth",
                    "size_mb": 16,
                    "vram_mb": 1800,
                    "scale": 4,
                    "denoise_level": 0,
                },
                # --- Simplified: conservative covers light denoising ---
                # "up4x-no-denoise": {
                #     "url": "https://github.com/bilibili/ailab/releases/download/Real-CUGAN/updated_weights.zip",
                #     "filename": "real-cugan-up4x-no-denoise.pth",
                #     "unzip": True,
                #     "archive_path": "updated_weights/up4x-latest-no-denoise.pth",
                #     "size_mb": 16,
                #     "vram_mb": 1600,
                #     "scale": 4,
                #     "denoise_level": -1,
                # },
            },
        },
        
        # ▸ GFPGAN
        "gfpgan": {
            "slot": "gfpgan",
            "label": "GFPGAN",
            "category": "face_restore",
            "description": "models.gfpgan",
            "variants": {
                "v1.4": {
                    "label": "v1.4",
                    "url": "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
                    "filename": "GFPGANv1.4.pth",
                    "size_mb": 348,
                    "vram_mb": 2000,
                },
            },
        },

        # ▸ MobileSAM (for AI object removal)
        "mobilesam": {
            "slot": "mobilesam",
            "label": "MobileSAM",
            "category": "segment",
            "description": "models.mobilesam",
            "variants": {
                "default": {
                    "label": "v1.0",
                    "url": "https://huggingface.co/dhkim2810/MobileSAM/resolve/main/mobile_sam.pt",
                    "filename": "mobile_sam.pt",
                    "size_mb": 39,
                    "vram_mb": 500,
                },
            },
        },

        # ▸ Waifu2x series
        "waifu2x": {
            "slot": "waifu2x",
            "label": "Waifu2x",
            "category": "upscale",
            "description": "models.waifu2x",
            "variants": {
                "cunet-art-2x": {
                    "label": "2x - cunet",
                    "url": "https://github.com/nagadomi/nunif/releases/download/0.0.0/waifu2x_pretrained_models_20250502.zip",
                    "filename": "waifu2x_cunet_art_2x.pth",
                    "unzip": True,
                    "archive_path": "pretrained_models/cunet/art/scale2x.pth",
                    "size_mb": 440,
                    "vram_mb": 1200,
                    "scale": 2,
                },
                # cunet-art-4x and swin-unet variants removed:
                # nunif's 4x models use SwinUNet architecture (not CUNet),
                # which is not supported by Spandrel.
            },
        },
    },

    # ───────────────────────────────────────────────────────
    # NCNN format: ncnn-vulkan CLI sidecar SR models (Phase 1).
    # Family slot/label/description/category are copied VERBATIM from the
    # FORMAT_PTH originals so the UI text does not drift during the T3→T11
    # transition window (Task 11 removes the shadowed PTH trio). Per-file URL
    # is built by the download service from _NCNN_BASE_URL + filename (D-P1-2).
    # Real-ESRGAN x2plus is DROPPED (no ncnn model); the single PTH
    # animevideov3 (4x) splits into three explicit ncnn variants (x2/x3/x4).
    # ───────────────────────────────────────────────────────
    FORMAT_NCNN: {
        # ▸ Real-ESRGAN series (exe: realesrgan-ncnn-vulkan; -n <name> -s <scale>)
        "realesrgan": {
            "slot": "realesrgan",
            "label": "Real-ESRGAN",
            "category": "upscale",
            "description": "models.realesrgan",
            "variants": {
                "x4plus": {
                    "label": "4x",
                    "exe_tool": "realesrgan",
                    "cli_model_name": "realesrgan-x4plus",
                    "files": ["realesrgan-x4plus.param", "realesrgan-x4plus.bin"],
                    "size_mb": 32,
                    "vram_mb": 2000,
                    "scale": 4,
                },
                "x4plus-anime": {
                    "label": "4x - anime",
                    "exe_tool": "realesrgan",
                    "cli_model_name": "realesrgan-x4plus-anime",
                    "files": ["realesrgan-x4plus-anime.param", "realesrgan-x4plus-anime.bin"],
                    "size_mb": 9,
                    "vram_mb": 2000,
                    "scale": 4,
                },
                "animevideov3-x2": {
                    "label": "2x - video",
                    "exe_tool": "realesrgan",
                    "cli_model_name": "realesr-animevideov3-x2",
                    "files": ["realesr-animevideov3-x2.param", "realesr-animevideov3-x2.bin"],
                    "size_mb": 2,
                    "vram_mb": 500,
                    "scale": 2,
                    "subcategory": "video_enhance",
                },
                "animevideov3-x3": {
                    "label": "3x - video",
                    "exe_tool": "realesrgan",
                    "cli_model_name": "realesr-animevideov3-x3",
                    "files": ["realesr-animevideov3-x3.param", "realesr-animevideov3-x3.bin"],
                    "size_mb": 2,
                    "vram_mb": 500,
                    "scale": 3,
                    "subcategory": "video_enhance",
                },
                "animevideov3-x4": {
                    "label": "4x - video",
                    "exe_tool": "realesrgan",
                    "cli_model_name": "realesr-animevideov3-x4",
                    "files": ["realesr-animevideov3-x4.param", "realesr-animevideov3-x4.bin"],
                    "size_mb": 2,
                    "vram_mb": 500,
                    "scale": 4,
                    "subcategory": "video_enhance",
                },
            },
        },

        # ▸ Waifu2x series (exe: waifu2x-ncnn-vulkan; -n -1 -s 2 → scale2.0x_model)
        "waifu2x": {
            "slot": "waifu2x",
            "label": "Waifu2x",
            "category": "upscale",
            "description": "models.waifu2x",
            "variants": {
                "cunet-art-2x": {
                    "label": "2x - cunet",
                    "exe_tool": "waifu2x",
                    "cli_noise": -1,
                    "files": ["scale2.0x_model.param", "scale2.0x_model.bin"],
                    "size_mb": 3,
                    "vram_mb": 1200,
                    "scale": 2,
                },
            },
        },

        # ▸ Real-CUGAN series (exe: realcugan-ncnn-vulkan; -n -1 -s {2,3,4} → up{s}x-conservative)
        "real-cugan": {
            "slot": "real-cugan",
            "label": "Real-CUGAN",
            "category": "upscale",
            "description": "models.real_cugan",
            "variants": {
                "up2x-conservative": {
                    "label": "2x - conservative",
                    "exe_tool": "realcugan",
                    "cli_noise": -1,
                    "files": ["up2x-conservative.param", "up2x-conservative.bin"],
                    "size_mb": 3,
                    "vram_mb": 1200,
                    "scale": 2,
                },
                "up3x-conservative": {
                    "label": "3x - conservative",
                    "exe_tool": "realcugan",
                    "cli_noise": -1,
                    "files": ["up3x-conservative.param", "up3x-conservative.bin"],
                    "size_mb": 3,
                    "vram_mb": 1500,
                    "scale": 3,
                },
                "up4x-conservative": {
                    "label": "4x - conservative",
                    "exe_tool": "realcugan",
                    "cli_noise": -1,
                    "files": ["up4x-conservative.param", "up4x-conservative.bin"],
                    "size_mb": 3,
                    "vram_mb": 1800,
                    "scale": 4,
                },
            },
        },
    },

}

# ═══════════════════════════════════════════════════════════
# Remote Inference Defaults
# ═══════════════════════════════════════════════════════════
REMOTE_INFERENCE_DEFAULTS = {
    # max_srt_batch=50: caps cloud SRT batches just as the local path uses
    # max_srt_batch to bound chunk size. Without a cap, _calc_srt_batch_size on
    # a 128K-context provider would pack all segments into one request, causing
    # response-structure drift for large files and removing per-batch progress.
    # 50 segments ≈ ~3-5 min of content — a practical sweet-spot that fits well
    # within gpt-4o-mini / gemini-2.5-flash max_tokens=16384.
    "translate":    {"temperature": 0.1, "max_tokens": 16384, "max_srt_batch": 50},
    # 8192: safe LCM across providers — gemini-2.5-flash hard cap is 8192,
    # gpt-4o-mini accepts up to 16384, Ollama unbounded. 4096 was the
    # original spec value (worked for Ollama qwen3.5:9b narrative) but cuts
    # close for bullets-mode on 50min+ videos where 30+ bullets × ~150
    # tokens each plus citations approaches 4k. Provider-aware caps are a
    # follow-up.
    "summarize":    {"temperature": 0.3, "max_tokens": 8192},
    # 16384: gpt-4o-mini / gpt-4o completion cap (OpenAI rejects anything
    # larger with HTTP 400 "max_tokens is too large", and the API doesn't
    # expose the limit so we can't query it). Was 32768 → every remote OCR
    # on gpt-4o-* failed. 16384 matches `translate` (both are full-text
    # outputs) and is ample for a single image. gemini-2.5-flash (8192 cap)
    # is the same pre-existing limitation as translate — provider-aware
    # caps remain the follow-up.
    "ocr":          {"temperature": 0.0, "max_tokens": 16384},
    "frame_select": {"temperature": 0.0, "max_tokens": 16},
}
