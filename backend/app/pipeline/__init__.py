"""Domain inference orchestration layer.

Modules here coordinate engine-level primitives (whisper/demucs/wav2vec2/llama/
remote providers) into cross-service inference flows. Unlike `utils/`, these
modules know domain concepts like "transcribe" / "translate" / "OCR".

Qualifying for pipeline/ requires:
- shared across ≥2 services (跨 service orchestration)
- coordinates multiple engines or a multi-stage LLM inference
- domain-aware (knows what the inference *means*)

Per-service orchestrations belong in `services/<domain>/<feature>/` instead.
Pure format/chunking helpers belong in `utils/`.
"""
