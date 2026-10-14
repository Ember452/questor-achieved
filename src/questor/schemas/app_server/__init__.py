"""app_server —— app-server 协议契约（跨语言接缝的单一来源，protocol.md 物化）。

# Reimplements wuu@wuu-main internal/appserver/{protocol.go,stdio.go,config_handlers.go}
#   的线契约层（信封 / initialize / thread·turn·run·item 四族形状）——以 Go json tag 为准，
#   未搬代码、逐符号差异记 docs/research/port-ledger.md。
# pitfalls: B-59 B-60 B-61 B-62 B-63 B-64 B-65 B-66 B-119 B-121

本包是 **A 阶段契约形状的唯一 Python 侧定义点**：`names.py` 的 METHOD/NOTIFICATION 注册表
派生 `initialize.methods`，并被 `tests/architecture/test_protocol_single_source.py` 与
`protocol.md` 双向核对（B-119 方法表派生 / B-121 声明面 ⊆ 实现且双向）。

注：旧的 ``schemas/app_server/v0-1.json`` + ``scripts/gen`` 生成链原服务已废弃的 ``ui/``
（ADR-0040）；Phase 1 起线契约以本包 pydantic 模型为单一来源，旧路线随 Phase 2a handler
重写作废（port-ledger 已登记，非静默并存）。
"""

from __future__ import annotations
