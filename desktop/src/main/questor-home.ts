// 单点解析 Questor 用户状态目录（overview §14 "路径单点解析"）。
// 优先级：QUESTOR_HOME env（非空、trim 后不空）→ join(homedir(), ".questor")。
// 返回绝对路径；**不 mkdir**——写入侧走 atomic-file 的 mkdir -p，避免此函数
// 有副作用（可测性 + 幂等）。
import { homedir } from "node:os";
import { join, resolve } from "node:path";

export function resolveQuestorHome(env: NodeJS.ProcessEnv): string {
  const raw = env.QUESTOR_HOME;
  if (raw && raw.trim() !== "") return resolve(raw);
  return resolve(join(homedir(), ".questor"));
}
