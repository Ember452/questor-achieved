// Files 面板：`files/list` 列 workspace 内条目；点文件后 `files/read` 带
// expected_revision 拉内容（B-92：不匹配一律拒，不给过期结果）。
// M3c 简化：只列一层目录 + 单击展文本；"只改这一段"、语法高亮、图片/PDF 推 Phase E。

import { useEffect, useState } from "react";
import { client } from "../rpc/client";
import type { FilesListEntry } from "../rpc/generated/app_server-v0-1";
import type { PanelProps } from "./registry";

export function FilesPanel({ threadId, activeTurnId }: PanelProps) {
  const [entries, setEntries] = useState<FilesListEntry[]>([]);
  const [revision, setRevision] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  void threadId;
  void activeTurnId;

  useEffect(() => {
    let cancelled = false;
    setError(null);
    client
      .call("files/list", { path: ".", recursive: false })
      .then((r) => {
        if (!cancelled) {
          setEntries(r.entries);
          setRevision(r.revision);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selected || revision === null) {
      setContent(null);
      return;
    }
    let cancelled = false;
    setError(null);
    client
      .call("files/read", { path: selected, expected_revision: revision })
      .then((r) => {
        if (!cancelled) setContent(r.content);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, revision]);

  return (
    <div className="flex h-full min-h-0">
      <ul className="w-1/2 overflow-auto border-r border-border text-ui-xs">
        <li className="px-3 py-1 font-mono text-foreground-subtlest">rev {revision ?? 0}</li>
        {entries.map((e) => (
          <li key={e.path}>
            <button
              type="button"
              className="block w-full px-3 py-1 text-left font-mono hover:bg-surface"
              onClick={() => setSelected(e.path)}
            >
              {e.kind === "dir" ? `d ${e.path}/` : `f ${e.path} (${e.size ?? 0}B)`}
            </button>
          </li>
        ))}
      </ul>
      <div className="w-1/2 overflow-auto text-ui-xs">
        {error ? (
          <p className="p-3 text-red-500">err: {error}</p>
        ) : selected ? (
          <pre className="whitespace-pre p-3 font-mono text-foreground-subtle">
            {content ?? "..."}
          </pre>
        ) : (
          <p className="p-3 text-foreground-subtlest">选一个文件查看内容</p>
        )}
      </div>
    </div>
  );
}
