"""
AI 模型註冊表 (Three-Layer Architecture V2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
採用「格式優先」樹狀結構：FORMAT -> FAMILY -> SPECS
這是系統的單一數據來源 (Single Source of Truth)
"""

# ═══════════════════════════════════════════════════════════
# 格式常數 (Format Constants)
# ═══════════════════════════════════════════════════════════
FORMAT_PKG = "PKG"     # 套件自管模型 (Whisper, Demucs)
FORMAT_GGUF = "GGUF"   # llama-cpp-python 單檔 (LLM)
FORMAT_PTH = "PTH"     # PyTorch 權重檔 (CV)
FORMAT_ONNX = "ONNX"   # ONNX Runtime (預留 DirectML 擴展)

# ═══════════════════════════════════════════════════════════
# 插槽常數 (Slot Constants)
# ═══════════════════════════════════════════════════════════
SLOT_WHISPER = "whisper"
SLOT_LLM = "llm"      # LLM 模型共用（一次只載入一個）
SLOT_PTH = "pth"      # PTH 模型共用（一次只載入一個）
SLOT_DEMUCS = "demucs"  # 音源分離（一次只載入一個）
SLOT_BASIC_PITCH = "basic_pitch"  # 音訊轉 MIDI（basic-pitch）
SLOT_RIFE = "rife"
SLOT_SEGMENT = "segment"  # 物件分割（MobileSAM）

# ═══════════════════════════════════════════════════════════
# 格式優先註冊表 (Format-First Registry)
# ═══════════════════════════════════════════════════════════

MODELS_REGISTRY = {
    # ───────────────────────────────────────────────────────
    # PKG 格式：套件自管模型（Whisper、Demucs）
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
        # ▸ Demucs（音源分離）
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
        # ▸ Basic Pitch（音訊轉 MIDI）
        "basic_pitch": {
            "slot": SLOT_BASIC_PITCH,
            "label": "Basic Pitch",
            "category": "midi",
            "description": "models.basic_pitch",
            "variants": {
                "default": {
                    "label": "default",
                    "model_name": "basic_pitch",
                    "size_mb": 10,
                    "vram_mb": 0,
                },
            },
        },
        # ▸ RIFE（影片補幀）
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
    # GGUF 格式：llama-server 模型（文字 + 視覺語言模型）
    # ───────────────────────────────────────────────────────
    FORMAT_GGUF: {
        "translategemma": {
            "slot": SLOT_LLM,
            "capabilities": ["text"],
            "description": "TranslateGemma 翻譯模型",
            "specs": {
                "4b": {
                    "layers": 26,
                    "n_ctx": 8192,
                    "vram_overhead_mb": 400,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "mradermacher/translategemma-4b-it-GGUF",
                            "filename": "translategemma-4b-it.Q4_K_M.gguf",
                            "size_mb": 2500,
                        },
                    },
                },
                "12b": {
                    "layers": 40,
                    "n_ctx": 8192,
                    "vram_overhead_mb": 800,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "mradermacher/translategemma-12b-it-GGUF",
                            "filename": "translategemma-12b-it.Q4_K_M.gguf",
                            "size_mb": 7300,
                        },
                        # --- 精簡：只保留 Q4_K_M，低量化品質差異大但 VRAM 省不多 ---
                        # "Q4_K_S": {
                        #     "repo_id": "mradermacher/translategemma-12b-it-GGUF",
                        #     "filename": "translategemma-12b-it.Q4_K_S.gguf",
                        #     "size_mb": 6940,
                        # },
                        # "Q3_K_L": {
                        #     "repo_id": "mradermacher/translategemma-12b-it-GGUF",
                        #     "filename": "translategemma-12b-it.Q3_K_L.gguf",
                        #     "size_mb": 6480,
                        # },
                        # "Q3_K_M": {
                        #     "repo_id": "mradermacher/translategemma-12b-it-GGUF",
                        #     "filename": "translategemma-12b-it.Q3_K_M.gguf",
                        #     "size_mb": 6010,
                        # },
                        # "Q3_K_S": {
                        #     "repo_id": "mradermacher/translategemma-12b-it-GGUF",
                        #     "filename": "translategemma-12b-it.Q3_K_S.gguf",
                        #     "size_mb": 5460,
                        # },
                    },
                },
                "27b": {
                    "layers": 64,
                    "n_ctx": 2048,
                    "vram_overhead_mb": 1200,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "bullerwins/translategemma-27b-it-GGUF",
                            "filename": "translategemma-27b-it-Q4_K_M.gguf",
                            "size_mb": 16500,
                        },
                    },
                },
            },
            "default_variant": {
                "4b": "Q4_K_M",
                "12b": "Q4_K_M",
                "27b": "Q4_K_M",
            },
        },
        
        "qwen3": {
            "slot": SLOT_LLM,
            "capabilities": ["text"],
            "description": "Qwen3 翻譯模型",
            "specs": {
                "1.7b": {
                    "layers": 28,
                    "n_ctx": 8192,
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
                    "n_ctx": 8192,
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
                    "n_ctx": 8192,
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
                    "n_ctx": 2048,
                    "vram_overhead_mb": 1000,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "Qwen/Qwen3-14B-GGUF",
                            "filename": "Qwen3-14B-Q4_K_M.gguf",
                            "size_mb": 9000,
                        },
                        # --- 精簡：只保留 Q4_K_M，低量化品質差異大但 VRAM 省不多 ---
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
            "capabilities": ["text", "vision"],
            "description": "Qwen3-VL 視覺語言模型（OCR）",
            "specs": {
                "2b": {
                    "layers": 28,
                    "n_ctx": 8192,
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
                        # --- 精簡：小模型 Q8_0 體積大但品質提升有限 ---
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
                    "n_ctx": 8192,
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
                        # --- 精簡：小模型 Q8_0 體積大但品質提升有限 ---
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
                    "n_ctx": 8192,
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
            "capabilities": ["text", "vision"],
            "description": "InternVL2.5 視覺語言模型（OCR）",
            "specs": {
                "1b": {
                    "layers": 24,
                    "n_ctx": 8192,
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
                    "n_ctx": 8192,
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
                        # --- 精簡：小模型 Q8_0 體積大但品質提升有限 ---
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
            "capabilities": ["text", "vision"],
            "description": "Gemma 3 視覺語言模型（OCR）",
            "specs": {
                "4b": {
                    "layers": 34,
                    "n_ctx": 8192,
                    "vram_overhead_mb": 600,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "ggml-org/gemma-3-4b-it-GGUF",
                            "filename": "gemma-3-4b-it-Q4_K_M.gguf",
                            "mmproj_repo_id": "ggml-org/gemma-3-4b-it-GGUF",
                            "mmproj_filename": "mmproj-model-f16.gguf",
                            "size_mb": 2490,
                            "mmproj_size_mb": 851,
                        },
                    },
                },
                "12b": {
                    "layers": 46,
                    "n_ctx": 8192,
                    "vram_overhead_mb": 800,
                    "variants": {
                        "Q4_K_M": {
                            "repo_id": "ggml-org/gemma-3-12b-it-GGUF",
                            "filename": "gemma-3-12b-it-Q4_K_M.gguf",
                            "mmproj_repo_id": "ggml-org/gemma-3-12b-it-GGUF",
                            "mmproj_filename": "mmproj-model-f16.gguf",
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

        # ▸ Qwen3.5
        "qwen3.5": {
            "slot": SLOT_LLM,
            "capabilities": ["text", "vision"],
            "description": "Qwen3.5 多模態模型",
            "specs": {
                "4b": {
                    "layers": 36,
                    "n_ctx": 8192,
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
                    "n_ctx": 8192,
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
                    "n_ctx": 8192,
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
    # PTH 格式：PyTorch 影像處理模型
    # ───────────────────────────────────────────────────────
    FORMAT_PTH: {
        # ▸ Real-ESRGAN 系列
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
        
        # ▸ SwinIR 系列
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
                    "label": "default",
                    "url": "https://github.com/cszn/KAIR/releases/download/v1.0/BSRGAN.pth",
                    "filename": "BSRGAN.pth",
                    "size_mb": 64,
                    "vram_mb": 2200,
                    "scale": 4,
                },
            },
        },
        
        # ▸ Real-CUGAN 系列
        # 注意：所有變體來自同一個壓縮檔，下載後自動解壓
        # 壓縮檔結構：updated_weights/up{2,3,4}x-latest-{variant}.pth
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
                # --- 精簡：conservative 已涵蓋輕降噪，no-denoise 場景極少 ---
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
                # --- 精簡：conservative 已涵蓋輕降噪 ---
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
                # --- 精簡：conservative 已涵蓋輕降噪 ---
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
        
        # ▸ CodeFormer
        "codeformer": {
            "slot": "codeformer",
            "label": "CodeFormer",
            "category": "face_restore",
            "description": "models.codeformer",
            "variants": {
                "default": {
                    "label": "default",
                    "url": "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth",
                    "filename": "codeformer.pth",
                    "size_mb": 357,
                    "vram_mb": 2500,
                },
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

        # ▸ MobileSAM（AI 物件移除用）
        "mobilesam": {
            "slot": "mobilesam",
            "label": "MobileSAM",
            "category": "segment",
            "description": "models.mobilesam",
            "variants": {
                "default": {
                    "label": "default",
                    "url": "https://huggingface.co/dhkim2810/MobileSAM/resolve/main/mobile_sam.pt",
                    "filename": "mobile_sam.pt",
                    "size_mb": 39,
                    "vram_mb": 500,
                },
            },
        },

        # ▸ Waifu2x 系列
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
                    "size_mb": 17,
                    "vram_mb": 1200,
                    "scale": 2,
                },
                "cunet-art-4x": {
                    "label": "4x - cunet",
                    "url": "https://github.com/nagadomi/nunif/releases/download/0.0.0/waifu2x_pretrained_models_20250502.zip",
                    "filename": "waifu2x_cunet_art_4x.pth",
                    "unzip": True,
                    "archive_path": "pretrained_models/cunet/art/scale4x.pth",
                    "size_mb": 17,
                    "vram_mb": 1200,
                    "scale": 4,
                },
                "swin-unet-art-2x": {
                    "label": "2x - swin-unet",
                    "url": "https://github.com/nagadomi/nunif/releases/download/0.0.0/waifu2x_pretrained_models_20250502.zip",
                    "filename": "waifu2x_swin_unet_art_2x.pth",
                    "unzip": True,
                    "archive_path": "pretrained_models/swin_unet/art/scale2x.pth",
                    "size_mb": 52,
                    "vram_mb": 1500,
                    "scale": 2,
                },
                "swin-unet-art-4x": {
                    "label": "4x - swin-unet",
                    "url": "https://github.com/nagadomi/nunif/releases/download/0.0.0/waifu2x_pretrained_models_20250502.zip",
                    "filename": "waifu2x_swin_unet_art_4x.pth",
                    "unzip": True,
                    "archive_path": "pretrained_models/swin_unet/art/scale4x.pth",
                    "size_mb": 52,
                    "vram_mb": 1500,
                    "scale": 4,
                },
            },
        },
    },

}

# 模型註冊表結束
