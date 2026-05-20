import asyncio

import pytest

from app.services.files.file_service import FileService
from app.workers.progress_tracker import ProgressTracker
from app.workers.task_manager import TaskManager


@pytest.fixture
def fs(tmp_path):
    return FileService(base_dir=str(tmp_path))


@pytest.fixture
def tm(fs):
    return TaskManager(progress_tracker=ProgressTracker(), file_service=fs)


@pytest.mark.asyncio
async def test_results_policy_tags_metadata(tm, fs):
    # Arrange an output file
    out_path = fs.output_dir / "result_test.srt"
    out_path.write_text("x")
    fs.register_output(file_id="out-1", file_path=out_path, original_filename="input.mp4")
    # Pretend an input file exists
    in_path = fs.upload_dir / "input.mp4"
    in_path.write_text("in")
    fs.register_output(file_id="in-1", file_path=in_path, original_filename="input.mp4")

    def handler(params, cb):
        return {"output_file_id": "out-1", "output_filename": "result.srt"}

    tm.register_handler("audio.transcribe", handler, output_policy="results")
    task_id = await tm.submit("audio.transcribe", {"file_id": "in-1"})

    # Wait for completion
    for _ in range(50):
        t = tm.get_task(task_id)
        if t.status.value in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    assert tm.get_task(task_id).status.value == "completed"
    fd = fs.get_file("out-1")
    assert fd.metadata["tool_id"] == "audio.transcribe"
    assert fd.metadata["source_file_id"] == "in-1"
    assert fd.metadata["show_in_results"] is True
    assert fs._sidecar_path("out-1").exists()


@pytest.mark.asyncio
async def test_history_policy_does_not_write_sidecar(tm, fs):
    out_path = fs.output_dir / "img_test.jpg"
    out_path.write_text("x")
    fs.register_output(file_id="img-1", file_path=out_path, original_filename="in.jpg")
    in_path = fs.upload_dir / "in.jpg"
    in_path.write_text("in")
    fs.register_output(file_id="in-1", file_path=in_path, original_filename="in.jpg")

    def handler(params, cb):
        return {"output_file_id": "img-1"}

    tm.register_handler("image.upscale", handler, output_policy="history")
    task_id = await tm.submit("image.upscale", {"file_id": "in-1"})

    for _ in range(50):
        if tm.get_task(task_id).status.value in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    fd = fs.get_file("img-1")
    # Metadata still tagged for tool_id / source (useful for "來自" display) but show_in_results=False
    assert fd.metadata["tool_id"] == "image.upscale"
    assert fd.metadata["show_in_results"] is False
    assert not fs._sidecar_path("img-1").exists()


@pytest.mark.asyncio
async def test_history_policy_downgrades_on_multi_output(tm, fs, caplog):
    # Output files
    for fid in ("a", "b"):
        p = fs.output_dir / f"{fid}.wav"
        p.write_text("x")
        fs.register_output(file_id=fid, file_path=p, original_filename="in.wav")
    in_path = fs.upload_dir / "in.wav"
    in_path.write_text("in")
    fs.register_output(file_id="in-1", file_path=in_path, original_filename="in.wav")

    def handler(params, cb):
        return {"output_file_id": "a", "output_files": [{"file_id": "a"}, {"file_id": "b"}]}

    tm.register_handler("audio.fake_split", handler, output_policy="history")
    task_id = await tm.submit("audio.fake_split", {"file_id": "in-1"})

    for _ in range(50):
        if tm.get_task(task_id).status.value in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    # Downgraded to results
    assert fs.get_file("a").metadata["show_in_results"] is True
    assert fs.get_file("b").metadata["show_in_results"] is True
    assert "downgrade" in caplog.text.lower() or "results" in caplog.text.lower()


@pytest.mark.asyncio
async def test_submit_captures_file_id_on_taskdata(tm):
    """submit() should copy params['file_id'] onto TaskData for response-time
    file-name resolution."""
    tm.register_handler("audio.transcribe", lambda params, cb: {}, output_policy="history")
    task_id = await tm.submit("audio.transcribe", {"file_id": "in-42"})
    assert tm.get_task(task_id).file_id == "in-42"


@pytest.mark.asyncio
async def test_submit_without_file_id_leaves_taskdata_file_id_none(tm):
    """A task whose params carry no file_id keeps TaskData.file_id == None."""
    tm.register_handler("llm.chat", lambda params, cb: {}, output_policy="history")
    task_id = await tm.submit("llm.chat", {"prompt": "hi"})
    assert tm.get_task(task_id).file_id is None
