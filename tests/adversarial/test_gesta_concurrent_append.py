"""对抗：跨进程并发追加（gesta 锁契约的运行时面）。

两个子进程 + 父进程同时向同一线程追加 Item：所有记录必须整行落地、不丢不重，
seq 严格稠密——这验证 store_lock 串行化 + O_APPEND 整行语义的组合。
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import questor.gesta as gesta
from questor.schemas.model import (
    Item,
    ItemKind,
    Origin,
    PermissionMode,
    Run,
    RunStatus,
    Thread,
    Timestamp,
    utc_timestamp_now,
)
from questor.testenv.fake_home import fake_home

REPO = pathlib.Path(__file__).resolve().parents[2]

T0: Timestamp = "2026-10-11T08:30:00Z"

_CHILD = """
import sys
from questor.gesta import add_item
from questor.schemas.model import Item, ItemKind, utc_timestamp_now

thread_id = sys.argv[1]
run_id = sys.argv[2]
prefix = sys.argv[3]
count = int(sys.argv[4])
for i in range(count):
    add_item(thread_id, Item(
        id=f"item-{prefix}-{i:04d}",
        run_id=run_id,
        kind=ItemKind.MESSAGE,
        payload={"text": f"hello-{prefix}-{i} " * 20},
        evidence=None,
        created_at=utc_timestamp_now(),
    ))
"""


def _spawn_writer(
    env: dict[str, str], thread_id: str, run_id: str, prefix: str, count: int
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-c", _CHILD, thread_id, run_id, prefix, str(count)],
        env=env,
    )


def test_concurrent_appends_from_three_writers() -> None:
    with fake_home():
        env = dict(os.environ)
        src = str(REPO / "src")
        env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

        thread = Thread(
            id="thread-conc",
            workspace_id="ws-0001",
            title=None,
            engine_id="engine-01",
            permission_mode=PermissionMode.STANDARD,
            pinned=False,
            archived=False,
            created_at=T0,
            updated_at=T0,
        )
        gesta.create_thread(thread)
        gesta.add_turn(
            "thread-conc",
            turn_id="turn-0001",
            origin=Origin.USER,
            created_at=T0,
        )
        gesta.add_run(
            "thread-conc",
            Run(
                id="run-0001",
                turn_id="turn-0001",
                engine_id="engine-01",
                permission_mode=PermissionMode.STANDARD,
                status=RunStatus.QUEUED,
                created_at=T0,
            ),
        )

        children = [
            _spawn_writer(env, "thread-conc", "run-0001", prefix, count=25)
            for prefix in ("aaa", "bbb")
        ]
        # 父进程同时追加 10 条
        for i in range(10):
            gesta.add_item(
                "thread-conc",
                Item(
                    id=f"item-ccc-{i:04d}",
                    run_id="run-0001",
                    kind=ItemKind.MESSAGE,
                    payload={"text": f"parent-{i} " * 20},
                    evidence=None,
                    created_at=utc_timestamp_now(),
                ),
            )
        for child in children:
            assert child.wait(timeout=60) == 0, "子进程追加失败"

        view = gesta.load_thread("thread-conc")
        # 3（created+turn+run）+ 60 条 item，seq 稠密无空洞
        assert view.last_seq == 63
        assert len(view.items) == 60
        item_ids = {item.id for item in view.items}
        assert len(item_ids) == 60, "追加不允许丢行或重号"
        # 每条 item 都完整可解析（整行落地，无半行被静默吃掉一半内容）
        for item in view.items:
            assert item.payload["text"].endswith(" ")
