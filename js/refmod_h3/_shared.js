// Shared helpers for the RefMod / H3 frontends. Exports only; registers nothing.
// (ComfyUI loads every .js under js/ as an extension; a file without registerExtension is inert.)
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

/** Show or hide a widget with the frontend's own hidden flags and a zero-height size. */
export function setWidgetVisible(node, w, visible) {
    if (!w) return;
    w.hidden = !visible;
    w.options = w.options ?? {};
    w.options.hidden = !visible;
    if (!visible && !w._jwtfSize) {
        w._jwtfSize = { own: Object.hasOwn(w, "computeSize"), fn: w.computeSize };
        w.computeSize = () => [0, -4];
    } else if (visible && w._jwtfSize) {
        if (w._jwtfSize.own) w.computeSize = w._jwtfSize.fn;
        else delete w.computeSize;
        w._jwtfSize = null;
    }
    if (w.element) w.element.style.display = visible ? "" : "none";
    if (w.inputEl && w.inputEl !== w.element) w.inputEl.style.display = visible ? "" : "none";
}

/** Chain a function onto an object method (prototype or instance); the original runs first. */
export function chain(obj, name, fn) {
    const orig = obj[name];
    obj[name] = function (...args) {
        const r = orig?.apply(this, args);
        const r2 = fn.apply(this, args);
        return r2 === undefined ? r : r2;
    };
}

/** Wrap a widget callback so `fn(value)` runs after the original. */
export function onWidget(w, fn) {
    if (!w || w._jwtfWrapped?.includes(fn)) return;
    w._jwtfWrapped = [...(w._jwtfWrapped ?? []), fn];
    const orig = w.callback;
    w.callback = function (v, ...rest) {
        const r = orig?.call(this, v, ...rest);
        fn(v);
        return r;
    };
}

/** Look up a link in either the array/object or Map form of graph.links. */
export function getLink(graph, id) {
    if (!graph || id == null) return null;
    const links = graph.links;
    if (!links) return null;
    return typeof links.get === "function" ? links.get(id) : links[id];
}

export function fitHeight(node, minW = 0) {
    const sz = node.computeSize();
    node.setSize([Math.max(node.size[0], sz[0], minW), sz[1]]);
    node.setDirtyCanvas(true, true);
}

/** GET a JSON route; resolves to `fallback` on any failure. */
export async function fetchJson(path, fallback = null) {
    try {
        const r = await api.fetchApi(path);
        if (!r.ok) return fallback;
        return await r.json();
    } catch {
        return fallback;
    }
}

/** True when two node ids refer to the same node (equal, or one is the tail of a subgraph path). */
export function sameNode(a, b) {
    if (a == null || b == null) return false;
    const x = String(a), y = String(b);
    return x === y || x.endsWith(":" + y) || y.endsWith(":" + x);
}

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** Every node of the visible graph and the root graph that has this comfyClass. */
export function nodesOfClass(app, comfyClass) {
    const out = new Set();
    for (const g of [app.canvas?.graph, app.graph]) {
        for (const n of g?._nodes ?? []) if (n.comfyClass === comfyClass || n.type === comfyClass) out.add(n);
    }
    return [...out];
}
