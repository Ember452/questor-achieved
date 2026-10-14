"""协议名称注册表 —— initialize.methods 与"有哪些方法/通知"的唯一 Python 侧派生点。

# Reimplements wuu@wuu-main internal/appserver/protocol.go 的 Method*/Notification* 常量集
#   （A 阶段"做"子集，见 docs/research/phase0-wuu-protocol-table.md）。
# pitfalls: B-119（方法表单一来源派生）B-121（声明面 ⊆ 实现且双向）

`tests/architecture/test_protocol_single_source.py` 把本表与 `docs/architecture/protocol.md`
§3/§4 表首列**双向**核对：任一漂移（多一个、少一个、大小写/连字符差）即红。二者同为契约侧
产物，不依赖尚未重写的 `serve` handler，故本护栏在 Phase 1 即可转绿；"实现面 ⊆ 契约面"
由旧 `test_serve_names_are_contracted`（TL-1）守，handler 在 Phase 2a 物化后转绿。
"""

from __future__ import annotations

#: 跨语言接缝的版本串。用户拍板用 Questor 自命名（port-ledger P1-1）；
#: Phase 2b 重建前端时其 protocol 常量须同步为本值，initialize 严格相等不降级（B-60）。
PROTOCOL_VERSION = "questor-app-server/v0.1"

#: 反向 id 前缀（core→client server-initiated 请求），锚 client_calls.go:50 `srv-` + seq。
REVERSE_ID_PREFIX = "srv-"

#: 单帧字节上限，锚 stdio.go:16 `appServerMaxStdioRequestBytes = 64*1024*1024`。
MAX_FRAME_BYTES = 64 * 1024 * 1024

#: client→core 方法名（A 阶段"做"集），**有序**——initialize.methods 按此序派生（B-119）。
METHOD_NAMES: tuple[str, ...] = (
    "initialize",
    "shutdown",
    "thread/start",
    "thread/resume",
    "thread/fork",
    "thread/archive",
    "thread/delete",
    "thread/list",
    "thread/listAll",
    "thread/listArchived",
    "thread/search",
    "thread/pin",
    "thread/rename",
    "thread/preview",
    "thread/regenerate-title",
    "thread/edit-message",
    "thread/compact/start",
    "thread/context-composition",
    "turn/start",
    "turn/interrupt",
    "turn/steer",
    "turn/unsteer",
    "turn/queue",
    "turn/dequeue",
    "turn/requeue",
    "turn/update-queued",
    "run/start",
    "run/interrupt",
    "process/list",
    "process/read",
    "process/write",
    "process/resize",
    "process/stop",
    "activity/list",
    "activity/takeover",
    "activity/release",
    "activity/stop",
    "user-question/hold",
    "user-question/respond",
    "user-question/list",
    "user-question/cancel",
    "config/read",
    "config/model/update",
    "config/advanced/update",
    "config/general/update",
    "config/provider/remove",
    "config/model-catalog/refresh",
    "config/model-catalog/providers",
    "usage/overview",
    "settings/usage",
    "git/commit-message",
    "text/polish",
    "workspace/list",
    "workspace/state/cleanup",
    "sessionFolder/create",
    "sessionFolder/update",
    "sessionFolder/reorder",
    "sessionFolder/delete",
)

#: core→client 反向请求方法（server-initiated，不进 handleLine，走 pending 表；
#: 锚 protocol.go:138-153）。
REVERSE_METHOD_NAMES: tuple[str, ...] = (
    "browser/cdp",
    "browser/screenshot",
    "browser/open_tab",
    "browser/close_tab",
    "browser/set_visibility",
    "browser/list_tabs",
    "browser/turn_ended",
    "browser/finalize",
)

#: core→client 通知名（A 阶段"做"集）。
NOTIFICATION_NAMES: tuple[str, ...] = (
    "thread/started",
    "thread/resumed",
    "thread/updated",
    "turn/started",
    "turn/queued",
    "turn/dequeued",
    "turn/steered",
    "turn/unsteered",
    "turn/held",
    "turn/event",
    "turn/error",
    "turn/completed",
    "turn/usage",
    "run/started",
    "run/updated",
    "item/started",
    "item/completed",
    "item/removed",
    "item/agentMessage/delta",
    "item/agentMessage/replace",
    "item/reasoning/delta",
    "item/reasoning/replace",
    "item/toolCall/delta",
    "item/toolCall/outputDelta",
    "activity/started",
    "activity/updated",
    "activity/control_changed",
    "activity/stopped",
    "browser/turn_started",
    "browser/request_cancelled",
    "user-question/requested",
    "user-question/resolved",
    "config/changed",
    "config/error",
)

#: 错误方言 code 集，须与 protocol.md §7 + envelope 一致（B-56 等）。
ERROR_CODES: tuple[str, ...] = (
    "boundary_denied",
    "authorization_denied",
    "review_blocked",
    "stale_revision",
    "protocol_version_mismatch",
    "unknown_method",
    "invalid_params",
    "internal_error",
)


def initialize_methods() -> tuple[str, ...]:
    """client→core 方法表——由 :data:`METHOD_NAMES` 单一来源派生（B-119）。

    杜绝两处手写字面量漂移。
    """
    return METHOD_NAMES
