"""协议实现（一协议一文件，ADR-0016）。

新协议的落地路径：本目录加一个文件 → 在 :mod:`questor.providers.registry` 的表里登记一行
→ 若需要新的请求字段，先扩 `schemas/llm.py` 的 `ModelRequest`（**不改 ModelPort 签名**）。
"""

from __future__ import annotations

from questor.providers.protocols.anthropic import AnthropicMessagesClient
from questor.providers.protocols.openai_chat import OpenAIChatCompletionsClient

__all__ = ["AnthropicMessagesClient", "OpenAIChatCompletionsClient"]
