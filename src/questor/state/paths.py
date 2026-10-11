"""路径单点解析（overview §6 state 职责的第一条）。

全部路径必须经本模块解析，禁止任何模块散写 ``~/.questor`` 字面量（overview §14 门清单）。
env 覆盖每次调用时求值（B-73），不做模块级缓存。

# Reimplements wuu@wuu-main internal/statepath/statepath.go — pitfalls: B-73
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re

# Questor 实体 id：小写字母数字与连字符，服务端生成（data-model §1）
_ENTITY_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# 文件名安全字符：外部 id（如 provider 的 tool_use_id）可能带大写与下划线，
# 落盘只要求"构成安全的单个路径组件"——拒绝分隔符、冒号（Windows ADS）与点项
_FILENAME_COMPONENT = re.compile(r"^[A-Za-z0-9._-]+$")

_SLUG_MAX = 48
_SLUG_FALLBACK = "workspace"


def questor_home() -> pathlib.Path:
    """返回 Questor 存储根目录。

    ``QUESTOR_HOME`` 非空（去首尾空白后）时整体重定向为该绝对路径，否则
    ``<用户主目录>/.questor``。每次调用都重新读取环境变量（B-73），测试与
    多实例场景才能可靠隔离。
    """
    override = os.environ.get("QUESTOR_HOME", "").strip()
    if override:
        return pathlib.Path(override).resolve()
    return pathlib.Path.home() / ".questor"


def sessions_dir() -> pathlib.Path:
    """会话正文目录：append-only JSONL 唯一真相源（data-model §5）。"""
    return questor_home() / "sessions"


def index_dir() -> pathlib.Path:
    """搜索索引目录：可丢弃可重建，损坏即重建不修复（data-model §5）。"""
    return questor_home() / "index"


def files_dir() -> pathlib.Path:
    """工作文件目录（粘贴长文本/图片），带过期，清理与历史快照分离（data-model §5）。"""
    return questor_home() / "files"


def workspaces_dir() -> pathlib.Path:
    """工作区状态根目录；每个工作区一个 ``<slug>-<hash16>`` 子目录。"""
    return questor_home() / "workspaces"


def config_path() -> pathlib.Path:
    """用户级配置文件路径（config 模块消费；data-model §5）。"""
    return questor_home() / "config.toml"


def validate_entity_id(entity_id: str) -> str:
    """校验 Questor 实体 id（data-model §1 形状），非法即抛 ``ValueError``。

    这不是文件名安全检查——是 id 形状契约：非法 id 在入口处爆炸，
    不允许变成文件名里的路径逃逸。
    """
    if not _ENTITY_ID.match(entity_id):
        raise ValueError(f"非法实体 id：{entity_id!r}（须匹配 {_ENTITY_ID.pattern}）")
    return entity_id


def validate_filename_component(name: str) -> str:
    """校验外部 id 可安全用作单个文件名组件，非法即抛 ``ValueError``。

    外部 id（provider 的 tool_use_id 等）不受 Questor id 形状约束，但落盘必须
    拒绝路径分隔符、盘符冒号、空串与相对路径点项。
    """
    if not name or name in {".", ".."} or not _FILENAME_COMPONENT.match(name):
        raise ValueError(f"非法文件名组件：{name!r}")
    return name


def thread_path(thread_id: str) -> pathlib.Path:
    """线程正文文件路径 ``<sessions>/<thread_id>.jsonl``；id 非法即抛 ``ValueError``。"""
    return sessions_dir() / f"{validate_entity_id(thread_id)}.jsonl"


def tool_result_path(tool_use_id: str) -> pathlib.Path:
    """工具结果落盘路径 ``<sessions>/<tool_use_id>.txt``（data-model §5，B-24）。

    tool_use_id 来自 provider，按文件名组件校验而非实体 id 形状。
    """
    return sessions_dir() / f"{validate_filename_component(tool_use_id)}.txt"


def sanitize_slug(name: str) -> str:
    """目录名 slug：仅保留 ``[A-Za-z0-9._-]``，其余折叠为单个 ``-``，上限 48 字符。

    折叠连续非法字符为一个 ``-``，掐头去尾的 ``.-``，截断后再次去尾——保证产物
    永远是安全的单个路径组件；全非法时回落 ``workspace``。
    """
    pieces: list[str] = []
    last_dash = False
    for ch in name:
        if ch.isascii() and (ch.isalnum() or ch in {".", "_", "-"}):
            pieces.append(ch)
            last_dash = False
            continue
        if not last_dash:
            pieces.append("-")
            last_dash = True
    slug = "".join(pieces).strip(".-")
    if len(slug) > _SLUG_MAX:
        slug = slug[:_SLUG_MAX].strip(".-")
    return slug or _SLUG_FALLBACK


def workspace_dir_name(root: pathlib.Path) -> str:
    """工作区状态目录名 ``<slug>-<sha256(canonical_root)[:16]>``。

    root 先做 ``resolve()``（含符号链接解析），保证符号链接路径与真实路径映射到
    同一目录（wuu `statepath.go#WorkspaceDir` 的语义）；目录名含内容哈希，
    不可预测的用户内容不会直接成为目录名。
    """
    canonical = str(root.expanduser().resolve())
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{sanitize_slug(root.resolve().name)}-{digest}"
