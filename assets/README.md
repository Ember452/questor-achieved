# Questor 图标源

## 现状（Phase U / B7）

- 本目录仅提供 `icon.svg` 手写占位；**不**交 `icon.ico`（多尺寸 ico 生成推到 Phase U
  之后的下一个小切片）。
- `desktop/electron-builder.yml` 里 `win.icon: ../assets/icon.ico` 指向**未创建**的
  文件；`electron-builder` 缺 ico 时会 `warn cannot execute rcedit ... icon not found`
  但**不阻断构建**，安装产物能正常跑。这是 Phase U 已知的、诚实记录的妥协（per
  AGENTS §一 铁律 1 与 `ADR-0032` §代价）。
- 正式品牌图标设计与多尺寸 `icon.ico` 生成走**另一个小计划**；`icon.svg` 目前是
  最简占位（方形 + `Q`），不代表最终视觉。

## 再生成命令（引入 `icon.ico` 时启用）

参照 `wuu-main/scripts/generate-icon.ts`（同调），从 `icon.svg` 产出多尺寸 `ico`：

```sh
# 一次跑通两条命令即可；`@resvg/resvg-js-cli` 与 `png-to-ico` 都是 npm 上的一次性工具。
npx --yes @resvg/resvg-js-cli assets/icon.svg assets/icon.png --width 1024 --height 1024
npx --yes png-to-ico assets/icon.png > assets/icon.ico
```

生成后把 `assets/icon.ico` 加进 git、`electron-builder.yml` 里 `win.icon` 就已经指对；
`electron-builder` 会用它替换 exe 与 shortcut 的默认图标。

## 与 B7 的关系

- Task B7 的 `feat(desktop): electron-builder Windows NSIS packaging with assets
  placeholder` commit 会随本 README 与 `icon.svg` 一起落；`icon.ico` 缺失的**理由与
  影响面**都记在这里，避免 reviewer 到 `electron-builder.yml` 里看 `win.icon` 时迷路。
