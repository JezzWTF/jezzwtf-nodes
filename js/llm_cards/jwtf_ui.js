// Shared DOM helpers for the JezzWTF LLM + cards widgets.
// ComfyUI also loads this file as an extension; it only exports helpers, so that is harmless.
import { api } from "../../../scripts/api.js";

export { api };

const injected = new Set();

/** Add a <style> block once per id. */
export function injectCss(id, css) {
    if (injected.has(id) || document.getElementById(id)) return;
    injected.add(id);
    const style = document.createElement("style");
    style.id = id;
    style.textContent = css;
    document.head.appendChild(style);
}

/** Tiny element builder: h("div", {class: "x", onclick: fn}, [children]). */
export function h(tag, attrs = {}, children = []) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (v == null || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of [].concat(children)) {
        if (c == null || c === false) continue;
        el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
}

export const findWidget = (node, name) => node.widgets?.find((w) => w.name === name);

/** Hide a backing widget while keeping it serialised. */
export function hideWidget(node, name) {
    const w = findWidget(node, name);
    if (!w || w._jwtfHidden) return w;
    w._jwtfHidden = true;
    w.hidden = true;
    w.options = { ...(w.options || {}), hidden: true };
    w.computeSize = () => [0, -4];
    if (w.element) w.element.style.display = "none";
    return w;
}

export function setWidget(node, name, value) {
    const w = findWidget(node, name);
    if (!w) return;
    w.value = value;
    w.callback?.(value);
}

export function uniqueUploadName(file) {
    const raw = String(file.name || "");
    const dot = raw.lastIndexOf(".");
    const ext = dot > 0 ? raw.slice(dot).replace(/[^A-Za-z0-9.]/g, "").slice(0, 8) : "";
    const base = (dot > 0 ? raw.slice(0, dot) : raw).replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 40) || "image";
    const rand = Math.random().toString(36).slice(2, 8);
    return `${base}_${Date.now().toString(36)}_${rand}${ext || ".png"}`;
}

/**
 * Upload a file through core /upload/image without overwriting anything (core renames on a clash).
 * `unique` also gives the file a timestamped name, for pasted images that all arrive as "image.png".
 * Resolves to {name, subfolder, type}.
 */
export async function uploadToInput(file, subfolder, { unique = false } = {}) {
    const body = new FormData();
    body.append("image", file, unique ? uniqueUploadName(file) : file.name);
    body.append("overwrite", "false");
    body.append("subfolder", subfolder);
    body.append("type", "input");
    const resp = await api.fetchApi("/upload/image", { method: "POST", body });
    if (resp.status !== 200) throw new Error(`Upload failed (${resp.status})`);
    return resp.json();
}

export function viewUrl(info, cacheKey = "t") {
    const q = new URLSearchParams({
        filename: info.name ?? info.filename ?? "",
        subfolder: info.subfolder ?? "",
        type: info.type ?? "input",
        [cacheKey]: String(Date.now()),
    });
    return api.apiURL(`/view?${q}`);
}

export async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        const ta = h("textarea", { style: { position: "fixed", opacity: "0" } });
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        const ok = document.execCommand("copy");
        ta.remove();
        return ok;
    }
}

/** Stop canvas shortcuts (Delete, Ctrl+C, …) from firing while typing in a widget. */
export function shieldKeys(el) {
    for (const t of ["keydown", "keyup", "keypress"]) el.addEventListener(t, (e) => e.stopPropagation());
}

/** Drag grip that resizes `target` vertically and reports the new height. */
export function makeGrip(target, { min = 48, max = 480, initial = 64, onChange }) {
    const grip = h("div", { class: "jwtf-grip", title: "Drag to resize, double-click to reset" });
    grip.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const startY = e.clientY;
        const startH = target.getBoundingClientRect().height / (app_scale(target) || 1);
        const move = (ev) => {
            const hgt = Math.round(Math.min(max, Math.max(min, startH + (ev.clientY - startY) / (app_scale(target) || 1))));
            target.style.height = `${hgt}px`;
            onChange?.(hgt, false);
        };
        const up = () => {
            window.removeEventListener("pointermove", move);
            window.removeEventListener("pointerup", up);
            onChange?.(parseInt(target.style.height, 10) || initial, true);
        };
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
    });
    grip.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        target.style.height = `${initial}px`;
        onChange?.(initial, true);
    });
    return grip;
}

function app_scale(el) {
    // The canvas zoom is applied as a CSS transform on DOM widgets; measure it.
    const r = el.getBoundingClientRect();
    return el.offsetHeight ? r.height / el.offsetHeight : 1;
}

/** Fit a node's height to its DOM widget content. */
export function fitNode(node, minWidth = 0) {
    requestAnimationFrame(() => {
        const sz = node.computeSize();
        node.setSize([Math.max(node.size[0], sz[0], minWidth), sz[1]]);
        node.setDirtyCanvas(true, true);
    });
}

export const BASE_CSS = `
.jwtf-panel{font:12px/1.4 system-ui,sans-serif;color:var(--fg-color,#ddd);background:var(--comfy-input-bg,#1e1e1e);
 border:1px solid var(--border-color,#3a3a3a);border-radius:6px;box-sizing:border-box;overflow:hidden;display:flex;flex-direction:column}
.jwtf-row{display:flex;align-items:center;gap:6px;padding:4px 6px}
.jwtf-btn{background:var(--comfy-menu-bg,#2a2a2a);color:inherit;border:1px solid var(--border-color,#444);border-radius:4px;
 padding:2px 8px;font:inherit;cursor:pointer;white-space:nowrap}
.jwtf-btn:hover{border-color:#888}.jwtf-btn:disabled{opacity:.45;cursor:default}
.jwtf-btn.on{background:#3b5b8a;border-color:#5b83c0}
.jwtf-led{width:8px;height:8px;border-radius:50%;background:#666;flex:none}
.jwtf-led.busy{background:#f0a030;animation:jwtf-pulse 1s infinite}.jwtf-led.live{background:#4caf50;animation:jwtf-pulse .7s infinite}
.jwtf-led.done{background:#4a8fe0}.jwtf-led.error{background:#e04a4a}
@keyframes jwtf-pulse{50%{opacity:.35}}
@keyframes jwtf-in{from{opacity:0;transform:translateY(4px)}}
.jwtf-bar{height:3px;background:#333;position:relative;overflow:hidden}
.jwtf-bar>i{position:absolute;inset:0 auto 0 0;width:0;background:#f0a030;transition:width .2s}
.jwtf-bar.indet>i{width:30%;animation:jwtf-indet 1.1s linear infinite}
.jwtf-bar.live>i{background:#4caf50}.jwtf-bar.done>i{background:#4a8fe0;width:100%}.jwtf-bar.error>i{background:#e04a4a;width:100%}
@keyframes jwtf-indet{from{left:-30%}to{left:100%}}
.jwtf-muted{opacity:.65}.jwtf-grow{flex:1;min-width:0}
.jwtf-ellipsis{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jwtf-grip{height:6px;cursor:ns-resize;background:repeating-linear-gradient(90deg,#555 0 2px,transparent 2px 5px);opacity:.5;flex:none}
.jwtf-grip:hover{opacity:1}
.jwtf-chip{border:1px solid #555;border-radius:9px;padding:0 6px;font-size:10px;letter-spacing:.04em}
.jwtf-panel textarea,.jwtf-panel input{font:inherit;color:inherit;background:#151515;border:1px solid #3a3a3a;border-radius:4px;box-sizing:border-box}
`;
