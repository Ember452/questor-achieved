# ADR-0042 — 协议词表取齐 wuu app-server（关闭 overview §13 未决项 1）

状态: accepted
日期: 2026-10-14 | 关联: 关闭 `overview.md` §13 未决项1、取代 `protocol.md` 现自研方法名、联动 C4/C8/C9/C19、护栏 `test_serve_names_are_contracted`、`docs/research/phase0-wuu-protocol-table.md`

## 结论

`protocol.md` 的方法/通知词表**全部取齐 wuu 实测**（见 `phase0-wuu-protocol-table.md`：约 126 方法常量、约 40 通知，A 阶段"做"约 60 方法 + 33 通知）。词表同源点：`thread/start`（非 `thread/create`）、`turn/steer|queue|requeue`、`run/updated`（非 `run/status`）、`item/*/delta|replace`、`process/*`、`browser/*` 反向 8、`activity/*`、`user-question/*`。传输 = **stdio JSONL 单一通道、64MiB 帧、snake_case、反向 `srv-` 前缀 id**。旧自研命名一律废弃。

## 理由与取舍

- app-server 协议是"前端吃 wuu 形态 + Python 后端"的**唯一跨语言接缝**，词表不同源 = 两套真相 = 前端解析断裂。
- 取舍：Questor 早期自研的动词命名作废，一切以 wuu 实际序列化的 JSON 为准（Phase 1 用 fixture 回放钉死）。

## 被否决的选项

- **保留自研词表 + adapter 映射 wuu**：多一层、前端仍要改、漂移面更大。
- **自研 REST/HTTP 面**：弃 stdio 帧优势与 wuu 前端可复用性。

## 适用条件与失效条件

**适用**：A 阶段移植的方法/通知族。**触发重评审**：wuu 协议加性演进（新族）→ 按 ADR-0028 加性跟进；C19（`approval/request` per-command 弹窗）按 wuu 的 `approve_for_me` 收紧型实测对表后再定。
