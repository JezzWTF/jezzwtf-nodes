// Shared helpers for the JezzWTF model-loader frontends. Exports only; registers nothing.
import { api } from "../../../scripts/api.js";

export { api };

const injected = new Set();

export function injectCss(id, css) {
    if (injected.has(id) || document.getElementById(id)) return;
    injected.add(id);
    const style = document.createElement("style");
    style.id = id;
    style.textContent = css;
    document.head.appendChild(style);
}

/** Tiny element builder: h("div.cls.other", {props}, children...) */
export function h(spec, props = {}, ...children) {
    const [tag, ...classes] = spec.split(".");
    const el = document.createElement(tag || "div");
    if (classes.length) el.className = classes.join(" ");
    for (const [k, v] of Object.entries(props ?? {})) {
        if (v == null || v === false) continue;
        if (k === "style" && typeof v === "object") Object.assign(el.style, v);
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else if (k === "dataset") Object.assign(el.dataset, v);
        else if (k in el) el[k] = v;
        else el.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of children.flat()) {
        if (c == null || c === false) continue;
        el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
}

export const findWidget = (node, name) => node.widgets?.find((w) => w.name === name);

/** Hide a backing widget while keeping it serialised. Safe to call repeatedly. */
export function hideWidget(w) {
    if (!w) return w;
    w.hidden = true;
    w.options = { ...(w.options || {}), hidden: true };
    if (!w._jwtfHidden) {
        w._jwtfHidden = true;
        w.computeSize = () => [0, -4];
    }
    if (w.element) w.element.style.display = "none";
    if (w.inputEl && w.inputEl !== w.element) w.inputEl.style.display = "none";
    return w;
}

/** Set a widget's value and fire its callback (so graph change tracking notices). */
export function setWidgetValue(w, value) {
    if (!w) return;
    w.value = value;
    w.callback?.(value);
}

/** Chain a function onto an object method (prototype or instance). */
export function chain(obj, name, fn) {
    const orig = obj[name];
    obj[name] = function (...args) {
        const r = orig?.apply(this, args);
        fn.apply(this, args);
        return r;
    };
}

/** Wrap a widget callback so `fn(value)` runs after the original. */
export function onWidget(w, fn) {
    if (!w || w._jwtfWrapped?.has(fn)) return;
    (w._jwtfWrapped ??= new Set()).add(fn);
    const orig = w.callback;
    w.callback = function (v, ...rest) {
        const r = orig?.call(this, v, ...rest);
        fn(v);
        return r;
    };
}

export function fitNode(node, minW = 0, minH = 0) {
    const sz = node.computeSize();
    node.setSize([Math.max(node.size[0], sz[0], minW), Math.max(sz[1], minH)]);
    node.setDirtyCanvas(true, true);
}

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export const round2 = (v) => Math.round(v * 100) / 100;

export async function getJson(path, init) {
    const res = await api.fetchApi(path, init);
    let body = null;
    try { body = await res.json(); } catch { /* non-JSON error body */ }
    if (!res.ok) throw new Error(body?.error ?? `${res.status} ${res.statusText}`);
    return body;
}

export async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        const ta = h("textarea", { value: text, style: { position: "fixed", opacity: "0" } });
        document.body.append(ta);
        ta.select();
        let ok = false;
        try { ok = document.execCommand("copy"); } catch { ok = false; }
        ta.remove();
        return ok;
    }
}

let toastEl = null;
export function toast(text, kind = "ok") {
    if (!toastEl) {
        toastEl = h("div.jwtf-ml-toast");
        document.body.append(toastEl);
    }
    toastEl.textContent = text;
    toastEl.className = `jwtf-ml-toast show ${kind}`;
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(() => toastEl.classList.remove("show"), 1400);
}

export function loadJson(key, fallback) {
    try {
        const v = JSON.parse(localStorage.getItem(key) ?? "null");
        return v ?? fallback;
    } catch {
        return fallback;
    }
}

export function saveJson(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}

export const BASE_CSS = `
.jwtf-ml { box-sizing: border-box; width: 100%; display: flex; flex-direction: column; gap: 6px; padding: 6px;
  font: 12px system-ui, sans-serif; color: #ddd; background: #1b1c20; border: 1px solid #2c2e35; border-radius: 8px;
  overflow: hidden; user-select: none; }
.jwtf-ml * { box-sizing: border-box; }
.jwtf-ml-row { display: flex; align-items: center; gap: 6px; }
.jwtf-ml-wrap { flex-wrap: wrap; }
.jwtf-ml-grow { flex: 1 1 auto; min-width: 0; }
.jwtf-ml-muted { color: #8b8f99; }
.jwtf-ml-btn { font: inherit; color: #ddd; background: #2a2c33; border: 1px solid #3a3d46; border-radius: 6px;
  padding: 3px 9px; cursor: pointer; }
.jwtf-ml-btn:hover:not(:disabled) { background: #343741; }
.jwtf-ml-btn:disabled { opacity: .45; cursor: not-allowed; }
.jwtf-ml-btn.on { background: #3c4f7a; border-color: #5672b4; }
.jwtf-ml-btn.armed { background: #7a2e3a; border-color: #c04a5c; }
.jwtf-ml-input { font: inherit; color: #e6e6e6; background: #121317; border: 1px solid #30333b; border-radius: 6px;
  padding: 3px 6px; outline: none; min-width: 0; user-select: text; }
.jwtf-ml-input:focus { border-color: #5672b4; }
.jwtf-ml-ta { font: 12px/1.45 ui-monospace, Consolas, monospace; color: #e6e6e6; background: #121317;
  border: 1px solid #30333b; border-radius: 6px; padding: 6px; outline: none; resize: none; user-select: text; width: 100%; }
.jwtf-ml-ta:focus { border-color: #5672b4; }
.jwtf-ml-dot { width: 8px; height: 8px; border-radius: 50%; background: #3a3d46; flex: none; transition: background .2s; }
.jwtf-ml-dot.live { background: #4ade80; box-shadow: 0 0 6px #4ade80; }
.jwtf-ml-dot.busy { background: #facc15; box-shadow: 0 0 6px #facc15; }
.jwtf-ml-dot.err { background: #f43f5e; box-shadow: 0 0 6px #f43f5e; }
.jwtf-ml-chip { font-size: 11px; padding: 1px 8px; border-radius: 10px; background: #2d3a55; color: #b8c8f0;
  cursor: pointer; border: 0; }
.jwtf-ml-chip:hover { background: #3b4c70; }
.jwtf-ml-chip.on { background: #4a64a0; color: #fff; }
.jwtf-ml-toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); padding: 5px 12px;
  background: #23252c; color: #e6e6e6; border: 1px solid #3a3d46; border-radius: 8px; font: 12px system-ui, sans-serif;
  opacity: 0; pointer-events: none; transition: opacity .2s; z-index: 10001; }
.jwtf-ml-toast.show { opacity: 1; }
.jwtf-ml-toast.warn { border-color: #c9a227; }
.jwtf-ml-toast.err { border-color: #f43f5e; }
`;
injectCss("jwtf-ml-base", BASE_CSS);
