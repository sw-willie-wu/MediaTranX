# llama-server Binary

Place llama-server executables and DLLs here.

## Download

Pre-built Windows binaries are available from the llama.cpp releases page:
https://github.com/ggerganov/llama.cpp/releases

Download the Windows release archive (e.g. `llama-bxxxx-bin-win-cuda-cu12.x.x-x64.zip` for CUDA,
or `llama-bxxxx-bin-win-noavx-x64.zip` for CPU-only) and extract:
- `llama-server.exe`
- All accompanying `.dll` files (ggml, llama, CUDA, etc.)

into this directory.

## Variants

| Variant | File | Notes |
|---------|------|-------|
| CUDA 12 | `llama-bXXXX-bin-win-cuda-cu12.x.x-x64.zip` | Requires NVIDIA GPU + CUDA 12 |
| CPU only | `llama-bXXXX-bin-win-noavx-x64.zip` | Works on any x64 CPU |

The application auto-selects CUDA or CPU based on the detected hardware at runtime.
