// 对话区：标题栏 + 空态（EmptyConversationHome，参照 wuu empty-home）+ Composer 占位。
// M1 骨架只渲染空态与禁用输入；消息流 M2 接真事件流。

import { useState } from "react";

export function ConversationPane() {
  return (
    <main aria-label="conversation-pane" className="flex min-w-0 flex-1 flex-col">
      <header className="border-b border-border px-4 py-2 text-ui-sm text-foreground-subtle">
        选择或新建一个会话
      </header>
      <EmptyConversationHome />
      <Composer />
    </main>
  );
}

function EmptyConversationHome() {
  return (
    <section className="flex flex-1 items-center justify-center">
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

function Composer() {
  const [value, setValue] = useState("");
  return (
    <div className="border-t border-border p-3">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled
        rows={2}
        placeholder="M2 起：描述任务（Enter 发送 / 插话）——骨架期禁用"
        className="w-full resize-none rounded border border-border bg-surface px-3 py-2 text-ui-sm placeholder:text-foreground-subtlest disabled:opacity-60"
      />
    </div>
  );
}
