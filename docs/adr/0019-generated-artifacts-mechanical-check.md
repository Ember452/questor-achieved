# ADR-0019 — 生成链的定义点归位与第三方声明生成

状态: accepted
日期: 2026-10-12 | 关联: M2.3 收口 / B-68 B-69 B-70 B-80、`justfile` L28-33、`ci.yml`、
`docs/architecture/structure.md` §6 §9、ADR-0008（门禁范围一致性）

## 前提修正（本 ADR 初稿写错了一句，先按现实改掉）

初稿声称"CI 从不校验生成链、R4 只活在本地"——**这是错的**。实测 `ci.yml`：lint job 已跑
`npm --prefix ui run gen:check`（L50），test job 的 windows leg 再跑一次（L93，专防 B-68），
另有 `gen-check` 本地钩子在 `pre-commit run --all-files`（L54）里跑，且 `npm ci` 排在钩子
之前（B-70 已修）。**R4 的机器守卫已经存在**。

真正缺的两件（本 ADR 的实际范围）：

1. **定义点归属错**：生成器住在 `ui/scripts/gen-types.mjs`，而 `structure.md` §9 把
   "schema → TS 生成、THIRD-PARTY-NOTICES 生成"定在 `scripts/gen/`；
2. **`third_party/THIRD-PARTY-NOTICES` 的生成器完全不存在**（目录也没建），
   `structure.md` §10 已把它列为 M2 交付。

## 结论

1. **唯一实现落 `scripts/gen/`**：`ui/scripts/gen-types.mjs` 搬为 `scripts/gen/types.mjs`
   （逻辑不变，只搬位置）；因为脚本从 `scripts/gen/` 运行时 Node 无法在 `ui/node_modules`
   里解析 `json-schema-to-typescript`，改用
   `createRequire(join(repoRoot, "ui", "noop.js"))` 从 `ui/` 起始路径解析依赖（跳目录不靠
   `NODE_PATH` 这种环境变量魔法）；新增 `scripts/gen/notices.mjs` 生成
   `third_party/licenses/{MIT,BSD-3-Clause,Apache-2.0}.json` 与 `third_party/THIRD-PARTY-NOTICES`；
   `scripts/ci/check_gen.py` 把"重生成→比对→非空即红"收成一个入口。
2. **`justfile` 的 `gen` / `gen-check` 指向新入口**；`ui/package.json` 移除 `gen` / `gen:check`
   脚本（定义点只剩 justfile + scripts，避免两处真相）；`json-schema-to-typescript`
   **留在 `ui/devDependencies`**（依赖声明处即安装处，CI 用 `npm ci --prefix ui`）。
3. **CI lint job 必跑**：新增 `actions/setup-node` + `npm ci --prefix ui` +
   `uv run python scripts/ci/check_gen.py`（依赖缺失时生成步骤直接失败，不再另造一条
   只存于 CI 的断言命令，B-69）；同时把 `check_specs.py` / `check_notes.py` 从 test job 的
   OS 矩阵收进 lint job（核查工具与门禁同类，不该在两个 OS 上各跑一遍）。
4. **`lint` 与 `gen-check` 是两条命令，不能只跑其一**：`just check` 保持两条都在
   （现状已如此），本 ADR 只补 CI 侧的缺位。
5. **B-80 转 covered**：lint job 的 `actions/checkout` 加 `fetch-depth: 0`，并把"浅克隆会让
   `check_notes` 的日期语义失效"这一事实写成可断言的核查（脚本自检：锚点文件历史不足即报
   错而非静默判过期）。

## 理由与取舍

- **定义点归位不是扰民重构**：`just gen`、`gen-check`、CI 与钩子现在都指向 `ui/` 下的脚本，
  而仓库把生成工具登记在 `scripts/gen/`——同一个工具两个家，下一位读者不知道该往哪改。
- **"两边一致"只有被断言时才算存在**：本仓库已为同一课付过三次学费——模块表
  （overview §6 ↔ structure §3）、生成物跨平台复现（B-68）、justfile ↔ CI（B-69）。
- **搬到 `scripts/gen/` 而非在 ui 与 scripts 各留一份**：`structure.md` §9 已把 `scripts/gen/`
  定为"schema → TS 生成、THIRD-PARTY-NOTICES 生成"的家；两份实现必然漂移（B-69 的根因就是
  两处定义）。
- **代价**：CI 的 lint job 要装 npm 依赖（多 30–60 秒）；`npx` 与 workspace 路径在 Windows/Ubuntu
  上的差异需要负向验证（B-79 同族盲区），因此本项必须本地原样跑过再进 CI（B-69 纪律）。

## 被否决的选项

- **只在文档声称"改 schema 记得跑 just gen"**：本轮核对发现这类声称其实已被 CI 覆盖（见
  "前提修正"），但"声称即成立"的推法仍不可信——钩子与 CI 步骤都要能指到具体行号。
- **把生成链写进 npm `prepare` 钩子**：绕过 `just gen` 与 CI 的同一条命令，破坏 parity；
  且生成真相从 justfile 迁进 package.json，出现第二个定义点。
- **复制一份 gen 脚本到 `scripts/gen`**：两个真相源，与上面同罪。
- **在 `pre-commit` 钩子里生成并自动 `git add`**：钩子会改动暂存内容，提交物与作者所见不一致，
  违反"提交只提交我审过的"；现钩子只做 check 报错，保持现状。
- **手写 `third_party/THIRD-PARTY-NOTICES`**：结构 §10 与 wuu 的做法都是"由脚本生成"，
  手写会随依赖变化必然漏项。
- **把 notices 做成运行时 `questor --licenses`**：审计面属仓库合规文件，与 AGENTS §一 的
  可验证柱同源，须可 diff 可追溯，不宜只在运行时可见。

## 适用条件与失效条件

**适用**：M2.3 起所有生成物（前端类型、第三方声明、未来的模型目录）。
**触发重新评审**：① 生成链出现第二个语言宿主（桌面 Rust 需要 JSON schema 绑定）→ 扩
`scripts/gen` 的输入族；② npm 依赖体量导致 CI 明显变慢 → 改用 lockfile 缓存或独立 job，
但"CI 必须跑 gen check"这条不变。
