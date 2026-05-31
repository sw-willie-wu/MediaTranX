"""PathSettings.ytdlp returns a directory (mirrors the ffmpeg field)."""
import sys
from pathlib import Path

from app.init.configs.paths import PathSettings


def test_ytdlp_is_a_directory_under_bin_on_windows():
    ps = PathSettings(root=Path("/data"))
    if sys.platform == "win32":
        assert ps.ytdlp == Path("/data") / "bin" / "yt-dlp"
    else:
        assert ps.ytdlp == Path("yt-dlp")


def test_ytdlp_mirrors_ffmpeg_shape():
    ps = PathSettings(root=Path("/data"))
    # Both resolve to a *directory* (wrapper finds the exe inside), never an exe.
    assert ps.ytdlp.suffix == ""
