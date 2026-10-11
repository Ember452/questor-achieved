"""三档 × 边界三元组的显式表（B-33：档位语义表驱动，不做分支散布）。

wuu boundary.go 的三构造器直译为数据表：``{enforce_paths, allow_mutations}``。
守卫链（敏感路径、危险命令）在所有档位恒开——表里没有"关守卫"这一列，
档位不解除守卫（B-54）正是靠"表里根本没有那个开关"来保证的。
"""

from __future__ import annotations

from questor.limen.gate import Boundary
from questor.schemas.model import PermissionMode

__all__ = ["MODE_BOUNDARIES", "boundary_for"]

# 模式 → 边界三元组。读档位注释与 overview §9 逐字对照。
MODE_BOUNDARIES: dict[PermissionMode, Boundary] = {
    # 只读档：读范围不变（路径门仍在），写调用一律拒
    PermissionMode.READ_ONLY: Boundary(enforce_paths=True, allow_mutations=False),
    # 标准档：注册根内可写（路径门强制），命令经进程树管理；Windows 上无 OS 写隔离
    # （ADR-0007：执行侧须如实声明 sandboxed=false，本表不提供"假装沙箱化"的选项）
    PermissionMode.STANDARD: Boundary(enforce_paths=True, allow_mutations=True),
    # 非受限档：去路径边界与进程沙箱；敏感路径守卫仍在（B-54，表里无开关）
    PermissionMode.UNCONFINED: Boundary(enforce_paths=False, allow_mutations=True),
}


def boundary_for(mode: PermissionMode) -> Boundary:
    """查模式对应的边界三元组；未知模式显式 KeyError（schemas 枚举兜底，防御未来漂移）。"""
    return MODE_BOUNDARIES[mode]
