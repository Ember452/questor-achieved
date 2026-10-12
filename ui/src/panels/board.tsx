// Board 面板（M4 分栏看板 + M5 验收证据卡）：任务列表 + 状态分栏 + 确认/打回，
// 并把"声称的检查 vs 当时录得输出"的核对结论摊开——每条结论可点击回链到具体记录条目。
//
// D7 决定：M4 只做注册表驱动的分栏视图，`@xyflow/react` 的 DAG 图推 E1；
// 类型全部从 rpc/generated 引（R4，禁止手写 DTO）。任务状态迁移一律经 serve 方法，
// 前端不猜状态（模型提议、代码裁决）。验收 verdict 只呈现 serve 落好的结论，前端不臆断。

import { useCallback, useEffect, useState } from "react";
import { client } from "../rpc/client";
import type {
  AcceptanceStatus,
  EvidenceDTO,
  EvidenceVerdict,
  TaskDTO,
} from "../rpc/generated/app_server-v0-1";
import type { PanelProps } from "./registry";

//: 看板分栏顺序（与编排任务状态机的可见阶段对应）
const COLUMNS: ReadonlyArray<{ id: string; label: string; statuses: readonly string[] }> = [
  { id: "todo", label: "待办", statuses: ["inbox", "pending", "planning", "planned"] },
  { id: "doing", label: "进行中", statuses: ["executing", "paused"] },
  { id: "review", label: "待验收", statuses: ["reviewed"] },
  { id: "done", label: "已结束", statuses: ["completed", "failed", "cancelled"] },
];

//: verdict → 呈现色（诚实呈现：unverified 用中性警示，不当作通过）
const VERDICT_STYLE: Record<EvidenceVerdict, string> = {
  verified: "bg-emerald-600/20 text-emerald-500 border-emerald-700",
  mismatch: "bg-red-600/20 text-red-500 border-red-700",
  unverified: "bg-amber-600/20 text-amber-500 border-amber-700",
};

const VERDICT_LABEL: Record<AcceptanceStatus, string> = {
  proposed: "待授权",
  accepted_by_user: "已授权",
  executing: "执行中",
  reported: "已上报待核",
  verified: "证据核验通过",
  regressed: "证据不符/缺记录",
};

/** 会话轨迹里的 item 是自由形状（schema 侧为 `{}`）；只做定位条目所需的窄化读取。 */
type TraceItem = { id?: string; run_id?: string; payload?: { output?: string; preview?: string } };

export function BoardPanel({ threadId }: PanelProps) {
  const [tasks, setTasks] = useState<TaskDTO[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [openTaskId, setOpenTaskId] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<EvidenceDTO[]>([]);
  const [record, setRecord] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    client
      .call("task/list", threadId ? { thread_id: threadId } : {})
      .then((r) => setTasks(r.tasks as TaskDTO[]))
      .catch((err: Error) => setError(err.message));
  }, [threadId]);

  useEffect(() => {
    load();
    // 任务状态/验收通知到达时刷新（单一数据源在服务端，前端不镜像真值）
    return client.onNotification((n) => {
      if (n.method === "task/status" || n.method === "plan/updated" || n.method === "evidence/reported") {
        load();
      }
    });
  }, [load]);

  async function act(
    method: "task/review" | "task/reject" | "task/complete" | "task/start",
    taskId: string,
  ) {
    try {
      await client.call(method, { task_id: taskId, authorized: true });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  /** 展开某任务的验收证据：经 `task/show` 拉证据（结论只读呈现，不前端造 verdict）。 */
  async function openEvidence(taskId: string) {
    setRecord(null);
    if (openTaskId === taskId) {
      setOpenTaskId(null);
      return;
    }
    setOpenTaskId(taskId);
    try {
      const r = await client.call("task/show", { task_id: taskId });
      setEvidence(r.evidence ?? []);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  /** 结论点击回链：经 `sessiontrace/get` 定位 `recorded_output_ref` 指向的记录条目。 */
  async function revealRecord(threadOfTask: string | null | undefined, ref: string) {
    if (!threadOfTask) {
      setRecord(`无所属线程，无法定位记录：${ref}`);
      return;
    }
    try {
      const r = await client.call("sessiontrace/get", { thread_id: threadOfTask });
      const items: TraceItem[] = (r.turns ?? []).flatMap((t) => (t.items ?? []) as TraceItem[]);
      const hit = items.find((it) => it.id === ref);
      if (hit) {
        const body = hit.payload?.output ?? hit.payload?.preview ?? "(空输出)";
        setRecord(`记录 ${ref}：\n${body.slice(0, 2000)}`);
      } else {
        // 溢出回链是落盘文件名（非 item id）——诚实显示引用本身，不假装找到
        setRecord(`录得输出已落盘，引用：${ref}`);
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (error) return <div className="p-3 text-ui-xs text-red-500">err: {error}</div>;

  return (
    <div className="flex min-h-0 flex-1 gap-2 overflow-auto p-2">
      {COLUMNS.map((col) => {
        const items = tasks.filter((t) => col.statuses.includes(t.status));
        return (
          <section key={col.id} className="min-w-44 flex-1">
            <h3 className="px-1 py-1 text-ui-xs text-foreground-subtle">
              {col.label} · {items.length}
            </h3>
            <ul className="space-y-1">
              {items.map((t) => {
                const open = openTaskId === t.id;
                const verdict = VERDICT_LABEL[t.acceptance.status] ?? t.acceptance.status;
                return (
                  <li key={t.id} className="rounded border border-border bg-surface p-2 text-ui-xs">
                    <button
                      type="button"
                      onClick={() => void openEvidence(t.id)}
                      className="w-full text-left text-foreground"
                    >
                      {t.title}
                    </button>
                    <div className="text-foreground-subtlest">
                      {t.status} · {t.id}
                    </div>
                    <div className="mt-1 inline-block rounded border border-border px-1.5 py-0.5 text-foreground-subtle">
                      验收：{verdict}
                    </div>
                    {open && (
                      <div className="mt-2 space-y-1 border-t border-border pt-2">
                        {evidence.length === 0 ? (
                          <p className="text-foreground-subtlest">
                            无核对证据（未上报声称，或尚无录得输出可比对——不轻信）
                          </p>
                        ) : (
                          evidence.map((ev) => (
                            <div key={ev.id} className="rounded bg-surface-subtle p-1.5">
                              <div className="flex items-center gap-2">
                                <span
                                  className={`rounded border px-1 text-[10px] ${VERDICT_STYLE[ev.verdict]}`}
                                >
                                  {ev.verdict}
                                </span>
                                <span className="text-foreground">{ev.claimed || "(空声称)"}</span>
                              </div>
                              <button
                                type="button"
                                onClick={() => void revealRecord(t.thread_id, ev.recorded_output_ref)}
                                className="mt-1 font-mono text-[10px] text-foreground-subtle underline"
                              >
                                {ev.recorded_output_ref || "无记录引用（unverified）"}
                              </button>
                            </div>
                          ))
                        )}
                        {record && (
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap bg-surface px-2 py-1 text-[10px] text-foreground-subtle">
                            {record}
                          </pre>
                        )}
                      </div>
                    )}
                    {t.status === "reviewed" && (
                      <div className="mt-1 flex gap-1">
                        <button
                          type="button"
                          onClick={() => void act("task/complete", t.id)}
                          className="rounded bg-brand px-2 py-0.5 text-on-brand"
                        >
                          通过
                        </button>
                        <button
                          type="button"
                          onClick={() => void act("task/reject", t.id)}
                          className="rounded border border-border px-2 py-0.5 text-foreground-subtle"
                        >
                          打回
                        </button>
                      </div>
                    )}
                    {t.status === "executing" && (
                      <button
                        type="button"
                        onClick={() => void act("task/review", t.id)}
                        className="mt-1 rounded border border-border px-2 py-0.5 text-foreground-subtle"
                      >
                        提交待审
                      </button>
                    )}
                    {(t.status === "pending" || t.status === "planned") && (
                      <button
                        type="button"
                        onClick={() => void act("task/start", t.id)}
                        className="mt-1 rounded border border-border px-2 py-0.5 text-foreground-subtle"
                      >
                        开始执行
                      </button>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
