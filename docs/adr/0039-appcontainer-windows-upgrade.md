# ADR-0039 — AppContainer 列为 Windows 写隔离后期升级路径（改判 ADR-0007 被否决项）

状态: accepted
日期: 2026-10-14 | 关联: 改判 ADR-0007「被否决的选项·AppContainer」走其失效条件①、`overview.md` §9 §10、计划 §1/§1.6

## 结论

维持 ADR-0007 的三层现状（**limen 路径门 + Job Object 进程树管理 + 敏感路径守卫**、standard 档无 OS 写隔离**如实标注**）为 A 阶段现实；但把 **AppContainer** 从"直接否决"改判为 **Phase 4 之后的可选写隔离升级路径**：`Policy{Mode,WritableRoots}` → 受限 capability SID → 仅在 WritableRoots 授 ACL → `CreateProcess` 带 `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITY`；用 pywin32/ctypes FFI，照 wuu `processsandbox.Provider` seam 让后端可插拔、`passthrough` 与 `sandboxed` 始终回报。**仍不引 Docker Desktop 为默认**。

## 理由与取舍

- ADR-0007 失效条件①（"出现对开发工具链友好、可脚本化的 Windows OS 沙箱原语"）+ 用户明确"不焊死、后期可能加"，触发本改判。
- AppContainer 是 Seatbelt/Landlock 在 Windows 上的最近对应物（逐进程、路径作用域写拒绝），比 wuu 现状（Windows 直接 ErrUnavailable）更强。
- 取舍：不现在做（拖慢 A 阶段可用），只"保住 seam、别焊死"，落地排到 Phase 4 之后。

## 被否决的选项

- **现在就上 AppContainer**：干扰主链稳定性与"可用优先"。
- **Docker Desktop 担当 standard 默认**：重、破坏"同一可见工作区"、给个人工具塞重依赖（沿用 0007 结论）。

## 适用条件与失效条件

**适用**：Windows 第一平台、A 阶段先逻辑边界。**触发重评审**：若 AppContainer 实测在目标用户工具链大面积损坏（默认断网/管道重定向破坏 CLI），退回"仅逻辑边界 + 文档标注"，本 ADR 标 withdrawn。
