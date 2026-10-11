"""对抗：活跃线程拒删与归档（M2.1 出口判据"会话删除"）。

有未终态 run（queued/running/steered/waiting）的线程：删除与归档一律拒绝；
全部终态后：删除成功，正文与索引条目一并消失。
"""

from __future__ import annotations

import pytest

import questor.gesta as gesta
from questor.schemas.model import (
    Origin,
    PermissionMode,
    Run,
    RunStatus,
    Thread,
    Timestamp,
)
from questor.state.paths import thread_path
from questor.testenv.fake_home import fake_home

T0: Timestamp = "2026-10-11T08:30:00Z"


def _setup() -> None:
    gesta.create_thread(
        Thread(
            id="thread-del",
            workspace_id="ws-0001",
            title=None,
            engine_id="engine-01",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=T0,
            updated_at=T0,
        )
    )
    gesta.add_turn(
        "thread-del",
        turn_id="turn-0001",
        origin=Origin.USER,
        created_at=T0,
    )
    gesta.add_run(
        "thread-del",
        Run(
            id="run-0001",
            turn_id="turn-0001",
            engine_id="engine-01",
            permission_mode=PermissionMode.STANDARD,
            status=RunStatus.QUEUED,
            created_at=T0,
        ),
    )


@pytest.mark.parametrize(
    "status",
    [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.STEERED, RunStatus.WAITING],
)
def test_delete_and_archive_rejected_while_active(status: RunStatus) -> None:
    with fake_home():
        _setup()
        if status != RunStatus.QUEUED:
            gesta.transition_run("thread-del", "run-0001", RunStatus.RUNNING)
            if status in (RunStatus.STEERED, RunStatus.WAITING):
                gesta.transition_run("thread-del", "run-0001", status)
        with pytest.raises(gesta.ThreadStoreError, match="未终态"):
            gesta.delete_thread("thread-del")
        with pytest.raises(gesta.ThreadStoreError, match="运行中"):
            gesta.set_thread_flags("thread-del", archived=True)
        assert thread_path("thread-del").is_file(), "被拒的删除不得动文件"


def test_delete_succeeds_after_terminal() -> None:
    with fake_home():
        _setup()
        gesta.transition_run("thread-del", "run-0001", RunStatus.CANCELLED)
        gesta.delete_thread("thread-del")
        assert not thread_path("thread-del").exists()
        assert [s.id for s in gesta.list_threads()] == []
        with pytest.raises(gesta.ThreadNotFound):
            gesta.load_thread("thread-del")
