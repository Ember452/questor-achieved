# tests/contract

本目录承载**两类**契约测试，共同点是"跨实现/跨语言的对账基线"，彼此独立：

## 一、app-server 协议帧契约（Phase 1 已落地）· `test_replay_wuu_frames.py`

把「Electron 前端吃 wuu app-server 协议 + Python 后端」这道唯一跨语言接缝用**帧回放**钉死。
wuu 协议**无代码生成**（TS/Go/Python 三份并行、会漂移），本套件是弥补该漂移的唯一防线
（`protocol.md` §8、`docs/research/behavior-protocol-wuu.md` §5）。

- **基准帧来源**（本机无 Go，不靠实跑，§1.5 机制 2 软模式）：
  - **真实 golden**：wuu `_test.go` 里写死的期望 JSON，逐字取入 `fixtures/`：
    - `fixtures/wuu_initialize_request.json` ← `internal/appserver/client_calls_test.go:60`
    - `fixtures/wuu_reverse_response.json` ← `internal/appserver/client_calls_test.go:89`
  - **手写期望帧**：逐方法读 `internal/appserver/protocol.go` 结构体、核对其 `json` tag 后按形状
    手打（测试内附 wuu 行号锚点）。**线格式真相 = Go tag**，TS `packages/protocol/src/index.ts` 会漂移。
- **断言**：initialize + thread/turn/run/item 四族逐字段一致（键名/类型/可选性）；含硬语义
  `Turn.items` nil→`[]`（P1-3）、`Origin≠Role`、Provider 凭据 `extra=forbid` 拒（P1-4）、
  `srv-` 反向 id（B-59）、版本严格相等不降级（B-60）。
- **负向验证**：把某帧键改 camelCase 或塞未知键 → 模型必须 `ValidationError`（证明会咬人）。
- **单一来源护栏**（同目录外，`tests/architecture/test_protocol_single_source.py`）：
  `protocol.md` §3/§4/§7 ↔ `schemas/app_server/names.py` 双向同源；`schemas/app_server/` 是 A 阶段
  线契约形状的 Python 侧唯一定义点。

## 二、引擎行为契约（M6 落地，ADR-0033）

所有引擎跑**同一套行为契约测试**（`overview.md` §11）：参数化对象 = 内置引擎 + 各外部适配器
（ACP / Claude / Codex）。断言 turn 生命周期与事件顺序、插话只在步前边界消费（B-67）、接管即停、
`stop`/`resume`/`fork` 可观察语义、能力缺口显式报错不静默忽略。**此项尚未落地**——`engine/contract/`
提取（ADR-0033）是 M6 开工准入条件；在此之前该子集收集 0 条属预期。

## 运行

`just` 的 `test`/`arch` 配方覆盖本目录（协议帧契约已入 `just check`）。
