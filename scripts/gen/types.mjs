// 由 ADR-0019 归位的 schema → TypeScript 生成器（定义点唯一：scripts/gen/）。
// 用法：node scripts/gen/types.mjs [--check]
//   默认：原位重生成 ui/src/rpc/generated/*.d.ts
//   --check：生成后断言 `git diff --exit-code -- ui/src/rpc/generated`（CI 与 just gen-check 同源）
// 真相源：src/questor/schemas/{model,app_server}/*.json（纯 JSON Schema）。
//
// json-schema-to-typescript 依赖装在 ui/devDependencies（ADR-0019：依赖声明处即安装处）；
// 从 scripts/gen/ 运行时 Node 无法在 ui/node_modules 里解析 ESM 裸导入，改用 createRequire
// 从 ui/ 起始路径解析（跳目录不靠 NODE_PATH 这种环境变量魔法）。ui/noop.js 是解析锚点。

import { createRequire } from "node:module";
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join, dirname, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const genDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(genDir, "..", "..");
const schemaRoot = join(repoRoot, "src", "questor", "schemas");
const uiRoot = join(repoRoot, "ui");
const outDir = join(uiRoot, "src", "rpc", "generated");
const check = process.argv.includes("--check");

const require = createRequire(join(uiRoot, "noop.js"));
const { compile } = require("json-schema-to-typescript");

function collectSchemas(dir, prefix = "") {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...collectSchemas(full, `${prefix}${entry.name}-`));
    else if (entry.name.endsWith(".json"))
      out.push({ name: `${prefix}${entry.name.replace(/\.json$/, "")}`, full });
  }
  return out;
}

mkdirSync(outDir, { recursive: true });

for (const { name, full } of collectSchemas(schemaRoot)) {
  const schema = JSON.parse(readFileSync(full, "utf-8"));
  // banner 里的路径必须跨平台一致：path.relative() 在 Windows 返回 `src\questor\...`、
  // 在 Linux 返回 `src/questor/...`，而 banner 会被写进 .d.ts——不规范化则生成物
  // 不可复现，CI 的 gen:check 必然报漂移（B-68）。
  const schemaRef = relative(repoRoot, full).split(sep).join("/");
  const ts = await compile(schema, schema.title ?? name, {
    bannerComment: `/* 由 src/questor/schemas 生成（${schemaRef}）。禁止手写编辑——改动走 schema 与契约文档。 */`,
    additionalProperties: false,
    enableConstEnums: true,
    // M3a-1：把 $defs 里的每个方法族形状都 export，UI 才能拿到严格类型；
    // 不设 true 时 json-schema-to-typescript 只 export 顶层引用的定义，未直接
    // 引用的 <Method>Params / <Method>Notification 会被丢弃（B-98 复现路径）。
    declareExternallyReferenced: true,
    unreachableDefinitions: true,
  });
  const outFile = join(outDir, `${name}.d.ts`);
  writeFileSync(outFile, ts, "utf-8");
  console.log(`generated: src/rpc/generated/${name}.d.ts`);
}

if (check) {
  try {
    execFileSync("git", ["diff", "--exit-code", "--", "ui/src/rpc/generated"], {
      cwd: repoRoot,
      stdio: "pipe",
    });
    console.log("gen-check: generated types are up to date");
  } catch {
    console.error(
      "gen-check FAILED: generated types drifted from schemas. Run `just gen` and commit.",
    );
    process.exit(1);
  }
}
