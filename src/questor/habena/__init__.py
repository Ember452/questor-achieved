"""habena —— 插话收件箱、排队、接管与暂停、取消传播（overview §6）。

三柱归属：**可干预**的核心通道。插话只在 iteration 起点被消费（B-67/94），接管
走 CAS + revision 栅栏（overview §12 出口判据"接管即停"）。落盘靠 gesta 的
`habena.held_work` 记录，正文 append-only 与索引一致性由 B-45 单点定序守住。

依赖：`engine` `gesta` `schemas`（structure §5）；不 import serve——业务错通过
`ControlError` / 返回值传上来，由 serve 层的 handler 转 `ProtocolError`。
"""

from __future__ import annotations

from questor.habena.control import ControlError, SessionControl
from questor.habena.inbox import HabenaInbox

__all__ = ["ControlError", "HabenaInbox", "SessionControl"]
