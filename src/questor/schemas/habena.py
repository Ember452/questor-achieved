"""habena 记录形状（跨模块数据经 schemas 承载，与 `context.replacements` 同层）。

`SteerMessage` 是会话正文 `habena.held_work` 记录与队列的共用形状；gesta fold 与
habena.Inbox 都从本模块取。放 schemas 而非 habena 内部是因为依赖方向：gesta 只能
import schemas/state/config，不能反向 import habena（structure §5）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SteerMessage(BaseModel):
    """插话/排队消息（held_user_work 双 origin，B-65）。

    `client_id` 是幂等键（B-63）：同 id 提交两次只入队一次；`expected_turn_id`
    空则旧客户端兼容放行，非空不匹配当前 turn 拒（B-64）。`turn_id` 记录消息挂
    到哪一轮（steered 消息不新开 turn，落原 turn 序列）。
    """

    model_config = ConfigDict(frozen=True)

    thread_id: str = Field(min_length=1)
    client_id: str = Field(min_length=1)
    origin: Literal["queue", "steer"]
    content: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    turn_id: str | None = None
    expected_turn_id: str | None = None
