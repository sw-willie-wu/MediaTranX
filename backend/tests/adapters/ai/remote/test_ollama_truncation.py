import logging
from app.adapters.ai.remote.ollama import OllamaProvider


def _big_messages(est_tokens: int):
    # chars//3 estimate: need ~est_tokens*3 chars
    return [{"role": "user", "content": "x" * (est_tokens * 3)}]


def test_warns_once_when_prompt_eval_far_below_estimate(caplog):
    ol = OllamaProvider("http://h")
    msgs = _big_messages(20000)  # est ~20000 tokens
    with caplog.at_level(logging.WARNING):
        ol._maybe_warn_truncation(msgs, 4096)   # 4096 << 20000*0.5
        ol._maybe_warn_truncation(msgs, 4096)   # second call must NOT warn again
    hits = [r for r in caplog.records if "truncat" in r.getMessage().lower()]
    assert len(hits) == 1
    assert ol._truncation_warned is True


def test_no_warning_on_normal_request(caplog):
    ol = OllamaProvider("http://h")
    msgs = _big_messages(10000)  # est ~10000
    with caplog.at_level(logging.WARNING):
        # normal: prompt_eval ~0.75*est = 7500, which is NOT < est*0.5 (5000)
        ol._maybe_warn_truncation(msgs, 7500)
    hits = [r for r in caplog.records if "truncat" in r.getMessage().lower()]
    assert hits == []
    assert ol._truncation_warned is False


def test_no_warning_when_prompt_eval_missing(caplog):
    ol = OllamaProvider("http://h")
    msgs = _big_messages(20000)
    with caplog.at_level(logging.WARNING):
        ol._maybe_warn_truncation(msgs, None)   # missing field -> skip
    assert ol._truncation_warned is False


def test_no_warning_below_est_floor(caplog):
    ol = OllamaProvider("http://h")
    msgs = _big_messages(2000)  # est 2000 < 4000 floor -> never warn
    with caplog.at_level(logging.WARNING):
        ol._maybe_warn_truncation(msgs, 10)
    assert ol._truncation_warned is False
