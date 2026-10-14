# Phase U 出口记录（Track A + Track B）

> ⚠️ **历史执行记录（2026-10-14 转向）**：其 `[real-terminal]` 步、`npm run package` 产 exe、可干预柱还原度等 pending，随旧代码废弃全部作废（见 `port-ledger` TL-2 / ADR-0044）。不得据此记"有人欠验收"。保留因它是 B-108~B-118 的唯一出处。

日期: 2026-10-13 | 关联: `docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md`、
`docs/plans/development-plan.md` Phase U 行、ADR-0006 / 0030 / 0031 / 0032

## 1. 出口判据对照

Phase U 出口判据（`development-plan.md` §Phase U "出口判据"）：

| # | 判据 | 状态 | 证据 |
|---|---|---|---|
| 1 | 能双击运行的 Electron 壳跑通；`questor serve stdio` 被壳以管道拉起、Review 面板显示真实 diff | 部分 | 拉起与 stdio 通道已在 B3 集成串跑通（`[sidecar] pid=30256 cmd=uv` 观测到）；**双击 + 显示真 diff 属 [real-terminal] 待办清单**（见 §2），需用户手动跑一次并回报 |
| 2 | 可见柱（Review 真 diff）与可干预柱（插话/接管）各有一个 wuu 级还原度的可演示面板 | 部分 | 可见柱 = Review 面板 Track A 完成（A1~A9 全绿）；**可干预柱（插话/接管）还原度未在本相**、推下一切片（gap 见 §4） |
| 3 | 内嵌浏览器真·同页接管 | 不属于本相 | ADR-0030 §结论 3 已限定 U2；本计划覆盖 U0（壳 + 一个高保真纵切片）+ U1 的 Review 部分 |
| 4 | 新面板只能走视图注册表、不改内核（`test_no_hardcoded_panel_case` 绿）；不为界面好看牺牲三柱 | ✅ | Track A 未破此护栏；Track B 未新增面板、仅接 `ui/` 构建产物到桌面壳；A9/B9 都跑该护栏 |

**Track B 出口判据（本次实施计划里 §Phase U（Track B）出口判据）**：

| # | 判据 | 状态 | 证据 |
|---|---|---|---|
| 1 | Electron 壳可双击打开、`serve stdio` 被 `child_process` 以管道拉起、窗口里能看到 Review 面板显示真 diff | 拉起 ✅、真 diff 待 [real-terminal] | B3 split 5/5 观测到 `[sidecar] pid=30256 cmd=uv`；Review diff 呈现依赖 `QUESTOR_MODEL_API_KEY`（本机无、按 M3/M4/M5 同口径记 pending） |
| 2 | `runtime_state.json` 单调 generation + `lifecycle_lock` 用例绿；崩溃重启 fail-open 生效 | ✅ | B4 5 条测绿、B5 5 条测绿；三条负向验证均咬住（详见各 split commit body） |
| 3 | Windows 打包产物可安装、可启动；`desktop.yml` CI 与本地同源 | 部分 | `desktop.yml` + `justfile` + `test_ci_parity.py` 已同步（B8）；打包配置文件就位（B7）、**`npm run package` 拉 GitHub Releases 失败**、需预放 electron zip 到 `%LOCALAPPDATA%/electron-builder/Cache/` 才能产 exe。**另：即便产出 exe，包内只有壳无核**——`extraResources: []`，`questor-core.exe` 不交付（R-10 裁决，Python 打包另开 ADR）；安装后双击 = 壳窗口 + fail-open 无 sidecar，除非设 `QUESTOR_DESKTOP_CORE` env 指向本地开发核 |
| 4 | `test_no_hardcoded_panel_case.py` 与 `test_ci_parity` 全绿 | ✅ | B8 后 parity 覆盖 desktop.yml、`just check` 也含 desktop-test |
| 5 | `development-plan.md` Phase U 勾销；坑目录 B-108~B-118 全部 covered 并附负向验证输出 | ✅ | pitfalls.md 116/118 有效、编号连续、证据可定位；B-103~B-107 在 Track A、B-108~B-118 在 Track B 补入 |

## 2. `[real-terminal]` 待办清单（一次性跑完覆盖 B3~B7）

以下条目需用户在**真终端**（非 Qoder 沙箱 PowerShell，沙箱里 `npm run dev` 会弹"应用程序无法正常启动"）里跑一次，把结果回报，我记录进 B9 完成态。所有条目共用同一份环境准备：

**前置一次性准备**：
1. 确认可达 npm registry（拉 vitest / electron-builder 依赖）；
2. 若需产 exe（§2 步 5）：`mkdir -p $env:LOCALAPPDATA/electron-builder/Cache/`、从 GitHub Releases 或镜像下载 `electron-v44.1.0-win32-x64.zip` 放进去；
3. 可选设 `QUESTOR_MODEL_API_KEY`（跑通真 turn 需要，不设则只跑 fake 场景）。

**一次跑通**（PowerShell）：

```powershell
cd d:\DEVELOP\My-project\questor
$env:QUESTOR_DESKTOP_USE_UV_RUN = "1"

# 步 1：拉起 & 关窗（覆盖 B3 与 B4 观察）
npm --prefix desktop run dev
#   观察 A（B3 Step 11）：主进程控制台出现 `[sidecar] pid=<N> cmd=uv home=<path>`
#   观察 B（B4 Step 8）：另开终端 `ls $env:USERPROFILE\.questor\desktop\`
#     期望 `runtime_state.json` 与 `.lifecycle.lock` 都在；第二次跑前 `.lifecycle.lock` 应消失
#     `cat $env:USERPROFILE\.questor\desktop\runtime_state.json` 里 `generation` 每次 +1、
#     上一版应存在 `runtime_state.json.bak`
#   观察 C（B3 收尾）：关窗后主进程控制台 `[sidecar] exited { code, signal }` 出现

# 步 2：重启 & 断链（覆盖 B5、B6）
# 再跑一次 dev；另开终端 `Get-Process node | Where-Object { $_.Id -ne $PID } | Select-Object Id,ProcessName`
# 找到 sidecar python.exe 或 uv 起的子进程 pid → `Stop-Process -Id <pid> -Force`
#   观察 D（B5 Step 7）：主进程控制台 500 ms 后看到新 `[sidecar] pid=<新 N>`
#     连杀 3 次 → 第 4 次杀后看到 `[sidecar] restart budget exhausted (fail-open), retries=3`
#   观察 E（B6 Step 9）：DevTools Console 里 `window.questorHost.onSidecarState(console.log)`
#     注册后应看到 `{ kind: "down", code, signal, willRetry }` → `{ kind: "up", pid }` 交替、
#     第 4 次 `{ kind: "budget-exhausted", retries: 3 }`
```

**步 3：B7 打包冒烟**（可选，需完成前置 2）

```powershell
npm --prefix desktop run build
npm --prefix desktop run package
# 期望：`desktop/dist/Questor Setup 0.1.0.exe` 大小约 80–120 MB
# 装 exe → 从开始菜单启动 → 环境已设 `QUESTOR_DESKTOP_USE_UV_RUN=1` 时窗口开、
#   sidecar 起、Review 面板显示（若 QUESTOR_MODEL_API_KEY 也配了、能跑真 turn）
# 无 uv 环境时：主进程 `[sidecar] failed to start: questor desktop core is missing` 日志、
#   窗口照开（Electron 壳正常、UI 里 renderer 需展示 sidecar 缺席提示）
```

**步 4：Track A 的浏览器真机走查**（M3~M5 已有类似 pending、本相一并）

```powershell
# 需 `QUESTOR_MODEL_API_KEY` 配置
uv run questor serve http --host 127.0.0.1 --port 8765
# 浏览器打开 http://127.0.0.1:8765、跑一次带写工具的 turn、Review 面板看 diff
```

## 3. 已知观察（记进后续小计划）

- **`[B-119 候选]` Windows 上 vitest 5 的 transform cache 与 pytest 的 bytecode cache 均受 mtime 精度影响**（本项目 B4/B5/B8 负向验证时反复遇到：SearchReplace 改源码后立刻跑测、仍 hit 旧版；`--no-cache` 与 `-p no:cacheprovider` 不完全 bypass；需 `pid`-scoped cacheDir + `sleep 3~5 s` 或 `shutil.rmtree(__pycache__)` 才可靠）。**Phase U 未新占坑号**（AGENTS §二"每个 B-NN 必须对应一个真实存在的测试"、本观察无自动化测可钉）；候选在后续小计划里若拿到可复现证据再补 B-119 与本目录。已在 B4 split 2/5、B5 各 split、B8 split 3/3 的 commit body 与 `docs/notes/2026-10-11-gate-parity.md` §2026-10-13 记录。
- **`electron-builder` 与 B2 的 `electron` 拉二进制走两套不同网络路径**：`electron` npm 用 `%LOCALAPPDATA%/electron/Cache/`、`electron-builder` 用 `%LOCALAPPDATA%/electron-builder/Cache/`；B7 的 yml 已就位但 `npm run package` 需在能拉 zip 或预放 zip 后跑。这条**不是代码 bug**、是 Windows 桌面工具链的常见网络假设，记在这里避免下个读者以为"配置错"。
- **`qst:sidecar-state` IPC channel 无 Phase U 消费方**（B6 R-13 落了 plumbing、renderer 里 `window.questorHost.onSidecarState` API 存在但 `ui/` 里无组件订阅）；护栏 `ipc-parity.test.ts` 咬住 channel 对偶、未来 Phase E 审批 UI 或 `board.tsx` 展示 sidecar 缺席时会加消费点。gap 记在 §4。

## 4. Phase U 未做的 gap（不阻本相勾销）

诚实列出、不假装完成：

1. **可干预柱还原度**（插话/接管面板，wuu 级）：Track B 里 Composer 与 habena 面板沿用 M3/M4 形状、未推 wuu 级；**下一小切片**处理（可参照 wuu `desktop/dev/three-pane/renderer.tsx`、`projects/renderer.tsx`）。
2. **Files / Terminal / Board 面板的 wuu 级还原度**：本相仅覆盖 Review 一例；其他面板另开。
3. **动效体系铺开**：本相只加 Review 用到的 `--motion-*` / `--elevation-*` token；其他面板动效跟各自面板走。
4. **Electron 主进程业务化的红线守住了**（ADR-0030 §触发重评 #2）：Track B 全程未往壳里塞业务判断；若未来某个面板"想给壳加个 if"、按 §七 停下走 ADR。
5. **macOS/Linux 打包**：ADR-0007/structure §7 Windows 第一平台；其他平台另开 ADR。
6. **代码签名**：B7 未做（SmartScreen 提示未消），ADR-0032 §代价 已记。
7. **`window.questorHost` 的 shared types**：`ui/` 与 `desktop/preload` 各持一份 inline 定义（两份 package 独立 lockfile per ADR-0032 §结论 4）；Phase E 若 promote 到 shared package 会另开 ADR。

## 5. 出口结论

**Phase U（Track A + Track B）主体出口判据达成**：

- Track A 面板 wuu 级还原（Review 一例、UI 测 12/12 已销）；
- Track B Electron 壳 Option A 端到端接入（desktop 测 33/33、UI 测 17/17 浏览器路径未破、CI parity 覆盖 desktop 一侧）；
- B-103~B-118 全部 covered、编号连续；
- ADR-0030/0031/0032 与 structure §7 / overview §12 一致。

**pending**（诚实标注、AGENTS §一 铁律 1）：
- 步 1~4 的 `[real-terminal]` 观察结果，需用户回报；
- `npm run package` 产 exe（网络前提）；
- 真 model 端点下的 Turn/Review 端到端（与 M3/M4/M5 同因 `QUESTOR_MODEL_API_KEY` 未配的 pending）；
- 可干预柱还原度与 Electron e2e（推后续小计划）。

## 6. 提交序列索引

Track B 各 Task 已按 `Task B<n> of docs/plans/2026-10-13-phase-u-ui-and-electron-shell.md (split <n>/<total>)` 拆细；`git log --oneline` 顶部即恢复地图。B3 5 段 + B4 5 段 + B5 4 段 + B6 6 段 + B7 2 段 + B8 3 段 + B9 3 段 = 28 段 commit + 每段前的 `docs(plans)` 展开回写 = Phase U 出口。
