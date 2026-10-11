"""schemas —— 协议与数据契约（纯 JSON Schema 真相源 + Python 侧 pydantic 绑定）。

JSON 文件是唯一真相源（data-model.md / protocol.md 物化）；本包下的 ``model`` 子模块
只是 data-model.md 的 pydantic v2 绑定，改动契约必须先改文档与 JSON Schema，绑定跟随。
"""

from __future__ import annotations
