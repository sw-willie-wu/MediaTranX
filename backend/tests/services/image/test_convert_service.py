"""Tests for ImageConvertService."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from tests.conftest import make_file_service_mock
from app.services.image.convert_service import (
    ImageConvertService,
    TASK_TYPE_IMAGE_CONVERT,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        ImageConvertService(file_service=fs, task_manager=tm)
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_IMAGE_CONVERT
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_params(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = ImageConvertService(file_service=fs, task_manager=tm)
        tid = await svc.submit_convert(
            file_id="fid", output_format="webp", quality=90,
            width=200, height=None, scale=None,
        )
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_IMAGE_CONVERT
        assert args[1]["output_format"] == "webp"
        assert args[1]["quality"] == 90
        assert args[1]["width"] == 200


class TestExecute:
    def _build(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = ImageConvertService(file_service=fs, task_manager=MagicMock())
        return svc, fs

    def _save_rgba(self, fs):
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGBA", (64, 64), (255, 0, 0, 128)).save(img_path)
        return img_path

    def _save_static_rgb(self, fs):
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGB", (64, 64), (0, 0, 255)).save(img_path)
        return img_path

    def test_static_png_to_jpeg_converts_rgba_to_rgb(self, tmp_path):
        svc, fs = self._build(tmp_path)
        self._save_rgba(fs)
        result = svc._execute(
            {"file_id": "f", "output_format": "jpeg", "quality": 90,
             "width": None, "height": None, "scale": None},
            lambda p, m: None,
        )
        assert "output_file_id" in result
        # Output file should exist on disk
        out_path = fs.output_dir / "input_converted.jpg"
        assert out_path.exists()

    def test_resize_with_scale(self, tmp_path):
        svc, fs = self._build(tmp_path)
        self._save_static_rgb(fs)
        result = svc._execute(
            {"file_id": "f", "output_format": "png", "quality": 90,
             "width": None, "height": None, "scale": 0.5},
            lambda p, m: None,
        )
        out_path = fs.output_dir / "input_converted.png"
        assert out_path.exists()
        with Image.open(out_path) as out:
            assert out.size == (32, 32)

    def test_resize_width_only_preserves_aspect(self, tmp_path):
        svc, fs = self._build(tmp_path)
        self._save_static_rgb(fs)  # 64x64
        svc._execute(
            {"file_id": "f", "output_format": "png", "quality": 90,
             "width": 32, "height": None, "scale": None},
            lambda p, m: None,
        )
        out_path = fs.output_dir / "input_converted.png"
        with Image.open(out_path) as out:
            assert out.size == (32, 32)

    def test_animated_gif_uses_apply_and_save(self, tmp_path):
        svc, fs = self._build(tmp_path)
        img_path = Path(fs.require_file("f").file_path)
        # Two-frame animated GIF
        Image.new("RGB", (32, 32), (255, 0, 0)).save(
            img_path, format="GIF", save_all=True,
            append_images=[Image.new("RGB", (32, 32), (0, 255, 0))],
            duration=100, loop=0,
        )
        with patch("app.utils.gif_utils.apply_and_save") as mock_apply:
            mock_apply.return_value = None
            svc._execute(
                {"file_id": "f", "output_format": "gif", "quality": 90,
                 "width": None, "height": None, "scale": None},
                lambda p, m: None,
            )
            mock_apply.assert_called_once()

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, fs = self._build(tmp_path)
        self._save_static_rgb(fs)
        progress = []
        svc._execute(
            {"file_id": "f", "output_format": "png", "quality": 90,
             "width": None, "height": None, "scale": None},
            lambda p, m: progress.append((p, m)),
        )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0


class TestQueryMethods:
    async def test_get_image_info_returns_dict(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGB", (100, 50), (0, 0, 0)).save(img_path)
        svc = ImageConvertService(file_service=fs, task_manager=MagicMock())
        info = await svc.get_image_info("f")
        assert info["width"] == 100
        assert info["height"] == 50
        assert info["format"] in {"PNG", "APNG"}
        assert info["mode"] == "RGB"


# ─── Coalesce tests ───

FIX = Path(__file__).parent.parent.parent / "fixtures" / "compress"


class TestCoalesce:
    """GIF coalesce post-processing via injected GifsicleWrapper."""

    def _make_anim_gif(self, path: Path) -> None:
        """Write a small two-frame animated GIF at *path*."""
        frames = [Image.new("P", (16, 16)), Image.new("P", (16, 16))]
        for i, color in enumerate([(255, 0, 0), (0, 255, 0)]):
            frames[i].putpalette([*color, *([0] * (256 * 3 - 3))])
        frames[0].save(
            path, save_all=True, append_images=[frames[1]],
            loop=0, format="GIF", duration=100,
        )

    def test_gif_coalesce_calls_gifsicle(self, tmp_path):
        """GIF→GIF with coalesce=True must invoke gifsicle.compress(coalesce=True)."""
        from unittest.mock import MagicMock

        fs = make_file_service_mock(tmp_path)
        img_path = Path(fs.require_file("f").file_path)
        # rename the mock file to .gif so PIL opens it as a GIF
        gif_path = tmp_path / "input.gif"
        self._make_anim_gif(gif_path)

        # Patch require_file to point at the gif
        def _require_file(file_id):
            fd = MagicMock()
            fd.file_id = file_id
            fd.original_filename = "input.gif"
            fd.file_path = str(gif_path)
            fd.file_size = gif_path.stat().st_size
            return fd
        fs.require_file.side_effect = _require_file

        # Patch create_output_path to produce a real gif path
        out_path = tmp_path / "out" / "input_converted.gif"
        out_path.parent.mkdir(exist_ok=True)
        fs.create_output_path.side_effect = lambda *, original_filename, suffix, ext: (
            "out_id", out_path
        )

        spy_gifsicle = MagicMock()
        # apply_and_save already wrote the GIF; the spy just needs to be a no-op
        # so register_output can stat the file that's already on disk.
        spy_gifsicle.compress.side_effect = lambda src, dst, **kwargs: None

        svc = ImageConvertService(
            file_service=fs, task_manager=MagicMock(), gifsicle=spy_gifsicle
        )
        svc._execute(
            {"file_id": "f", "output_format": "gif", "quality": 85,
             "width": None, "height": None, "scale": None, "coalesce": True},
            lambda p, m: None,
        )

        spy_gifsicle.compress.assert_called_once()
        call_kwargs = spy_gifsicle.compress.call_args.kwargs
        assert call_kwargs.get("coalesce") is True

    def test_non_gif_output_coalesce_does_not_call_gifsicle(self, tmp_path):
        """coalesce=True with PNG output must NOT invoke gifsicle."""
        from unittest.mock import MagicMock

        fs = make_file_service_mock(tmp_path)
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGB", (32, 32), (0, 0, 255)).save(img_path)

        spy_gifsicle = MagicMock()
        svc = ImageConvertService(
            file_service=fs, task_manager=MagicMock(), gifsicle=spy_gifsicle
        )
        svc._execute(
            {"file_id": "f", "output_format": "png", "quality": 85,
             "width": None, "height": None, "scale": None, "coalesce": True},
            lambda p, m: None,
        )

        spy_gifsicle.compress.assert_not_called()

    def test_gif_coalesce_real_gifsicle(self, tmp_path):
        """Integration: GIF→GIF coalesce=True with real GifsicleWrapper yields valid animated GIF."""
        from app.adapters.binary.gifsicle import GifsicleWrapper

        fs = make_file_service_mock(tmp_path)
        gif_src = FIX / "anim.gif"

        def _require_file(file_id):
            fd = MagicMock()
            fd.file_id = file_id
            fd.original_filename = "anim.gif"
            fd.file_path = str(gif_src)
            fd.file_size = gif_src.stat().st_size
            return fd
        fs.require_file.side_effect = _require_file

        out_path = tmp_path / "out" / "anim_converted.gif"
        out_path.parent.mkdir(exist_ok=True)
        fs.create_output_path.side_effect = lambda *, original_filename, suffix, ext: (
            "out_id", out_path
        )

        svc = ImageConvertService(
            file_service=fs, task_manager=MagicMock(), gifsicle=GifsicleWrapper()
        )
        result = svc._execute(
            {"file_id": "f", "output_format": "gif", "quality": 85,
             "width": None, "height": None, "scale": None, "coalesce": True},
            lambda p, m: None,
        )

        assert out_path.exists()
        with Image.open(out_path) as out:
            assert getattr(out, "n_frames", 1) >= 1, "output must be a valid animated GIF"
        assert result["output_file_id"] == "out_id"
