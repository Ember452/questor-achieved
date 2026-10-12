"""编排域存储：独立 append-only JSONL 唯一真相源 + fold 投影 + 可重建索引（ADR-0025）。

落盘契约与 `gesta/store.py` 同构（B-74 残尾容忍、append-only、`state` 跨进程锁），
但住**独立文件** `<home>/orchestration/tasks.jsonl`，不写进线程会话正文——编排是有界
上下文（看板跨线程、Goal 跨轮、将来多 Agent 树），塞进会话格式会被反向需求牵着走。

状态写路径的唯一入口是 :func:`transition_task`：它经 `orchestration.transitions` 白名单裁决，
与 gesta 的 run 状态迁移同一纪律（旁路写入即契约破坏）。`update_task` 只改非状态字段。

记录 kind：`task.created` / `task.updated` / `task.status` / `plan.created` / `plan.updated`
/ `goal.created` / `goal.updated` / `evidence.appended` / `acceptance.invalidated`。

索引 `tasks.json` 是摘要缓存（可丢弃可重建），temp+rename 原子替换。

# Reimplements evoflow@<tag> collab/state_transitions.py — pitfalls: B-38 B-39 B-43
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from questor.orchestration.acceptance import transition as _transition_acceptance
from questor.orchestration.transitions import is_terminal, transition
from questor.schemas.model import AcceptanceStatus, utc_timestamp_now
from questor.schemas.orchestration import (
    Evidence,
    Goal,
    Plan,
    Task,
    TaskAcceptance,
    TaskStatus,
)
from questor.state.atomic import write_atomic
from questor.state.locks import store_lock
from questor.state.paths import orchestration_dir, orchestration_log_path

__all__ = [
    "OrchestrationStoreError",
    "OrchestrationView",
    "TaskNotFound",
    "add_evidence",
    "add_goal",
    "add_plan",
    "add_task",
    "invalidate_acceptances",
    "list_tasks",
    "load_view",
    "rebuild_index",
    "transition_acceptance",
    "transition_task",
    "update_goal",
    "update_plan",
    "update_task",
]


class OrchestrationStoreError(Exception):
    """编排存储层错误的基类。"""


class TaskNotFound(OrchestrationStoreError):
    """引用了不存在的任务 id。"""


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seq: int = Field(ge=1)
    kind: str
    payload: dict[str, Any]
    recorded_at: str

    def to_line(self) -> str:
        return self.model_dump_json()


_RECORD_KINDS = frozenset(
    {
        "task.created",
        "task.updated",
        "task.status",
        "plan.created",
        "plan.updated",
        "goal.created",
        "goal.updated",
        "evidence.appended",
        "acceptance.invalidated",
        "acceptance.status",
    }
)


class OrchestrationView(BaseModel):
    """记录流 fold 出的当前状态（只读投影）。"""

    model_config = ConfigDict(frozen=True)

    tasks: tuple[Task, ...] = ()
    plans: tuple[Plan, ...] = ()
    goals: tuple[Goal, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    last_seq: int = Field(default=0, ge=0)


class TaskSummary(BaseModel):
    """看板索引条目：任务摘要，不含正文。"""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    status: TaskStatus
    thread_id: str | None
    goal_id: str | None
    updated_at: str


class _IndexFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int
    tasks: list[TaskSummary]


_INDEX_VERSION = 1


# ---- 读取与 fold（无锁；B-74 残尾容忍） ----


def _parse_line(text: str) -> _Record | None:
    text = text.strip()
    if not text:
        return None
    try:
        record = _Record.model_validate(json.loads(text))
    except (ValueError, ValidationError):
        return None
    if record.kind not in _RECORD_KINDS:
        return None
    return record


def _read_records(path: pathlib.Path) -> list[_Record]:
    if not path.is_file():
        return []
    records: list[_Record] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        record = _parse_line(line)
        if record is not None:
            records.append(record)
    return records


class _FoldState:
    """记录流的可变折叠状态（全量 fold 与增量共用一套语义）。"""

    def __init__(self) -> None:
        self.tasks: list[Task] = []
        self.plans: list[Plan] = []
        self.goals: list[Goal] = []
        self.evidence: list[Evidence] = []
        self.last_seq = 0

    def apply(self, record: _Record) -> None:
        self.last_seq = max(self.last_seq, record.seq)
        payload = record.payload
        if record.kind in ("task.created", "task.updated"):
            task = Task.model_validate(payload)
            self.tasks = [t for t in self.tasks if t.id != task.id] + [task]
        elif record.kind == "task.status":
            self._apply_status(payload)
        elif record.kind in ("plan.created", "plan.updated"):
            plan = Plan.model_validate(payload)
            self.plans = [p for p in self.plans if p.id != plan.id] + [plan]
        elif record.kind in ("goal.created", "goal.updated"):
            goal = Goal.model_validate(payload)
            self.goals = [g for g in self.goals if g.id != goal.id] + [goal]
        elif record.kind == "evidence.appended":
            self.evidence.append(Evidence.model_validate(payload))
        elif record.kind == "acceptance.status":
            self._apply_acceptance(payload)
        elif record.kind == "acceptance.invalidated":
            self._apply_invalidation(payload)

    def _apply_status(self, payload: dict[str, Any]) -> None:
        task = self._require_task(str(payload.get("task_id", "")))
        to_raw = payload.get("to")
        if not isinstance(to_raw, str):
            raise OrchestrationStoreError("task.status 记录缺少 to 字段")
        try:
            target = TaskStatus(to_raw)
        except ValueError as exc:
            raise OrchestrationStoreError(f"task.status 含未知状态 {to_raw!r}") from exc
        moved = transition(task.status, target)  # 回放同样过白名单：篡改历史在此爆炸
        self._replace_task(task.model_copy(update={"status": moved}))

    def _apply_acceptance(self, payload: dict[str, Any]) -> None:
        """回放验收态迁移：脏字段报存储错；非法序列漏 InvalidAcceptanceTransition
        （篡改历史属契约破坏，同 `_apply_status` 不降级为存储错）。"""
        task = self._require_task(str(payload.get("task_id", "")))
        to_raw = payload.get("to")
        if not isinstance(to_raw, str):
            raise OrchestrationStoreError("acceptance.status 记录缺少 to 字段")
        try:
            target = AcceptanceStatus(to_raw)
        except ValueError as exc:
            raise OrchestrationStoreError(f"acceptance.status 含未知验收态 {to_raw!r}") from exc
        raw_ids = payload.get("evidence_ids", [])
        if not isinstance(raw_ids, list):
            raise OrchestrationStoreError(f"acceptance.status 的 evidence_ids 非列表：{raw_ids!r}")
        moved = _transition_acceptance(task.acceptance.status, target)  # 回放同过白名单
        new_acc = task.acceptance.model_copy(
            update={"status": moved, "evidence_ids": tuple(str(x) for x in raw_ids)}
        )
        self._replace_task(task.model_copy(update={"acceptance": new_acc}))

    def _apply_invalidation(self, payload: dict[str, Any]) -> None:
        # 脏记录统一报存储错（B-76 口径：不得漏裸 KeyError/TypeError 给回放调用方）
        raw_revision = payload.get("requirement_revision")
        if raw_revision is None:
            raise OrchestrationStoreError("acceptance.invalidated 记录缺 requirement_revision")
        try:
            requirement_revision = int(raw_revision)
        except (TypeError, ValueError) as exc:
            raise OrchestrationStoreError(
                f"acceptance.invalidated 记录非法 requirement_revision：{raw_revision!r}"
            ) from exc
        task_ids = payload.get("task_ids", [])
        if not isinstance(task_ids, list):
            raise OrchestrationStoreError(
                f"acceptance.invalidated 的 task_ids 非列表：{task_ids!r}"
            )
        for task_id in task_ids:
            task = next((t for t in self.tasks if t.id == task_id), None)
            if task is None:
                continue
            reset = TaskAcceptance(
                status=AcceptanceStatus.PROPOSED,
                requirement_revision=requirement_revision,
                evidence_ids=(),
            )
            self._replace_task(task.model_copy(update={"acceptance": reset}))

    def _require_task(self, task_id: str) -> Task:
        task = next((t for t in self.tasks if t.id == task_id), None)
        if task is None:
            raise OrchestrationStoreError(f"记录引用了不存在的任务 {task_id!r}")
        return task

    def _replace_task(self, task: Task) -> None:
        self.tasks = [t for t in self.tasks if t.id != task.id] + [task]

    def build_view(self) -> OrchestrationView:
        return OrchestrationView(
            tasks=tuple(self.tasks),
            plans=tuple(self.plans),
            goals=tuple(self.goals),
            evidence=tuple(self.evidence),
            last_seq=self.last_seq,
        )


def _fold(records: list[_Record]) -> OrchestrationView:
    state = _FoldState()
    for record in records:
        state.apply(record)
    return state.build_view()


def load_view() -> OrchestrationView:
    """读取并 fold 编排当前状态；无文件返回空视图。"""
    return _fold(_read_records(orchestration_log_path()))


# ---- 索引（摘要缓存；可丢弃可重建） ----


def _index_path() -> pathlib.Path:
    return orchestration_dir() / "tasks.json"


def _summary(task: Task) -> TaskSummary:
    return TaskSummary(
        id=task.id,
        title=task.title,
        status=task.status,
        thread_id=task.thread_id,
        goal_id=task.goal_id,
        updated_at=task.updated_at,
    )


def _load_index() -> _IndexFile | None:
    path = _index_path()
    if not path.is_file():
        return None
    try:
        return _IndexFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ValidationError):
        return None  # 索引是缓存：损坏即重建，不修复


def _rewrite_index_locked(entries: list[TaskSummary]) -> None:
    data = _IndexFile(version=_INDEX_VERSION, tasks=entries)
    write_atomic(_index_path(), data.model_dump_json(indent=2).encode("utf-8") + b"\n")


def rebuild_index() -> list[TaskSummary]:
    """从 JSONL 全量重建任务摘要索引并落盘。"""
    entries = [_summary(task) for task in load_view().tasks]
    with store_lock(orchestration_dir()):
        _rewrite_index_locked(entries)
    return entries


def list_tasks() -> list[TaskSummary]:
    """列出任务摘要（读索引；缺失或损坏时先重建）。"""
    index = _load_index()
    if index is None:
        return rebuild_index()
    return index.tasks


# ---- 追加原语（持锁调用） ----


def _ends_with_newline(path: pathlib.Path) -> bool:
    if not path.exists():
        return True
    if path.stat().st_size == 0:
        return True
    with path.open("rb") as handle:
        handle.seek(-1, 2)
        return handle.read(1) == b"\n"


def _append_locked(kind: str, payload: dict[str, Any], last_seq: int) -> None:
    """整行追加一条记录；追加永不粘接残尾、永不截断（B-74）。"""
    record = _Record(seq=last_seq + 1, kind=kind, payload=payload, recorded_at=utc_timestamp_now())
    path = orchestration_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = record.to_line().encode("utf-8") + b"\n"
    if not _ends_with_newline(path):
        data = b"\n" + data
    with path.open("ab") as handle:
        handle.write(data)
        handle.flush()


def _upsert_index_locked(task: Task) -> None:
    index = _load_index() or _IndexFile(version=_INDEX_VERSION, tasks=[])
    entries = [s for s in index.tasks if s.id != task.id]
    entries.append(_summary(task))
    entries.sort(key=lambda s: s.updated_at)
    _rewrite_index_locked(entries)


# ---- 公共 API ----


def add_task(task: Task) -> Task:
    """追加一个任务；同 id 已存在即抛 :class:`OrchestrationStoreError`。"""
    with store_lock(orchestration_dir()):
        view = load_view()
        if any(t.id == task.id for t in view.tasks):
            raise OrchestrationStoreError(f"任务 {task.id} 已存在")
        _append_locked("task.created", task.model_dump(mode="json"), view.last_seq)
        _upsert_index_locked(task)
        return task


def update_task(task: Task) -> Task:
    """整对象覆盖任务**非状态字段**（run_id、acceptance、depends_on 等）。

    状态字段不得经本函数改：与落盘现值不一致即拒绝，逼调用方走 :func:`transition_task`
    （状态迁移唯一入口的机械表达）。
    """
    with store_lock(orchestration_dir()):
        view = load_view()
        current = next((t for t in view.tasks if t.id == task.id), None)
        if current is None:
            raise TaskNotFound(task.id)
        if task.status != current.status:
            raise OrchestrationStoreError(
                f"update_task 不得改状态（{current.status.value}→{task.status.value}）；"
                "用 transition_task"
            )
        if task.acceptance.status != current.acceptance.status:
            raise OrchestrationStoreError(
                f"update_task 不得改验收态（{current.acceptance.status.value}→"
                f"{task.acceptance.status.value}）；用 transition_acceptance"
            )
        _append_locked("task.updated", task.model_dump(mode="json"), view.last_seq)
        _upsert_index_locked(task)
        return task


def transition_task(task_id: str, target: TaskStatus) -> Task:
    """推进任务状态：唯一入口（transitions 白名单裁决），迁移记录追加进正文。"""
    with store_lock(orchestration_dir()):
        view = load_view()
        task = next((t for t in view.tasks if t.id == task_id), None)
        if task is None:
            raise TaskNotFound(task_id)
        moved = transition(task.status, target)  # 白名单外抛 InvalidTaskTransition，不落盘
        updated = task.model_copy(update={"status": moved, "updated_at": utc_timestamp_now()})
        _append_locked(
            "task.status",
            {"task_id": task_id, "from": task.status.value, "to": moved.value},
            view.last_seq,
        )
        _upsert_index_locked(updated)
        return updated


def transition_acceptance(
    task_id: str, target: AcceptanceStatus, *, evidence_ids: tuple[str, ...] | None = None
) -> Task:
    """推进验收态：唯一入口（acceptance 白名单裁决）；可选原子链入 ``evidence_ids``。

    ``evidence_ids`` 缺省保留现值；report 步在驱动 `executing → reported → verified|regressed`
    时同批写入证据 id（append-only：迁移与链证据在同一条 `acceptance.status` 记录里）。
    白名单外抛 :class:`InvalidAcceptanceTransition`，不落盘。
    """
    with store_lock(orchestration_dir()):
        view = load_view()
        task = next((t for t in view.tasks if t.id == task_id), None)
        if task is None:
            raise TaskNotFound(task_id)
        moved = _transition_acceptance(task.acceptance.status, target)
        next_ids = task.acceptance.evidence_ids if evidence_ids is None else tuple(evidence_ids)
        new_acc = task.acceptance.model_copy(update={"status": moved, "evidence_ids": next_ids})
        updated = task.model_copy(update={"acceptance": new_acc, "updated_at": utc_timestamp_now()})
        _append_locked(
            "acceptance.status",
            {
                "task_id": task_id,
                "from": task.acceptance.status.value,
                "to": moved.value,
                "evidence_ids": list(next_ids),
            },
            view.last_seq,
        )
        _upsert_index_locked(updated)
        return updated


def add_plan(plan: Plan) -> Plan:
    with store_lock(orchestration_dir()):
        view = load_view()
        _append_locked("plan.created", plan.model_dump(mode="json"), view.last_seq)
        return plan


def update_plan(plan: Plan) -> Plan:
    with store_lock(orchestration_dir()):
        view = load_view()
        if not any(p.id == plan.id for p in view.plans):
            raise OrchestrationStoreError(f"计划 {plan.id} 不存在")
        _append_locked("plan.updated", plan.model_dump(mode="json"), view.last_seq)
        return plan


def add_goal(goal: Goal) -> Goal:
    with store_lock(orchestration_dir()):
        view = load_view()
        _append_locked("goal.created", goal.model_dump(mode="json"), view.last_seq)
        return goal


def update_goal(goal: Goal) -> Goal:
    with store_lock(orchestration_dir()):
        view = load_view()
        if not any(g.id == goal.id for g in view.goals):
            raise OrchestrationStoreError(f"目标 {goal.id} 不存在")
        _append_locked("goal.updated", goal.model_dump(mode="json"), view.last_seq)
        return goal


def add_evidence(evidence: Evidence) -> Evidence:
    with store_lock(orchestration_dir()):
        view = load_view()
        _append_locked("evidence.appended", evidence.model_dump(mode="json"), view.last_seq)
        return evidence


def invalidate_acceptances(*, task_ids: list[str], requirement_revision: int) -> None:
    """需求改版 → 作废既有验收：**追加**一条作废记录，不改写历史（append-only）。

    改版后任务的 acceptance 被重置为 `proposed` 且绑定新的 `requirement_revision`
    （由 fold 应用），旧结论留在记录流里可审计。
    """
    if not task_ids:
        return
    with store_lock(orchestration_dir()):
        view = load_view()
        _append_locked(
            "acceptance.invalidated",
            {"task_ids": list(task_ids), "requirement_revision": requirement_revision},
            view.last_seq,
        )


def is_open(task: Task) -> bool:
    """任务是否未终态（供清扫与看板过滤用）。"""
    return not is_terminal(task.status)
