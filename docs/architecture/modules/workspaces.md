# workspaces —— 模块设计篇（M2.1）

状态: 随开工落盘 | 2026-10-11 | 参照: wuu `internal/workspaces`（语义，未搬代码）

## 职责与边界

工作区注册（canonical root → sha256[:16] 为 id，状态目录 `<slug>-<hash16>`）、
登记增删查、路径可见性判定 `is_within_workspace`（M2.2 limen 可达性推导的直接输入）。

## 身份与可见性

- id = canonical root 的哈希前缀：符号链接别名与 Windows 大小写变体注册出**同一**
  身份，不引入第二套 id；`workspace_dir_name` 复用 `state.paths` 的 slug-hash16。
- 可见性 = canonical resolve + `os.path.normcase`（Windows 折叠）+ 分隔符边界比较：
  `my-proj-evil` 不是 `my-proj` 内部；`..` 与符号链接在 resolve 阶段消化；
  未存在的路径同样可判（可达性推导不要求文件已存在）。
- `unregister` 只删 `~/.questor` 内的登记，**永不触碰工作区内文件**。
- 修订号 `revision` 本阶段恒 0；递增语义随 M3 review（ADR-0005）落地。

## 对应测试

`tests/unit/test_workspaces.py`（幂等与同源身份、大小写/符号链接归一、
改名、增删查、可见性边界与多根）。
