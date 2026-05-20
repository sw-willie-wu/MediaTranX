"""
Inference parameter helper.

Provides unified access to per-model, per-task inference config.
All services should use this instead of hardcoding temperature/max_tokens.
"""
import contextvars
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Shared single-poller coordination: set True (on the entering/call thread)
# by whichever in-call watcher owns poll+kill for the current blocking call
# (fake_progress when it has a cancellable, or cancel_guard). A nested guard
# that sees this True is a pure pass-through → exactly one watcher per call.
_in_call_cancel_owner: contextvars.ContextVar = contextvars.ContextVar(
    "in_call_cancel_owner", default=False
)
_CANCEL_GUARD_TICK = 1.0  # seconds; ≥1.0 (no synchronous work on the call thread)


def calc_max_tokens(config: dict, n_ctx: int, input_len: int) -> int:
    """
    Calculate max_tokens based on strategy.

    Args:
        config: inference config dict (must have max_tokens_strategy, max_tokens_ratio)
        n_ctx: context window size
        input_len: estimated input token count
    """
    strategy = config.get("max_tokens_strategy", "input_ratio")

    if strategy == "input_ratio":
        raw = int(input_len * config.get("max_tokens_ratio", 4))
        capped = min(raw, config.get("max_tokens_cap", n_ctx))
    elif strategy == "context_ratio":
        capped = int(n_ctx * config.get("max_tokens_ratio", 0.5))
    elif strategy == "fixed":
        capped = config.get("max_tokens_cap", 4096)
    else:
        capped = config.get("max_tokens_cap", 4096)

    # Safety: ensure input + output fits in context
    available = max(256, n_ctx - input_len)
    return min(capped, available)


def calc_batch_size(n_ctx: int, max_tokens: int, prompt_overhead: int,
                    avg_segment_tokens: int) -> int:
    """
    Calculate optimal batch size from available input space.

    Args:
        n_ctx: context window size
        max_tokens: reserved output tokens
        prompt_overhead: estimated tokens for prompt template
        avg_segment_tokens: average tokens per input segment
    """
    available_input = n_ctx - max_tokens - prompt_overhead
    if available_input <= 0:
        return 1
    return max(1, available_input // avg_segment_tokens)


def calc_n_ctx(spec: dict, available_vram_mb: float,
               user_override: Optional[int] = None) -> int:
    """
    Calculate optimal n_ctx from VRAM budget.

    Args:
        spec: model spec from registry (must have n_ctx_min, n_ctx_max, vram_per_ctx_token)
        available_vram_mb: available VRAM in MB after model loading
        user_override: user-set value from preferences (None = auto)
    """
    n_ctx_min = spec.get("n_ctx_min", 2048)
    n_ctx_max = spec.get("n_ctx_max", 8192)
    vram_per_token = spec.get("vram_per_ctx_token", 0.04)

    # Safe max based on VRAM
    safe_max = int(available_vram_mb / vram_per_token) if vram_per_token > 0 else n_ctx_max
    safe_max = min(safe_max, n_ctx_max)

    if user_override is not None:
        # Respect user setting but clamp to safe range
        return max(n_ctx_min, min(user_override, safe_max))

    # Auto: use default, clamped to what VRAM can afford
    default = spec.get("n_ctx_default", 4096)
    return max(n_ctx_min, min(default, safe_max))


def estimate_tokens(text: str) -> int:
    """Rough token estimate based on character types.

    CJK characters: ~1.5 tokens each (most tokenizers split CJK into 1-2 tokens)
    ASCII/Latin: ~4 chars per token (subword tokenization)
    """
    cjk = 0
    ascii_chars = 0
    for ch in text:
        cp = ord(ch)
        if (0x3000 <= cp <= 0x9FFF) or (0xF900 <= cp <= 0xFAFF) or (0xAC00 <= cp <= 0xD7AF):
            cjk += 1
        else:
            ascii_chars += 1
    return max(1, int(cjk * 1.5) + ascii_chars // 4)


def fake_progress(on_progress, start_pct: float, end_pct: float, message: str,
                  duration: float = 30.0, cancellable=None):
    """
    Context manager that emits interpolated progress while waiting for a blocking call.

    Usage:
        with fake_progress(callback, 0.1, 0.5, "task.progress.translating"):
            result = runtime.chat(...)  # blocking LLM call

    Progress interpolates from start_pct to (end_pct - 1%) over `duration` seconds,
    then stops. Real progress is reported by the caller after the `with` block.

    Args:
        cancellable: optional object with .kill_process() — invoked when the
            on_progress callback raises (e.g. TaskCancelledError) to unblock
            the in-flight llama-server HTTP call.
    """
    import threading
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        if not on_progress:
            yield
            return

        stop = threading.Event()
        cancelled_error = [None]  # mutable container for cross-thread error
        target = end_pct - 0.01
        steps = max(1, int(duration))

        def _run():
            current = start_pct
            step_size = (target - current) / steps
            while not stop.is_set() and current < target:
                current = min(current + step_size, target)
                try:
                    on_progress(current, message)
                except Exception as e:
                    # TaskCancelledError from cancellable callback
                    cancelled_error[0] = e
                    # Kill llama-server to unblock the HTTP call in main thread
                    if cancellable is not None:
                        try:
                            cancellable.kill_process()
                        except Exception:
                            pass
                    stop.set()
                    return
                stop.wait(1.0)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        # When this fake_progress owns a cancellable it is the single
        # poll+kill owner for the wrapped blocking call — mark it so a nested
        # cancel_guard (e.g. ChatSession self-guard) passes through.
        _own_token = (
            _in_call_cancel_owner.set(True) if cancellable is not None else None
        )
        try:
            yield
        finally:
            stop.set()
            if _own_token is not None:
                _in_call_cancel_owner.reset(_own_token)
            # Re-raise cancel error caught in background thread
            if cancelled_error[0] is not None:
                raise cancelled_error[0]

    return _ctx()


def cancel_guard(on_progress, *, cancellable, progress: float, message: str):
    """Pure cancel-watch (constant heartbeat, no progress animation) for
    blocking calls that have NO enclosing fake_progress owner — e.g. the
    one-shot summary chunk / VLM frame-select path.

    A daemon watcher ticks every _CANCEL_GUARD_TICK calling
    on_progress(progress, message) — a constant heartbeat at the caller's
    stable phase pct (never 0.0). If on_progress raises (TaskCancelledError),
    cancellable.kill_process() is invoked best-effort and the error re-raised.

    Pass-through (no watcher, never raises by itself) when on_progress is
    None, cancellable is None, OR an enclosing owner already set the shared
    ContextVar (fake_progress-with-cancellable, or an outer cancel_guard) —
    guaranteeing exactly one poll+kill watcher per in-flight call. The
    ContextVar is set/reset on the entering (call) thread only; the watcher
    thread never touches it (threading.Thread starts with a fresh context —
    do NOT copy_context for the watcher).
    """
    import threading
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        if (on_progress is None or cancellable is None
                or _in_call_cancel_owner.get()):
            yield
            return
        token = _in_call_cancel_owner.set(True)
        stop = threading.Event()
        cancelled_error = [None]

        def _run():
            while not stop.is_set():
                try:
                    on_progress(progress, message)
                except Exception as e:
                    cancelled_error[0] = e
                    try:
                        cancellable.kill_process()
                    except Exception:
                        pass
                    stop.set()
                    return
                stop.wait(_CANCEL_GUARD_TICK)

        t = threading.Thread(target=_run, daemon=True, name="cancel-guard")
        t.start()
        try:
            yield
        finally:
            stop.set()
            _in_call_cancel_owner.reset(token)
            if cancelled_error[0] is not None:
                raise cancelled_error[0]

    return _ctx()
