# ADR-0040 — 前端归属改判：渲染层回归 desktop/src/renderer，废弃独立 ui/

状态: accepted
日期: 2026-10-14 | 关联: 取代 ADR-0006 结论2、ADR-0030 结论4、ADR-0032 结论3/4；连带撤销"Electron 渲染层复用 ui 源码"规范；`docs/research/phase0-wuu-renderer-assembly.md`

## 结论

照 wuu 形态重搭前端：**渲染层住 `desktop/src/renderer/`**、共享客户端归 `clients/core` 等价物、契约归 `packages/protocol` 等价物（**由 Python `schemas/` 生成 TS**，弥补 wuu"无代码生成"缺陷）；**废弃独立 `ui/` 包**。双宿主（网页）后期按 wuu mobile-web「同一 renderer 换传输」的方式评估，不为其预建 `ui/`。依赖选型回到 wuu 实测集（Monaco 做 diff/编辑器、@xterm 终端、react-markdown、@pierre/trees），撤销 `ui/` 的 zustand/@pierre/diffs/@xyflow/shiki。

## 理由与取舍

- 用户明确"现有前端界面是乱的、代码不留、界面/动效照 wuu"；照 wuu 结构重搭是复用已趟平的前端形态，不再自造一套 UI。
- 实测：wuu 渲染层不 import Go、传输无关协议驱动 → 挂 Python 后端可行（`WUU_DESKTOP_CORE` 式钩子）。
- 取舍：`ui/` 已有代码废弃（知识在 `docs/research` + pitfalls 留存）；连带重裁 ADR-0031（@pierre/diffs 选型）。

## 被否决的选项

- **保留 ui/ 为唯一前端源、双宿主共用**：与母本形态相反，复用 wuu 前端时会一直别扭。
- **现在就做 web 宿主**：YAGNI；桌面 exe 先行。

## 适用条件与失效条件

**适用**：Electron 桌面壳为第一交付形态。**触发重评审**：若 wuu renderer 某面板深度绑定 Go 特有协议字段 → 该面板单独重设计并记 `port-ledger`。
