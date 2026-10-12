"""LLM wire 词汇表：engine ↔ providers ↔ context 的**进程内共享形状**（纯类型，无业务依赖）。

为什么住 `schemas`：`providers` 依矩阵不得 import 任何业务模块（structure §5），而
`ModelPort` 的参数与返回形状必须被两侧共同看到——放在无依赖层，port 才能留在内核
（R1：内核定义接口，providers 注册实现），否则 providers 要么反向依赖 engine，要么
各处自造一套同形类型（两处真相）。

**边界说明**：本模块不是跨进程契约。跨进程的实体与事件形状仍由 `model/v1.json` +
`app_server/v0-1.json` 承载（真相源），这里的形状改了不必然要升契约版本；两者一旦
出现语义分歧，以契约文档为准并当场回写（AGENTS §七）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

__all__ = [
    "CHARS_PER_TOKEN",
    "LLMUsage",
    "Message",
    "ModelCapabilities",
    "ModelRequest",
    "PromptAssembly",
    "PromptBlock",
    "PromptBlockKind",
    "Role",
    "STABLE_PROMPT_BLOCK_ORDER",
    "StreamDelta",
    "StreamEnd",
    "StreamEvent",
    "StreamThinking",
    "StreamToolCall",
    "ToolCall",
    "ToolResultBlock",
    "VOLATILE_PROMPT_BLOCK_KINDS",
    "WindowSource",
    "estimate_tokens",
]

#: 字符→token 的启发式换算（锚点后的尾部估算用）。住在共享层是因为
#: `engine`（循环/预算）与 `context`（压缩阈值）必须用同一个数——各自一份会让
#: 两侧对"窗口占了多少"得出不同结论（B-28）。
CHARS_PER_TOKEN = 3.5

Role = Literal["user", "assistant"]


class WindowSource(StrEnum):
    """窗口/上限数值的来源——可观测面必须能区分"配置给的"与"保守兜底"（B-82）。"""

    CONFIG = "config"
    DECLARED = "declared"
    CONSERVATIVE = "conservative"


@dataclass(frozen=True)
class ModelCapabilities:
    """一个端点的能力声明：随 `initialize` 回显、随 context 算预算。

    ``window_source`` 不是装饰——它告诉上层这个窗口数是配置给的还是猜的下界。
    """

    context_window: int
    max_output_tokens: int
    supports_thinking: bool
    supports_prompt_cache: bool
    window_source: WindowSource


class PromptBlockKind(StrEnum):
    """system 提示词的块类别（形状参照 wuu `internal/context/context.go#L66-L80` 的
    ``BlockKind``，重写实现；ADR-0018）。

    只列有真实消费者的类别；``task_state`` / ``memory`` / ``skill_index`` 随各自模块
    物化时加入（同一稳定归属判据），不预先声明无消费者的枚举。
    """

    AGENT_IDENTITY = "agent_identity"
    QUESTOR_RULES = "questor_rules"
    PROJECT_RULES = "project_rules"
    TOOL_POLICY = "tool_policy"
    TOOL_INVENTORY = "tool_inventory"
    SUMMARY_PROTOCOL = "summary_protocol"
    ENVIRONMENT = "environment"


#: 随会话/调用而变的类别——绝不能进缓存前缀（cwd、日期、权限档位都会变）
VOLATILE_PROMPT_BLOCK_KINDS = frozenset({PromptBlockKind.ENVIRONMENT})

#: 稳定块的固定顺序（装配点与压缩重注入共用同一顺序，防同义不同序）
STABLE_PROMPT_BLOCK_ORDER = (
    PromptBlockKind.AGENT_IDENTITY,
    PromptBlockKind.QUESTOR_RULES,
    PromptBlockKind.PROJECT_RULES,
    PromptBlockKind.TOOL_POLICY,
    PromptBlockKind.TOOL_INVENTORY,
)


@dataclass(frozen=True)
class PromptBlock:
    """一个提示词块。``stable`` 由 ``kind`` 推导，调用方不能自报——防止把易变内容谎标成
    稳定以套缓存（那会让缓存前缀里坐着会变的字节，比不缓存更糟）。
    """

    kind: PromptBlockKind
    text: str

    @property
    def stable(self) -> bool:
        return self.kind not in VOLATILE_PROMPT_BLOCK_KINDS


@dataclass(frozen=True)
class PromptAssembly:
    """装配好的 system 块序列 + 缓存边界：``blocks[:cache_boundary]`` 全为稳定块。

    构造即冻结；provider 与压缩重注入都只读它（装配行为在 :func:`questor.prompts.assemble`）。
    """

    blocks: tuple[PromptBlock, ...]
    cache_boundary: int

    @property
    def cacheable(self) -> tuple[PromptBlock, ...]:
        """可进缓存前缀的块（协议支持时按其中末块打缓存断点）。"""
        return self.blocks[: self.cache_boundary]

    @property
    def text(self) -> str:
        """全量拼接（供不支持缓存断点的协议使用）。"""
        return "\n\n".join(block.text for block in self.blocks)


@dataclass(frozen=True)
class ToolCall:
    """模型发起的一次工具调用（会话历史的组成部分，wire 侧同一形状）。"""

    id: str
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ToolResultBlock:
    """回喂模型的工具结果。``content`` 是**会话内表示**（可能已被 context 替换）。"""

    tool_use_id: str
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class Message:
    """一条会话消息。

    为何 frozen：B-25 要求"替换决策绝不 mutate 原始对话"——把消息做成不可变的，
    这条纪律就由类型兼管，而不是只靠约定与评审；替换走
    :func:`dataclasses.replace` 产生新对象，原历史保持可审计（重放时仍是对话原文）。
    """

    role: Role
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResultBlock] = field(default_factory=list)


@dataclass(frozen=True)
class StreamDelta:
    """正文增量（传输态，不落盘——正文真相是 message Item）。"""

    text: str


@dataclass(frozen=True)
class StreamThinking:
    """推理增量。可见柱要求过程可摊开，故独立成事件而不是混进正文（M2.3）。"""

    text: str


@dataclass(frozen=True)
class StreamToolCall:
    """一个**完整**的工具调用（args 分片由 provider 内部聚合后产出，M2.2 粒度）。"""

    call: ToolCall


@dataclass(frozen=True)
class LLMUsage:
    """一次调用的用量。cache/reasoning 分量必须单独携带：只报 input/output 会让
    成本与缓存收益两头都算不清（providers 侧的接口面，成本治理属后续功能面）。
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_creation: int = 0
    reasoning_tokens: int = 0

    def total_input(self) -> int:
        """窗口占用意义上的输入：缓存命中与缓存新建都占上下文。

        只算 ``input_tokens`` 会让压缩阈值永远晚于真实压力（B-28）。
        """
        return self.input_tokens + self.cache_read + self.cache_creation


@dataclass(frozen=True)
class StreamEnd:
    """流终局：停止原因 + 用量。"""

    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens" | "error" | ...
    usage: LLMUsage = field(default_factory=LLMUsage)


StreamEvent = StreamDelta | StreamThinking | StreamToolCall | StreamEnd


def estimate_tokens(messages: list[Message]) -> int:
    """字符估算（只用于真实用量锚点之后的尾部；B-28）。"""
    chars = sum(len(message.content) for message in messages)
    return int(chars / CHARS_PER_TOKEN)


@dataclass(frozen=True)
class ModelRequest:
    """一次模型调用的全部输入（port 的参数对象——新增字段不再改方法签名）。

    ``tools`` 沿用工具层既有约定：每项是 ``tools/base.Tool.schema()`` 产出的 **anthropic
    形态平铺 dict**（``name`` / ``description`` / ``input_schema``），provider 侧按自家协议
    包装。把它抽成显式 ``ToolSchema`` 模型会牵动 tools/limen/executor 三处，属独立重构，
    不在 M2.3 顺带做（留痕见 development-plan M2.3 实际结果）。
    """

    messages: list[Message]
    prompt: PromptAssembly
    #: 本次调用的输出上限。故意不给默认值：上限是预算的一部分，必须由调用方显式
    #: 给出（内核持有），而不是藏在客户端对象里——否则同一个数会有两处真相（B-08）。
    max_output_tokens: int
    tools: list[dict[str, Any]] = field(default_factory=list)
    thinking: bool = False
