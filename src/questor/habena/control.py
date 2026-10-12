"""接管栅栏：CAS + revision，stale 进程不能撤销人的接管（overview §12）。

holder 只有两态：`agent` 与 `user`。用户 take_over → holder=user；release 交回 agent。
每次操作递增 revision，客户端提交时带 `expected_revision` 做 CAS——不匹配即
`ControlError("stale_revision")`，由 serve 层转 ProtocolError 回客户端（对应
protocol.md §7 的错误方言）。

`pause` 只递增 revision 不切 holder——它表达"用户按了暂停、engine 下一步该看
`is_paused` 决定是否 yield waiting"；M3a-3 只落形状，pause 的 engine 侧消费点
随 M4 长跑/编排一起做。
"""

from __future__ import annotations

from dataclasses import dataclass


class ControlError(Exception):
    """接管栅栏失败（stale revision / 未持有 / 已终态）。serve handler 转 ProtocolError。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ControlState:
    """当前控制状态；revision 单调递增。"""

    holder: str = "agent"
    revision: int = 0
    paused: bool = False


class SessionControl:
    """一个线程的控制栅栏（holder + CAS revision）。"""

    def __init__(self) -> None:
        self._state = ControlState()

    @property
    def state(self) -> ControlState:
        return self._state

    @property
    def is_taken_over(self) -> bool:
        return self._state.holder == "user"

    def _check_cas(self, expected_revision: int | None) -> None:
        if expected_revision is not None and expected_revision != self._state.revision:
            raise ControlError(
                "stale_revision",
                f"expected_revision={expected_revision} 不匹配当前 {self._state.revision}",
            )

    def take_over(self, expected_revision: int | None = None) -> ControlState:
        """用户接管（agent→user）；stale 的接管请求被拒，防旧 UI 撤销新接管。"""
        self._check_cas(expected_revision)
        self._state = ControlState(
            holder="user", revision=self._state.revision + 1, paused=self._state.paused
        )
        return self._state

    def pause(self, expected_revision: int | None = None) -> ControlState:
        """暂停（不切 holder）；M4 长跑里 engine 消费点在 iteration 起点看 paused。"""
        self._check_cas(expected_revision)
        self._state = ControlState(
            holder=self._state.holder, revision=self._state.revision + 1, paused=True
        )
        return self._state

    def release(self, expected_revision: int | None = None) -> ControlState:
        """用户交回控制权（user→agent）；当前不是 user 时拒（防 stale 撤销）。"""
        self._check_cas(expected_revision)
        if self._state.holder != "user":
            raise ControlError(
                "invalid_params",
                "当前 holder 不是 user，release 无效",
            )
        self._state = ControlState(holder="agent", revision=self._state.revision + 1, paused=False)
        return self._state
