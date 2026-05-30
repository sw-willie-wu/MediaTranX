"""Container exposes yt_dlp_wrapper + video_download providers."""
from app.init.container import AppContainer


def test_providers_exist_and_build():
    c = AppContainer()
    wrapper = c.yt_dlp_wrapper()
    from app.adapters.binary.ytdlp import YtDlpWrapper
    assert isinstance(wrapper, YtDlpWrapper)

    svc = c.video_download()
    from app.services.video.download_service import VideoDownloadService
    assert isinstance(svc, VideoDownloadService)
    # Wired with the shared infra singletons.
    assert svc._ffmpeg is c.ffmpeg()
    assert svc._file_service is c.file_service()
    assert svc._task_manager is c.task_manager()
    assert svc._ytdlp is wrapper
