"""schemas —— 协议与数据契约（真相源 + Python 侧 pydantic 绑定）。

分两类，各有所本，不混用：
- **data-model 类**（`model/v1.json` 等）：JSON Schema 仍是唯一真相源，`model` 子模块只是
  data-model.md 的 pydantic 绑定；改契约先改文档与 JSON Schema，绑定跟随。
- **app_server 协议类**（`app_server/`）：Phase 1 起以本目录 pydantic 模型 + `names.py` 为
  A 阶段线契约的**目标单一来源**；旧 `v0-1.json` + `scripts/gen` 生成链属过渡期旧世界，
  随 Phase 2a handler 重写同批推倒（port-ledger 逐条登记）。改 app_server 契约先改
  `protocol.md`+`names.py`+模型，三处同源。
"""

from __future__ import annotations
