// createRequire 的路径锚点：`scripts/gen/types.mjs` 用 createRequire 从这里解析
// json-schema-to-typescript 等 ESM 裸导入解析不到的依赖（Node 从本文件所在目录树往上找
// node_modules，正好落在 ui/）。本文件不参与运行时逻辑，也不 export 任何东西。
// 见 ADR-0019。删掉本文件会让 `just gen` 报 "Cannot find module 'json-schema-to-typescript'"。
