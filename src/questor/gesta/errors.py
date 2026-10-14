"""gesta 存储层错误族（单一来源：所有会话库写路径只抛这些）。

设计约束：调用方要能**分清"业务性拒绝"与"库坏了"**——前者是产品语义（会话不存在、
控制态变了、插话形状不合法），后者要上浮成用户可见的存储错误，绝不能被当成"没找到"
静默吞掉（B-100 型教训：脏数据漏裸 ``KeyError`` 会让新旧实现口径不一致）。

# Ported from wuu@2026.10.6 internal/session/session.go（ErrSessionNotFound 族）、
# internal/session/inbox.go（ErrControlChanged）、internal/session/held_user_work.go
# （参数校验的 errors.New）——只对齐错误语义与分类，未搬码。
"""

from __future__ import annotations


class GestaError(RuntimeError):
    """gesta 存储层的错误基类；调用方据此区分"库的问题"与其他故障。"""


class SessionNotFound(GestaError):
    """会话不存在（对齐 wuu ``ErrSessionNotFound``）。

    注意与"库里有历史但没有会话行"区分：后者是数据损坏，走 :class:`StoreCorrupted`，
    不得伪装成"没找到"让上层安心继续。
    """


class SessionExists(GestaError):
    """同 id 会话已存在（创建路径拒绝静默覆盖历史）。"""


class SessionBusy(GestaError):
    """会话仍在执行中，拒绝删除/归档（``thread/delete`` 的"需 idle"前置，protocol.md §3）。"""


class ControlChanged(GestaError):
    """插话的控制栅栏已失效（对齐 wuu ``ErrControlChanged``）。

    入队时判一次不够：sender 可能在 hook 跑完前被接管，消费时必须复判
    ``session_controls`` 的 manager/revision/state（B-129）。
    """


class InboxInvalid(GestaError):
    """插话入队前置校验失败（缺 client_id / session_id）。

    这两个 id 是幂等判据本身，为空时 ``INSERT OR IGNORE`` 会把所有消息折叠成同一行，
    静默丢输入——必须显式拒绝（wuu inbox.go L49-51 同调）。
    """


class HeldWorkInvalid(GestaError):
    """未决工作形状不合法：缺 id / 缺正文或运行时 JSON / origin 不在 ``queue|steer`` 值域。"""


class ControlInvalid(GestaError):
    """控制态写入不合法：``state`` 不在单点值域内（防接管栅栏写进脏值）。"""


class StoreCorrupted(GestaError):
    """库内记录不自洽（缺列、坏 JSON、fold 不上）。"""


class RevisionConflict(GestaError):
    """修订号不匹配（乐观并发拒丢更新，ADR-0005；对齐 ``stale_revision`` 错误方言）。"""


class SequenceRejected(GestaError):
    """调用方自带 seq 被拒：seq 只能由 store 在追加事务内取号（B-45 单点分配）。"""
