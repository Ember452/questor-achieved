"""review —— 工作区修订号 + 写时 diff + turn↔revision 绑定（overview §6）。

**依赖方向**：review 只可 import limen / state / schemas（structure §5 表已登记），
不得反向 import tools / engine；写时 diff 由 tools/impl/{write,edit} 主动调用本包的
:func:`compute_diff` 生成，避免"事后重扫"造成两套真相（B-66/B-93）。

对外形状：
- :func:`compute_diff` —— unified diff + hunks + 内容指纹，落 `ToolResult.data["diff"]`；
- :func:`aggregate_turn_diff` —— 从 thread view 聚合某 turn 覆盖的 run 里的 diff 集合；
- 修订号的单点在 workspaces（`bump_revision` / `current_revision`），本包只做呈现。
"""

from __future__ import annotations

from questor.review.diff import FileDiff, compute_diff
from questor.review.turn_bindings import aggregate_turn_diff

__all__ = ["FileDiff", "aggregate_turn_diff", "compute_diff"]
