# Local LLM/VLM Cancel-Coverage Audit (2026-05-19)

Every llama-server-backed blocking call site, its poll+kill owner after T1–T5,
and verification there is **exactly one** owner (no uncovered, no double-poller).

| Site (file:line) | Blocking call | Poll+kill owner | Status |
|---|---|---|---|
| `pipeline/translate.py:232` | `session.chat/.complete` (236/242) | `fake_progress(cancellable=session)` — sets ContextVar; inner ChatSession `cancel_guard` passes through | ✅ already correct, **unchanged** |
| `pipeline/ocr.py:57` | `session.chat` (58) | `fake_progress(cancellable=session)`; inner passthrough | ✅ unchanged |
| `document/translate_service/text.py:126` | `session.chat/.complete` (130/136) | `fake_progress(cancellable=session)`; inner passthrough | ✅ unchanged |
| `transcribe_service/summarize.py:50,58,63` | `chat_fn` → `_local_chat` → `session.chat` (`transcribe_service/service.py:298`) | `fake_progress` **WITHOUT** `cancellable=` → **was uncovered** → **T5: add `cancellable=session`** | ✅ fixed T5 (shape b′) |
| `summary_service/service.py:272` | one-shot `self._chat_service.chat(` (chunk text) | no `fake_progress` on path → **T5: thread `on_progress`/`cancel_pct`/`cancel_msg`** → ChatSession `cancel_guard` sole owner | ✅ fixed T5 (shape a) |
| `summary_service/service.py:486` | one-shot `self._chat_service.chat_with_images(` (`_cb` via `_make_vlm_callback`) | no `fake_progress` → **T5: per-loop `_make_vlm_callback` threads params** → ChatSession `cancel_guard` sole owner | ✅ fixed T5 (shape a) |
| `chat_service.py:198,222` | internal one-shot→`session.chat/.chat_with_images` delegation | covered by F2 (the yielded `ChatSession` carries `on_progress`); not a separate site | ✅ structural |

## Transitive coverage (no direct `session.*` / `fake_progress` of their own)

`lyrics_service`, `image/ocr_service`, `document/doc_ocr_service`,
`video/subtitle_service`, `document/translate_service` (SRT branch) — all reach
llama-server **only** through the pipeline helpers `translate_srt_auto` →
`pipeline/translate.py:232` and `ocr_*` → `pipeline/ocr.py:57`, both of which
already own poll+kill via `fake_progress(cancellable=session)`. Confirmed by
grep: zero direct `session.{chat,complete,chat_with_images}(` outside
`transcribe_service:298`, `text.py:130/136`, `ocr.py:58`,
`translate.py:236/242`, `chat_service.py:198/222`. → **covered, no edit.**

## Gate result

- Uncovered sites: **0** (the only `fake_progress`-without-`cancellable`
  wrapping an LLM call was `summarize.py`; fixed in T5).
- Double-poller sites: **0** (every enclosing `fake_progress(cancellable=)`
  sets the shared ContextVar; the inner ChatSession `cancel_guard` passes
  through — verified by `test_single_poller_when_enclosing_fake_progress`).
- T5 scope = exactly `summarize.py:50/58/63` + `summary_service:272/486`. No
  extra site surfaced.
