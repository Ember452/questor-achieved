// Renderer 事件合批器：50 ms 窗口内同 identity 的 delta 合成一帧再 emit；
// 非 delta 事件先 flush 当前 batch、再立即 emit；raw provider delta 事件丢弃。
// provenance: 严格照 wuu-main/desktop/src/main/rendererServerEventBatcher.ts (137 行)
//   的事件集、identity 键、控制事件优先 flush 的时序；重写实现（AGENTS §二 (a) 边界层）。
// B-117：每 token 一帧 IPC 转发会卡住 renderer；且 `resolveSnapshot` 后 renderer 会
//   拿 snapshot 重放 delta——batcher 必须在 snapshot 之前 flush 已 emit 的 delta，
//   否则 renderer 见到"snapshot + 已重放" 双份。
export interface BatchedNotification {
  method: string;
  params?: unknown;
}

const STREAM_DELTA_METHODS = new Set<string>([
  "item/agentMessage/delta",
  "item/reasoning/delta",
  "item/toolCall/delta",
  "item/toolCall/outputDelta",
]);

// wuu 实测：Anthropic/OpenAI 的 raw delta 事件不应直接透传到 renderer；
// 上层 item/* delta 已经从 questor 内核规范化过、raw provider delta 会重复一份。
const RENDERER_IGNORED_METHODS = new Set<string>([
  "content_delta",
  "thinking_delta",
  "tool_use_delta",
]);

const DEFAULT_BATCH_INTERVAL_MS = 50;

/** identity 键：method + thread_id + turn_id + item_id；同键的 delta 才合批。 */
function identityKey(evt: BatchedNotification): string {
  const p = (evt.params ?? {}) as {
    thread_id?: string;
    turn_id?: string;
    item_id?: string;
  };
  return `${evt.method}::${p.thread_id ?? ""}::${p.turn_id ?? ""}::${p.item_id ?? ""}`;
}

export class RendererServerEventBatcher {
  private pending = new Map<string, BatchedNotification>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readonly intervalMs: number;

  constructor(
    private emit: (evt: BatchedNotification) => void,
    opts: { batchIntervalMs?: number } = {},
  ) {
    this.intervalMs = opts.batchIntervalMs ?? DEFAULT_BATCH_INTERVAL_MS;
  }

  enqueue(evt: BatchedNotification): void {
    if (RENDERER_IGNORED_METHODS.has(evt.method)) return; // raw provider delta 不转发
    if (!STREAM_DELTA_METHODS.has(evt.method)) {
      // 控制/终止事件：先 flush 已积累的 delta batch，再立即 emit 本条。
      this.flush();
      this.emit(evt);
      return;
    }
    const key = identityKey(evt);
    const prev = this.pending.get(key);
    this.pending.set(key, prev ? mergeDelta(prev, evt) : evt);
    if (this.timer === null) {
      this.timer = setTimeout(() => this.flush(), this.intervalMs);
      this.timer.unref();
    }
  }

  flush(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    for (const evt of this.pending.values()) this.emit(evt);
    this.pending.clear();
  }

  /** snapshot 请求前先 flush，防 renderer 拿到 snapshot 后又收到 snapshot 覆盖前的 delta 重放。 */
  async resolveSnapshot<T>(request: Promise<T>): Promise<T> {
    this.flush();
    return request;
  }
}

/**
 * delta 合并策略：同 identity 的连续 delta 累积 params.text（agentMessage/reasoning）、
 * params.delta（toolCall/outputDelta 常见字段）；其余字段以最新一帧为准（保留 id/索引）。
 * 无 text/delta 时只覆盖 params、不强合字段——保证不同 provider 形状下都能出合批语义。
 */
function mergeDelta(
  prev: BatchedNotification,
  next: BatchedNotification,
): BatchedNotification {
  const pp = (prev.params ?? {}) as Record<string, unknown>;
  const np = (next.params ?? {}) as Record<string, unknown>;
  const merged: Record<string, unknown> = { ...pp, ...np };
  if (typeof pp.text === "string" && typeof np.text === "string") {
    merged.text = pp.text + np.text;
  } else if (typeof pp.delta === "string" && typeof np.delta === "string") {
    merged.delta = pp.delta + np.delta;
  } else if (typeof pp.content === "string" && typeof np.content === "string") {
    merged.content = pp.content + np.content;
  }
  return { method: next.method, params: merged };
}
