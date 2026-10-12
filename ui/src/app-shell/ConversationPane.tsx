// 对话区：MessageStream 呈现 store.messages；Composer 送 turn/start；
// 一 useEffect 订阅 client 的通知，把 delta / item/started / item/completed /
// turn/steered / run/status 分派进 store。护栏：新加通知族在此文件的 switch 补 case
// 即可，不触碰 MessageStream 与 store 的接口形状。

import { useEffect, useState } from "react";
import { MessageStream } from "../conversation/MessageStream";
import { client } from "../rpc/client";
import { useWorkbenchStore } from "../state/workbenchStore";

let counter = 0;
function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}-${counter}`;
}

export function ConversationPane() {
  const activeSessionId = useWorkbenchStore((s) => s.activeSessionId);
  const setActiveTurn = useWorkbenchStore((s) => s.setActiveTurn);
  const appendMessage = useWorkbenchStore((s) => s.appendMessage);
  const appendDelta = useWorkbenchStore((s) => s.appendDelta);
  const markLastAssistantDone = useWorkbenchStore((s) => s.markLastAssistantDone);
  const setRunStatus = useWorkbenchStore((s) => s.setRunStatus);

  // 通知分派：与 protocol.md §4 事件族一一对应（M3 只落 delta / item/* / turn/usage /
  // turn/steered / run/status / notice/compact；未列的族在 default 里忽略，M4 时补）
  useEffect(() => {
    const off = client.onNotification((n) => {
      switch (n.method) {
        case "delta":
          appendDelta(n.params.text);
          break;
        case "item/started":
          appendMessage({
            id: n.params.tool_use_id,
            role: "assistant",
            text: `▶ ${n.params.name}(${JSON.stringify(n.params.arguments ?? {})})`,
            isStreaming: false,
          });
          break;
        case "item/completed":
          appendMessage({
            id: `${n.params.tool_use_id}-done`,
            role: "assistant",
            text: `${n.params.is_error ? "✗" : "✓"} ${n.params.name} · ${(n.params.elapsed_s ?? 0).toFixed(2)}s`,
            isStreaming: false,
          });
          break;
        case "turn/steered":
          appendMessage({
            id: nextId("steer"),
            role: "user",
            text: n.params.content,
            isStreaming: false,
            steered: true,
          });
          break;
        case "run/status":
          setRunStatus(n.params.status);
          if (n.params.status === "completed" || n.params.status === "failed") {
            markLastAssistantDone();
          }
          // 回合结束 → 拉该会话最新 turn 喂给 Review 面板（turn/start 响应不含
          // turn_id，落盘后从 thread/show 取；单线程本地即最后一条）。
          if (n.params.status === "completed" && activeSessionId) {
            void client
              .call("thread/show", { thread_id: activeSessionId })
              .then((r) => {
                const turns = r.turns as { id?: string }[];
                const last = turns[turns.length - 1];
                if (last?.id) setActiveTurn(last.id);
              })
              .catch(() => {
                /* 拉取失败不影响回合完成呈现 */
              });
          }
          break;
        case "notice/compact":
          appendMessage({
            id: nextId("compact"),
            role: "assistant",
            text: `· compact ${n.params.kind}${n.params.before_tokens != null ? ` ${n.params.before_tokens}→${n.params.after_tokens}tok` : ""}`,
            isStreaming: false,
          });
          break;
        case "turn/usage":
        default:
          break;
      }
    });
    return off;
  }, [
    appendDelta,
    appendMessage,
    markLastAssistantDone,
    setRunStatus,
    activeSessionId,
    setActiveTurn,
  ]);

  return (
    <main aria-label="conversation-pane" className="flex min-w-0 flex-1 flex-col">
      <header className="border-b border-border px-4 py-2 text-ui-sm text-foreground-subtle">
        {activeSessionId ?? "选择或新建一个会话"}
      </header>
      <MessageStream />
      <Composer />
    </main>
  );
}

function Composer() {
  const [value, setValue] = useState("");
  const activeSessionId = useWorkbenchStore((s) => s.activeSessionId);
  const runStatus = useWorkbenchStore((s) => s.runStatus);
  const appendMessage = useWorkbenchStore((s) => s.appendMessage);
  const setActiveTurn = useWorkbenchStore((s) => s.setActiveTurn);
  const setSessions = useWorkbenchStore((s) => s.setSessions);
  const setActive = useWorkbenchStore((s) => s.setActive);
  const setActiveTurn2 = setActiveTurn;

  async function submit() {
    const text = value.trim();
    if (!text) return;
    let threadId = activeSessionId;
    if (!threadId) {
      // 无活跃会话时自动新建一条以 text 为标题的会话（M3 出口判据 1 的手工冒烟入口）
      const created = await client.call("thread/create", {
        title: text.slice(0, 60),
      });
      threadId = created.thread.id;
      const list = await client.call("thread/list", {});
      setSessions(list.threads);
      setActive(threadId);
    }
    appendMessage({
      id: nextId("user"),
      role: "user",
      text,
      isStreaming: false,
    });
    setValue("");
    const ack = await client.call("turn/start", {
      thread_id: threadId,
      user_text: text,
    });
    void ack;
    setActiveTurn2(null); // 面板按当前 thread 最新 turn 拉；这里保留 hook 位待 store 里补 activeTurnId
  }

  const disabled = !value.trim() || runStatus === "running" || runStatus === "steered";

  return (
    <div className="border-t border-border p-3">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!disabled) void submit();
          }
        }}
        rows={2}
        placeholder={
          runStatus === "running" || runStatus === "steered"
            ? "Agent 正在跑，Enter 排队下一条 / Shift+Enter 换行"
            : "描述任务（Enter 发送 / Shift+Enter 换行）"
        }
        className="w-full resize-none rounded border border-border bg-surface px-3 py-2 text-ui-sm placeholder:text-foreground-subtlest"
      />
      <div className="mt-2 flex justify-end">
        <button
          type="button"
          onClick={() => void submit()}
          disabled={disabled}
          className="rounded bg-foreground px-3 py-1 text-ui-xs text-background disabled:opacity-40"
        >
          发送
        </button>
      </div>
    </div>
  );
}
