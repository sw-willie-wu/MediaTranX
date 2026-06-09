"""E2E: exercise the SHIPPED OllamaProvider + chunk math against the real
dev-ollama bridge, verifying AC-2 (get_model_ctx reads real model_info max),
the budget short-circuit, and AC-7 (batch/chunk size changes with budget)."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.adapters.ai.remote.ollama import OllamaProvider, _CTX_CACHE
from app.pipeline.translate import _calc_srt_batch_size, get_cloud_ctx

ENDPOINT = "https://dev-ollama.thinktron.co"
MODEL = "gemma3:27b"   # native ollama model, real max = 131072

# A realistic SRT sample (20 segments) so batch math has content to estimate.
SEGS = [{"text": "This is a sample subtitle line number %d that is moderately long." % i}
        for i in range(600)]

print("=== AC-2: get_model_ctx reads model_info.context_length (auto) ===")
_CTX_CACHE.clear()
auto = OllamaProvider(ENDPOINT, None)                      # no budget
ctx_auto = get_cloud_ctx(auto, MODEL)
print(f"  auto get_cloud_ctx({MODEL}) = {ctx_auto}   (expect 131072)")

print("=== budget short-circuit: get_model_ctx returns the budget, no HTTP ===")
bud = OllamaProvider(ENDPOINT, None, chunk_ctx_budget=8192)
ctx_bud = get_cloud_ctx(bud, MODEL)
print(f"  budget=8192 get_cloud_ctx = {ctx_bud}   (expect 8192)")

print("=== AC-7: batch size changes with the resolved ctx ===")
bs_auto = _calc_srt_batch_size(ctx_auto, SEGS)
bs_bud = _calc_srt_batch_size(ctx_bud, SEGS)
print(f"  batch_size @ auto({ctx_auto}) = {bs_auto}")
print(f"  batch_size @ budget({ctx_bud}) = {bs_bud}")
print(f"  -> differ? {bs_auto != bs_bud}   (smaller budget should give <= batch)")

print("=== summary chunking hints reflect the same ctx ===")
print(f"  auto hints   = {auto.get_summary_chunking_hints(MODEL)}")
print(f"  budget hints = {bud.get_summary_chunking_hints(MODEL)}")

print("=== vllm model (empty model_info) auto -> raise -> boundary 8192 ===")
_CTX_CACHE.clear()
vllm = OllamaProvider(ENDPOINT, None)
print(f"  get_cloud_ctx(gpt-oss-120b-vllm-openai) = {get_cloud_ctx(vllm, 'gpt-oss-120b-vllm-openai')}   (expect 8192 fallback)")
