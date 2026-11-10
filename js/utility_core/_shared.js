// Shared helpers for the JezzWTF utility-core frontends. Exports only; registers nothing.

export function injectCss(id, css) {
    if (document.getElementById(id)) return;
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
        if (v == null) continue;
        if (k === "style" && typeof v === "object") Object.assign(el.style, v);
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else if (k === "dataset") Object.assign(el.dataset, v);
        else if (k in el) el[k] = v;
        else el.setAttribute(k, v);
    }
    for (const c of children.flat()) {
        if (c == null || c === false) continue;
        el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
}

export const findWidget = (node, name) => node.widgets?.find((w) => w.name === name);

/** Show or hide a widget using the frontend's own hidden flags. */
export function setWidgetVisible(node, w, visible) {
    if (!w) return;
    w.hidden = !visible;
    w.options = w.options ?? {};
    w.options.hidden = !visible;
    // Zero height while hidden so the node doesn't keep a gap for it.
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

export const hideWidget = (node, w) => setWidgetVisible(node, w, false);

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
    if (!w) return;
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

export function viewUrl(api, { filename, subfolder = "", type = "temp" }) {
    const q = new URLSearchParams({ filename, subfolder, type, t: String(Date.now()) });
    return api.apiURL(`/view?${q}`);
}

export const BASE_CSS = `
.jwtf-card { box-sizing: border-box; width: 100%; height: 100%; display: flex; flex-direction: column; gap: 6px;
  padding: 6px; font: 12px system-ui, sans-serif; color: #ddd; background: #1b1c20; border: 1px solid #2c2e35;
  border-radius: 8px; overflow: hidden; }
.jwtf-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.jwtf-grow { flex: 1 1 auto; min-width: 0; }
.jwtf-muted { color: #8b8f99; }
.jwtf-btn { font: inherit; color: #ddd; background: #2a2c33; border: 1px solid #3a3d46; border-radius: 6px;
  padding: 3px 9px; cursor: pointer; }
.jwtf-btn:hover:not(:disabled) { background: #343741; }
.jwtf-btn:disabled { opacity: .45; cursor: not-allowed; }
.jwtf-btn.on { background: #3c4f7a; border-color: #5672b4; }
.jwtf-ta { box-sizing: border-box; width: 100%; resize: vertical; font: 12px/1.45 ui-monospace, Consolas, monospace;
  color: #e6e6e6; background: #121317; border: 1px solid #30333b; border-radius: 6px; padding: 6px; outline: none; }
.jwtf-ta:focus { border-color: #5672b4; }
.jwtf-ta[readonly] { opacity: .6; border-style: dashed; cursor: not-allowed; }
.jwtf-dot { width: 8px; height: 8px; border-radius: 50%; background: #3a3d46; transition: background .2s; flex: none; }
.jwtf-dot.live { background: #4ade80; box-shadow: 0 0 6px #4ade80; }
.jwtf-dot.err { background: #f43f5e; box-shadow: 0 0 6px #f43f5e; }
.jwtf-input { font: inherit; color: #e6e6e6; background: #121317; border: 1px solid #30333b; border-radius: 6px;
  padding: 3px 6px; outline: none; min-width: 0; }
`;
injectCss("jwtf-uc-base", BASE_CSS);
