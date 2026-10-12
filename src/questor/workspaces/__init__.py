"""workspaces —— 工作区注册与路径可见性（overview §6）。

三柱归属：**可见**与**可干预**的边界输入——注册根路径集合是 limen 可达性推导
（M2.2）与工作区状态落盘的依据。

工作区身份 = canonical root 的 sha256[:16]（state.workspace_dir_name 的 slug-hash16
目录名同源）：同一真实目录（含符号链接别名、Windows 大小写差异）注册出同一 id，
不引入第二套身份。可见性判定 ``is_within_workspace`` 是 limen 的直接输入，
按"canonical + normcase + 分隔符边界"比较，拒绝前缀误伤（``/root-evil`` 不是
``/root`` 内部）与 ``..`` 逃逸（先 resolve 再比较）。
"""

from __future__ import annotations

import hashlib
import os
import pathlib

from questor.schemas.model import Workspace, utc_timestamp_now
from questor.state.atomic import mkdir_secure, write_atomic
from questor.state.locks import store_lock
from questor.state.paths import validate_entity_id, workspace_dir_name, workspaces_dir

_RECORD_FILE = "workspace.json"


class WorkspaceError(Exception):
    """工作区注册/注销失败的显式错误。"""


def _state_dir(root: pathlib.Path) -> pathlib.Path:
    return workspaces_dir() / workspace_dir_name(root)


def _canonical(root: pathlib.Path) -> pathlib.Path:
    return root.expanduser().resolve()


def _record_path(directory: pathlib.Path) -> pathlib.Path:
    return directory / _RECORD_FILE


def _workspace_id(canonical_root: pathlib.Path) -> str:
    digest = hashlib.sha256(str(canonical_root).encode("utf-8")).hexdigest()[:16]
    return digest


def register(root: pathlib.Path, name: str | None = None) -> Workspace:
    """注册工作区（幂等）：canonical root 决定 id，状态目录与记录随之创建。

    已注册的同 id 工作区：name 为 ``None`` 时原样返回既有记录；给了 name 则
    更新显示名（幂等覆盖）。
    """
    canonical = _canonical(root)
    workspace_id = _workspace_id(canonical)
    directory = _state_dir(canonical)
    with store_lock(workspaces_dir()):
        existing = _read_record(workspace_id)
        if existing is not None:
            if name is not None and name != existing.name:
                updated = existing.model_copy(update={"name": name})
                _write_record(updated, directory)
                return updated
            return existing
        workspace = Workspace(
            id=workspace_id,
            name=name if name is not None else canonical.name,
            root_paths=[str(canonical)],
            revision=0,
            created_at=utc_timestamp_now(),
        )
        _write_record(workspace, directory)
        return workspace


def _write_record(workspace: Workspace, directory: pathlib.Path) -> None:
    mkdir_secure(directory)
    write_atomic(_record_path(directory), workspace.model_dump_json().encode("utf-8") + b"\n")


def _read_record(workspace_id: str) -> Workspace | None:
    validate_entity_id(workspace_id)
    for path in _all_record_paths():
        try:
            candidate = Workspace.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError:
            continue  # 损坏记录跳过：注册表是可重建的登记，不是唯一真相
        if candidate.id == workspace_id:
            return candidate
    return None


def _all_record_paths() -> list[pathlib.Path]:
    root = workspaces_dir()
    if not root.is_dir():
        return []
    # 记录位于 <slug>-<id>/workspace.json，恰好一层深
    return sorted(root.glob(f"*/{_RECORD_FILE}"))


def get_workspace(workspace_id: str) -> Workspace | None:
    """按 id 查工作区；不存在返回 ``None``。"""
    return _read_record(workspace_id)


def current_revision(workspace_id: str) -> int:
    """取当前修订号；未注册报 :class:`WorkspaceError`。

    files/read 与 selection 定位都先拿它对照 `expected_revision`（B-92）；
    不匹配一律拒，不给过期结果。
    """
    record = _read_record(workspace_id)
    if record is None:
        raise WorkspaceError(f"工作区 {workspace_id} 未注册")
    return record.revision


def bump_revision(workspace_id: str) -> int:
    """修订号 +1 并落 workspace.json；返回新值（overview §7 单点递增）。

    写工具（write/edit）与 run 终止路径都走本函数，不在其他模块散写 revision。
    跨进程靠 store_lock 守一致性（与 register 同一把锁）；本函数同步实现，
    async 调用方请走 ``await asyncio.to_thread(bump_revision, ws_id)``。
    """
    validate_entity_id(workspace_id)
    with store_lock(workspaces_dir()):
        record = _read_record(workspace_id)
        if record is None:
            raise WorkspaceError(f"工作区 {workspace_id} 未注册")
        updated = record.model_copy(update={"revision": record.revision + 1})
        directory = _state_dir(pathlib.Path(updated.root_paths[0]))
        _write_record(updated, directory)
        return updated.revision


def list_workspaces() -> list[Workspace]:
    """列出全部已注册工作区（损坏记录跳过）。"""
    out: list[Workspace] = []
    for path in _all_record_paths():
        try:
            out.append(Workspace.model_validate_json(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return sorted(out, key=lambda w: w.created_at)


def unregister(workspace_id: str) -> None:
    """注销工作区并删除其状态目录；未注册时抛 :class:`WorkspaceError`。

    只删 ``~/.questor`` 内的状态登记，**永不触碰工作区内的任何文件**。
    """
    validate_entity_id(workspace_id)
    record = _read_record(workspace_id)
    if record is None:
        raise WorkspaceError(f"工作区 {workspace_id} 未注册")
    canonical = pathlib.Path(record.root_paths[0])
    directory = _state_dir(canonical)
    with store_lock(workspaces_dir()):
        for child in sorted(directory.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        if directory.is_dir():
            directory.rmdir()


def is_within_workspace(path: pathlib.Path, workspace: Workspace) -> bool:
    """路径是否落在工作区某个注册根之内（limen 可达性推导的输入）。

    比较 = canonical resolve + ``normcase``（Windows 大小写折叠）+ 分隔符边界；
    ``..`` 与符号链接在 resolve 阶段消化，不需要单独特判。
    """
    candidate = os.path.normcase(str(path.expanduser().resolve()))
    for root in workspace.root_paths:
        base = os.path.normcase(str(pathlib.Path(root).expanduser().resolve()))
        if candidate == base or candidate.startswith(base + os.sep):
            return True
    return False
