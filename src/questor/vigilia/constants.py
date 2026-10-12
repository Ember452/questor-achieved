"""vigilia 阈值常量表（魔法数不散布——与 `engine/constants.py` 同一纪律）。

`tests/unit/test_vigilia_*.py` 直接引用这些常量，改值即改行为；护栏不写死数字。
"""

from __future__ import annotations

#: 一个 tick 的默认间隔（秒）；无人值守队列的节流下限
DEFAULT_TICK_SECONDS = 60
#: 一个 tick 最多并发启动的触发数（B-49 的并发上限）
DEFAULT_MAX_CONCURRENT = 2
#: 僵尸清扫批次下限（B-40：无 offset 重查同一 top-N 会紧密空转，故必须分批）
SWEEP_BATCH_MIN = 10
#: 清扫间隔（秒）；一批一间隔，剩余下轮再收（B-40）
DEFAULT_SWEEP_INTERVAL_SECONDS = 120
