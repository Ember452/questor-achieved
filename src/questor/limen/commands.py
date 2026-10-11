"""危险命令黑名单：结构化正则清单，可追加，不做散落 if/else（B-32）。

参照 FlowCoder ``permissions/dangerous.py`` 的 8 类清单重写。判定看**命令串内容**
（这与审批层"判定用目标非内容"不同：审批是 habena 语义，这里是 L1 硬拒层——
`rm -rf /` 不需要知道意图）。

安全只读命令白名单（FlowCoder is_safe_command）随 M3 habena 审批流落地：
它回答的是"该不该送审"，M2.2 没有送审层，白名单在此无判断力上的意义；
硬拒语义已完整（危险 → 全档位拒绝）。
"""

from __future__ import annotations

import re

# 8 类不可恢复破坏（FlowCoder dangerous.py#L10-18 语义重写，正则为本项目自有）
DANGEROUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "rm -rf 根目录",
        re.compile(r"(?i)\brm\s+(-[a-z]*r[a-z]*f|-[a-z]*f[a-z]*r[a-z]*)\s+(/|~|\$HOME)(?:\s|$)"),
    ),
    ("mkfs 建文件系统", re.compile(r"(?i)\bmkfs\.")),
    ("dd 直写块设备", re.compile(r"(?i)\bdd\b[^|;&]*\bof=/dev/(?:sd|nvme|hd|vd)")),
    ("chmod 777 根目录", re.compile(r"(?i)\bchmod\s+-R\s+777\s+(/|~)(?:\s|$)")),
    ("fork 炸弹", re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")),
    ("curl 管道 shell", re.compile(r"(?i)\bcurl\b[^|;&]*\|\s*(?:ba)?sh\b")),
    ("wget 管道 shell", re.compile(r"(?i)\bwget\b[^|;&]*\|\s*(?:ba)?sh\b")),
    ("重定向覆盖块设备", re.compile(r"(?i)>\s*/dev/(?:sd|nvme|hd|vd)")),
)


def is_dangerous_command(command: str) -> str | None:
    """命中黑名单返回类别名（供拒绝理由），安全返回 ``None``。

    清单可追加：调用方（config 装配层）可将用户自定义规则并成正则序列传入
    gate；本模块持有的是不可协商的基线。
    """
    for label, pattern in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return label
    return None
