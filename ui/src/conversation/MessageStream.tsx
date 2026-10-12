// 会话流：Notification 分派 + 消息渲染（ConversationPane 负责接线，本文件只管展示）。
// 与 panels 层解耦：这里只关心 delta / item/started / item/completed / turn/steered /
// run/status 五类通知；新加通知族在 ConversationPane 的 reducer 里补 case。

import { useWorkbenchStore, type ChatMessage } from "../state/workbenchStore";

export function MessageStream() {
  const messages = useWorkbenchStore((s) => s.messages);
  const runStatus = useWorkbenchStore((s) => s.runStatus);

  if (messages.length === 0) {
    return (
      <div className="flex-1 overflow-auto p-4">
        <EmptyConversationHome />
      </div>
    );
  }
  return (
    <div className="flex-1 overflow-auto p-4">
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
      {runStatus ? (
        <p className="mt-2 text-ui-2xs text-foreground-subtlest">run: {runStatus}</p>
      ) : null}
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="mb-3">
      <header className="flex items-center gap-2 text-ui-2xs text-foreground-subtlest">
        <span className="uppercase">{message.role}</span>
        {message.steered ? <span className="rounded bg-surface px-1">steer</span> : null}
        {message.isStreaming ? <span className="animate-pulse">▍</span> : null}
      </header>
      <pre className="mt-1 whitespace-pre-wrap font-mono text-ui-xs text-foreground">
        {message.text || "(empty)"}
      </pre>
    </div>
  );
}

function EmptyConversationHome() {
  return (
    <section className="flex h-full items-center justify-center">
      <div className="max-w-md text-center">
        <h2 className="text-ui-xl font-semibold">Questor</h2>
        <p className="mt-2 text-ui-sm text-foreground-subtle">
          Agent 在本地项目上长活——过程全摊开、随时能插手、跑完能验收。
        </p>
        <p className="mt-4 text-ui-2xs text-foreground-subtlest">
          可见 Visible · 可干预 Intervenable · 可验证 Verifiable
        </p>
      </div>
    </section>
  );
}
