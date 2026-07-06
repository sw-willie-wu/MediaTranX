"""Animation (GIF/APNG) transcode arg construction — adapters/binary/ffmpeg.py.

FFmpegWrapper() 建構子會 _find_ffmpeg/_find_ffprobe、找不到就 raise ——
依 test_ffmpeg_wrapper.py:115-123 的既有慣例 patch 兩者，讓單測完全
environment-independent（無 ffmpeg 的 runner 也能跑）。patch 目標的實際
名稱/形式照抄該處示範。
"""
from pathlib import Path
from unittest.mock import patch

from app.adapters.binary.ffmpeg import FFmpegWrapper, TranscodeOptions

IN = Path("in.mp4")


def _wrapper() -> FFmpegWrapper:
    with patch.object(FFmpegWrapper, "_find_ffmpeg", return_value="ffmpeg"), \
         patch.object(FFmpegWrapper, "_find_ffprobe", return_value="ffprobe"):
        return FFmpegWrapper()


def _args(fmt: str, **kw) -> list[str]:
    opts = TranscodeOptions(output_format=fmt, **kw)
    return _wrapper()._build_transcode_args(IN, Path(f"out.{fmt}"), opts)


def test_gif_palette_filtergraph_with_defaults():
    args = _args("gif")
    fc = args[args.index("-filter_complex") + 1]
    assert fc == "[0:v] fps=12,split [a][b];[a] palettegen [p];[b][p] paletteuse"
    assert args[args.index("-f") + 1] == "gif"
    assert args[args.index("-loop") + 1] == "0"
    assert "-an" in args
    assert "-progress" in args  # progress reporting preserved


def test_gif_with_resolution_inserts_scale_before_split():
    args = _args("gif", fps=15, resolution="640x360", scale_algorithm="lanczos")
    fc = args[args.index("-filter_complex") + 1]
    assert fc.startswith("[0:v] fps=15,scale=640:360:flags=lanczos,split ")


def test_gif_scale_algorithm_falls_back_to_bicubic():
    args = _args("gif", resolution="320x240")
    fc = args[args.index("-filter_complex") + 1]
    assert "scale=320:240:flags=bicubic" in fc


def test_apng_uses_vf_and_infinite_plays():
    args = _args("apng", fps=10)
    assert args[args.index("-vf") + 1] == "fps=10"
    assert args[args.index("-f") + 1] == "apng"
    assert args[args.index("-plays") + 1] == "0"
    assert "-an" in args


def test_apng_with_resolution():
    args = _args("apng", fps=10, resolution="160x120")
    assert args[args.index("-vf") + 1] == "fps=10,scale=160:120:flags=bicubic"


def test_animation_drops_codec_crf_preset_and_r():
    for fmt in ("gif", "apng"):
        args = _args(fmt, fps=12)
        for flag in ("-c:v", "-crf", "-preset", "-c:a", "-r"):
            assert flag not in args, f"{flag} leaked into {fmt} args"


def test_fps_none_falls_back_to_12():
    args = _args("gif", fps=None)
    fc = args[args.index("-filter_complex") + 1]
    assert fc.startswith("[0:v] fps=12,")


def test_normal_video_format_unchanged():
    args = _args("mp4")
    assert "-c:v" in args and "-crf" in args
    assert "-filter_complex" not in args and "palettegen" not in " ".join(args)
