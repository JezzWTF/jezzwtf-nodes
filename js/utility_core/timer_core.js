// Pure Batch Timer logic (no ComfyUI imports) so it can be unit-tested under plain node.

/**
 * Does the execution path `id` ("5" or "12:5") belong to `node`?
 * The last segment must be the node's own id and the leading segments must walk
 * subgraph instances from the root down to the graph that owns the node.
 */
export function pathMatches(node, id, rootGraph) {
    const parts = String(id).split(":");
    if (parts[parts.length - 1] !== String(node.id)) return false;
    let graph = rootGraph;
    for (const seg of parts.slice(0, -1)) {
        graph = graph?.getNodeById?.(seg)?.subgraph;
        if (!graph) return false;
    }
    return graph === (node.graph ?? rootGraph);
}

/**
 * Credit `n` finished items at wall-clock `nowMs`. The duration is the real time since the
 * previous item (or the run start), so time spent while the clock was paused still counts:
 * the work kept running. Mutates `t.durations` / `t.lastItemAt`; returns the durations added.
 */
export function attributeItems(t, n, nowMs, maxDurations = 64, maxPush = 5) {
    const each = Math.max(0, nowMs - t.lastItemAt) / 1000 / n;
    const added = [];
    for (let i = 0; i < Math.min(n, maxPush); i++) added.push(each);
    t.durations = [...t.durations, ...added].slice(-maxDurations);
    t.lastItemAt = nowMs;
    return added;
}
