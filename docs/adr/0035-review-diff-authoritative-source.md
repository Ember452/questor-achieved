# ADR-0035 — Review 的 diff 权威源：真 git diff 与工具时刻 diff 的分工

状态: proposed（待用户裁决；本 ADR 只裁决"谁是权威源"，不改代码）
日期: 2026-10-13 | 关联: `review/diff.py`、ADR-0031（@pierre/diffs）、ADR-0030、
`protocol.md` §3 `review/turn_diff`、overview §1"可见"柱、`AGENTS.md` §三

## 问题（实测）

`review/diff.py` 的模块注释第一句就写明：**"只吃 old_text / new_text，不看盘、不看
git"**，由 `write` / `edit` 工具在 `execute` 里调用，调用方负责把结果塞进
`ToolResult.data["diff"]` 与 `Item.payload`。

由此推出的采集盲区（不是猜测，是该设计的直接后果）：

1. `run` 工具里发生的文件变更（`black` / `ruff --fix` / `git apply` / `npm` 脚本 /
   测试自己写盘的 fixture）**一条 diff 都没有**；
2. 用户在编辑器里手改的文件、`process` 后台进程写的文件，同样没有；
3. 落盘的只有"agent 声明要改什么"，不是"世界实际变成了什么"。

而 Phase U Track A 已经按 ADR-0031 把 `@pierre/diffs` 的双栏渲染、折叠、
100+ hunks 收起都做完（`ui/src/panels/review.tsx`），项目定位又明写
"Review 显示**真实 git diff**"（wuu 提供的"过程可见"能力）。
**渲染面在往一个数据源残缺的管道上加保真度。**

## 候选方案

**A. 以真 git 为权威源（推荐）**
turn 收尾时对 workspace 采一次 `git diff`（含 untracked 的 add -N 或显式枚举），
落一条与工具时刻 diff **不同类型**的记录；`review/turn_diff` 默认返回这一条。
工具时刻 diff 降级为"意图审计"（agent 说要改 X，实际改了 X+Y 就是可展示的差异）。

**B. 承认边界，UI 如实标注**
Review 面板明写"仅显示 agent 文件工具的改动"。满足诚实，但把"可见"柱降级成
"部分可见"，与定位冲突。

**C. 内容快照基线（不依赖 git）**
turn 开始记录 workspace 内容哈希树，结束对比得出变更集。支持非 git 目录，
代价是大目录扫描成本与忽略规则维护（`SKIP_DIRS` 已有一份，但那是工具遍历用的，不是快照用的）。

推荐 **A 为主 + C 作为"非 git 工作区"的退化路径**；B 不可接受（定位即"真实 diff"）。

## 理由与取舍

- **为什么必须现在裁、不能边写边定**：一旦引入第二种 diff 来源，
  `Item.payload` 里就会同时存在两种语义的 `diff` 键，而 `ToolResult.data` 现在是
  `dict[str, object]`（无类型约束），历史数据无法回填区分——这正是 AGENTS §三
  禁止的"同一事实两套真相"。裁决晚于实现，就得写迁移脚本猜历史。
- **需要动的接口面**（按横切规则 7，接口面必须与内核同期定）：
  `protocol.md` §3 `review/turn_diff` 的返回形状、`schemas/app_server/v0-1.json`
  对应 `$defs`、`just gen` 重新生成 d.ts。协议是加性演进（ADR-0028），加字段不升版本，
  但**语义换源不是加字段**，需要明确写清 `source` 判别位。
- **代价**：turn 收尾多一次 git 调用（持锁窗口外的短操作，参照 worktree 的
  `asyncio.to_thread` 先例）；untracked 文件要决定进不进 diff（`add -N` 会把
  未跟踪文件变成 diff 可见，但也可能把构建产物扫进来——需要与 `.gitignore` 对齐的策略）。
- **为什么不现在写码**：① 权威源未裁就写会造双真相（上面第一条）；② 排期上 U2
  （Electron 内嵌浏览器真接管）是 ADR-0030 选 Electron 的核心收益兑现点，优先级在前。

## 被否决的选项

- **让 `run` 工具自己在执行前后采 diff**：只有被 run 的那条命令知道的改动范围，
  覆盖面仍是猜的（命令可以改任意路径），且每条命令多一倍扫描；本质是把权威源
  继续放在"agent 的自述"上。
- **保持现状 + 文档写明盲区**：文档改了不改变用户看到假完成的事实——看板说
  "本轮改了 3 个文件"而工作区实际变了 9 个。
- **用 pygit2 / gitpython 代替 CLI**：多引一个原生或纯 Python 依赖（需另开 ADR，
  见依赖纪律），而 `worktree/` 已确立"subprocess 调 git CLI、不引 pygit2"的口径，
  同一件事该用同一种方式。

## 适用条件与失效条件

**适用**：从裁决定案起，Review 面板与验收证据（evidence）都以 git 侧为真值。

**触发重新评审**：
1. 工作区不是 git 仓库的比例明显上升（个人项目里非 git 目录常见）→ 提前启用 C 方案；
2. `review/turn_diff` 需要跨 worktree 分叉呈现（fork 后两条线的 diff 归属）；
3. 引入容器/远程执行环境（M8 `containers/`）后，"workspace"不再是本地目录，
   git 采集点必须随执行环境一起搬。
