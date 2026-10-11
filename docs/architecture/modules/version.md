# version —— 模块设计篇（M2.1）

状态: 随开工落盘 | 2026-10-11 | 参照: wuu 根 `VERSION` + `internal/version`（设计决定，未搬代码）

## 职责与边界

回答"当前版本是什么"，此外什么都不做。根目录 `VERSION`（CalVer `YYYY.M.D`）是唯一
真相源；pyproject 经 hatchling dynamic 读取（构建产物与文件天然同值），构建标识
（git hash 等）随 M2.3 CLI 收口再定形态，本模块不预置。

## 公共 API

- `questor_version() -> str`：先读已安装分发的元数据；未安装（开发态）回落从
  `__file__` 祖先链定位仓库根的 `VERSION`。两个来源都不可用 → `RuntimeError`，
  绝不猜默认值。

## 取舍

- 包根 `questor.__version__` 用 PEP 562 惰性求值：import 本包不触发版本解析，
  安装损坏只在真正取值时报错。
- 不做版本缓存——解析成本低，进程内多次调用可接受；缓存会让测试与安装态切换更难。

## 对应测试

`tests/unit/test_version.py`（护栏：CalVer 格式、pyproject dynamic 接线、元数据与文件同值；
负向验证记录见该模块 docstring）。
