// Board 面板（M4）：任务分栏看板 + 任务总结卡的确认/打回。
//
// D7 决定：M4 只做注册表驱动的分栏视图，`@xyflow/react` 的 DAG 图推 E1；
// 类型全部从 rpc/generated 引（R4，禁止手写 DTO）。任务状态迁移一律经 serve 方法，
// 前端不猜状态（模型提议、代码裁决）。

import { useCallback, useEffect, useState } from "react";
import { client } from "../rpc/client";
import type { TaskDTO } from "../rpc/generated/app_server-v0-1";
import type { PanelProps } from "./registry";

//: 看板分栏顺序（与编排任务状态机的可见阶段对应）
const COLUMNS: ReadonlyArray<{ id: string; label: string; statuses: readonly string[] }> = [
  { id: "todo", label: "待办", statuses: ["inbox", "pending", "planning", "planned"] },
  { id: "doing", label: "进行中", statuses: ["executing", "paused"] },
  { id: "review", label: "待验收", statuses: ["reviewed"] },
  { id: "done", label: "已结束", statuses: ["completed", "failed", "cancelled"] },
];

export function BoardPanel({ threadId }: PanelProps) {
  const [tasks, setTasks] = useState<TaskDTO[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    client
      .call("task/list", threadId ? { thread_id: threadId } : {})
      .then((r) => setTasks(r.tasks as TaskDTO[]))
      .catch((err: Error) => setError(err.message));
  }, [threadId]);

  useEffect(() => {
    load();
    // 任务状态迁移通知到达时刷新（单一数据源在服务端，前端不镜像真值）
    return client.onNotification((n) => {
      if (n.method === "task/status" || n.method === "plan/updated") load();
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

  if (error) return <div className="p-3 text-ui-xs text-red-500">err: {error}</div>;

  return (
    <div className="flex min-h-0 flex-1 gap-2 overflow-auto p-2">
      {COLUMNS.map((col) => {
        const items = tasks.filter((t) => col.statuses.includes(t.status));
        return (
          <section key={col.id} className="min-w-40 flex-1">
            <h3 className="px-1 py-1 text-ui-xs text-foreground-subtle">
              {col.label} · {items.length}
            </h3>
            <ul className="space-y-1">
              {items.map((t) => (
                <li key={t.id} className="rounded border border-border bg-surface p-2 text-ui-xs">
                  <div className="text-foreground">{t.title}</div>
                  <div className="text-foreground-subtlest">
                    {t.status} · {t.id}
                  </div>
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
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
