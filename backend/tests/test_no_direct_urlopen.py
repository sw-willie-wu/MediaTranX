"""Guard: the 3 remote providers must route HTTP through _http.urlopen (the
cross-scheme redirect guard), never urllib.request.urlopen directly."""
import pathlib

REMOTE = pathlib.Path(__file__).resolve().parents[1] / "app" / "adapters" / "ai" / "remote"

def test_providers_use_http_helper_not_raw_urlopen():
    offenders = []
    for name in ["ollama.py", "openai.py", "gemini.py"]:
        src = (REMOTE / name).read_text(encoding="utf-8")
        if "urllib.request.urlopen(" in src:
            offenders.append(name)
    assert not offenders, f"Direct urllib.request.urlopen in: {offenders} (use _http.urlopen)"
