"""可达性推导：路径是否落在注册根集合之内（B-30 二段 resolve；Windows 大小写折叠）。

输入是纯数据（``roots`` 字符串列表 = ``Workspace.root_paths``，由调用方从
workspaces 注入——依赖矩阵禁止 limen import workspaces）。语义参照 FlowCoder
``permissions/sandbox.py`` 的二段 resolve + wuu ``ResolvePath`` 的 EvalSymlinks。

关键坑（B-30）：不存在的路径不能只 resolve 一次——向上找最近存在祖先、resolve
祖先、拼回尾部之后，**必须对完整结果再 resolve(strict=False) 重查**：拼回尾部
可能重新引入 ".." 段，而前缀比较是纯词法匹配、不会消除 ".."。
"""

from __future__ import annotations

import os
import pathlib


def _normcase(path_text: str) -> str:
    """Windows 大小写折叠（wuu resolveStartCWD 同款）；POSIX 恒等。"""
    return os.path.normcase(path_text)


def _resolve_two_phase(raw: pathlib.Path) -> pathlib.Path:
    """二段 resolve（B-30）：存在路径直接 resolve；不存在路径 resolve 最近存在
    祖先后拼回尾部，**再对完整结果 resolve(strict=False) 重查**。"""
    absolute = pathlib.Path(os.path.expanduser(str(raw))).absolute()
    if absolute.exists():
        return absolute.resolve()
    # 向上找最近存在祖先
    missing_tail: list[str] = []
    cursor = absolute
    while not cursor.exists():
        if cursor.parent == cursor:
            # 到达文件系统根仍无存在祖先（Windows 空盘符等病态输入）：让 strict resolve 报错
            return absolute.resolve()
        missing_tail.append(cursor.name)
        cursor = cursor.parent
    resolved_ancestor = cursor.resolve()
    for segment in reversed(missing_tail):
        resolved_ancestor = resolved_ancestor / segment
    # B-30：拼回尾部后对完整结果再 resolve(strict=False) 重查——
    # 尾部可能重新引入 ".."（如 missing_tail 含 ".." 段），不重查即可穿越
    return resolved_ancestor.resolve(strict=False)


def is_within(path_text: str, roots: list[str]) -> bool:
    """``path``（已 canonical 的字符串或原始输入）是否落在 ``roots`` 某个根内。

    比较 = canonical resolve（含符号链接展开）+ normcase（Windows 大小写折叠）
    + 分隔符边界（``/root-evil`` 不是 ``/root`` 内部）。
    """
    candidate = _normcase(str(_resolve_two_phase(pathlib.Path(path_text))))
    for root_text in roots:
        base = _normcase(str(_resolve_two_phase(pathlib.Path(root_text))))
        if candidate == base or candidate.startswith(base + os.sep):
            return True
    return False


def check_path(
    path_text: str | None, roots: list[str], *, expects_path: bool
) -> tuple[bool, str | None]:
    """路径门判定：返回 ``(允许, 拒绝原因)``。

    - ``expects_path`` 且 ``path_text`` 缺失 → deny（B-31：缺路径参数视为拒绝而非跳过）；
    - 不期望路径的调用（shell/meta 类）恒允许通过此门（其余守卫另行判定）；
    - 存在路径走二段 resolve + 根集合比较。
    """
    if not expects_path:
        return True, None
    if not path_text or not path_text.strip():
        return False, "工具调用缺少必需的路径参数"
    if is_within(path_text, roots):
        return True, None
    return False, f"路径 {path_text!r} 超出注册根范围"
