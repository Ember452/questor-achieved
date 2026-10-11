// schema → TypeScript 类型生成（R4：前端类型由 schema 生成，禁止手写 DTO）。
// 用法：node scripts/gen-types.mjs [--check]
//   默认：原位重生成 ui/src/rpc/generated/*.d.ts
//   --check：生成后断言 `git diff --exit-code -- src/rpc/generated`（CI 与 just gen-check 同源）
// 真相源：src/questor/schemas/{model,app_server}/*.json（纯 JSON Schema）。

import { compile } from "json-schema-to-typescript";
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join, dirname, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { execSync } from "node:child_process";

const uiRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = join(uiRoot, "..");
const schemaRoot = join(repoRoot, "src", "questor", "schemas");
const outDir = join(uiRoot, "src", "rpc", "generated");
const check = process.argv.includes("--check");

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
  });
  const outFile = join(outDir, `${name}.d.ts`);
  writeFileSync(outFile, ts, "utf-8");
  console.log(`generated: src/rpc/generated/${name}.d.ts`);
}

if (check) {
  try {
    execSync("git diff --exit-code -- ui/src/rpc/generated", { cwd: repoRoot, stdio: "pipe" });
    console.log("gen-check: generated types are up to date");
  } catch {
    console.error("gen-check FAILED: generated types drifted from schemas. Run `just gen` and commit.");
    process.exit(1);
  }
}
