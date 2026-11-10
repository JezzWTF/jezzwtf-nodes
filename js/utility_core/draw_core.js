// Pure Draw Image helpers (no ComfyUI imports) so they can be unit-tested under plain node.

/** Another live editor already using this editor's uid (node ids repeat across graphs, so ids can't arbitrate). */
export function collidesWithOther(editors, ed) {
    for (const other of editors) if (other !== ed && other.uid === ed.uid) return true;
    return false;
}

/** Free a layer's GPU texture now instead of waiting for garbage collection, then forget it. */
export function dropTexture(layer) {
    try { layer.tex?.texture?.destroy?.(); } catch { /* device lost */ }
    layer.tex = null;
}
