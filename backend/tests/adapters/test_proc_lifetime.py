"""Unit tests for the process-lifetime binding helper."""
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.binary import _proc_lifetime as pl

win_only = pytest.mark.skipif(sys.platform != "win32", reason="Win32 Job Object only")


def test_kill_on_job_close_flag_constant():
    assert pl.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE == 0x2000


@win_only
def test_build_extended_limit_info_sets_kill_on_close():
    info = pl.build_extended_limit_info()
    assert (info.BasicLimitInformation.LimitFlags
            & pl.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)


@win_only
def test_create_job_success_returns_handle():
    k = MagicMock()
    k.CreateJobObjectW.return_value = 555
    k.SetInformationJobObject.return_value = 1
    with patch.object(pl, "_kernel32", k):
        job = pl.create_kill_on_close_job()
    assert job == 555
    k.CreateJobObjectW.assert_called_once()
    k.SetInformationJobObject.assert_called_once()
    # info class arg (2nd positional) must be JobObjectExtendedLimitInformation (9)
    assert k.SetInformationJobObject.call_args.args[1] == 9


@win_only
def test_create_job_create_failure_returns_none():
    k = MagicMock()
    k.CreateJobObjectW.return_value = 0  # NULL → failure
    with patch.object(pl, "_kernel32", k):
        assert pl.create_kill_on_close_job() is None
    k.SetInformationJobObject.assert_not_called()


@win_only
def test_create_job_setinfo_failure_closes_handle_returns_none():
    k = MagicMock()
    k.CreateJobObjectW.return_value = 555
    k.SetInformationJobObject.return_value = 0  # failure
    with patch.object(pl, "_kernel32", k):
        assert pl.create_kill_on_close_job() is None
    k.CloseHandle.assert_called_once_with(555)


@win_only
def test_assign_process_success():
    k = MagicMock()
    k.AssignProcessToJobObject.return_value = 1
    with patch.object(pl, "_kernel32", k):
        assert pl.assign_process_to_job(555, 1234) is True
    k.AssignProcessToJobObject.assert_called_once_with(555, 1234)


@win_only
def test_assign_process_failure_returns_false():
    k = MagicMock()
    k.AssignProcessToJobObject.return_value = 0
    with patch.object(pl, "_kernel32", k):
        assert pl.assign_process_to_job(555, 1234) is False


@win_only
def test_close_job_swallows_errors():
    k = MagicMock()
    k.CloseHandle.side_effect = OSError("bad handle")
    with patch.object(pl, "_kernel32", k):
        pl.close_job(555)  # must not raise


def test_posix_preexec_is_linux_only():
    if sys.platform.startswith("linux"):
        assert callable(pl.posix_pdeathsig_preexec())
    else:
        # win32 (Popen requires None) AND darwin (no libc.so.6/prctl — the
        # closure would crash every spawn inside the forked child).
        assert pl.posix_pdeathsig_preexec() is None
