import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, findWidget, getLink, h, hideWidget, injectCss } from "./_shared.js";

// Multi Load Image: up to 16 Load Image slots, each with its own IMAGE output.

const MAX = 16;
const SIZES = { S: [60, 104], M: [112, 150], L: [168, 210] };
const DEFAULT_VIEW = { layout: "list", size: "S", hover: true };
let filesCache = { at: 0, list: [] };

injectCss("jwtf-multiload", `
.jwtf-ml { gap: 6px; }
.jwtf-ml-slots { display: flex; flex-direction: column; gap: 4px; overflow: auto; flex: 1 1 auto; min-height: 0; }
.jwtf-ml-slots.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--cell), 1fr)); align-content: start; }
.jwtf-ml-slot { display: flex; gap: 6px; align-items: center; background: #15161a; border: 1px solid #2a2c33; border-radius: 6px; padding: 4px; }
.jwtf-ml-slots.grid .jwtf-ml-slot { flex-direction: column; align-items: stretch; }
.jwtf-ml-slot.drop { border-color: #5672b4; background: #1c2233; }
.jwtf-ml-th { position: relative; flex: none; width: var(--th); height: var(--th); border-radius: 5px; background: #0d0e11 center/contain no-repeat;
  border: 1px dashed #333; cursor: zoom-in; }
.jwtf-ml-slots.grid .jwtf-ml-th { width: 100%; height: auto; aspect-ratio: 1; }
.jwtf-ml-th.filled { border-style: solid; border-color: #2a2c33; }
.jwtf-ml-th .tag { position: absolute; left: 3px; top: 3px; font: 700 9px system-ui; padding: 1px 4px; border-radius: 4px; background: rgba(0,0,0,.7); }
.jwtf-ml-th .dim { position: absolute; right: 3px; bottom: 3px; font: 9px ui-monospace, monospace; padding: 0 3px; border-radius: 3px; background: rgba(0,0,0,.7); }
.jwtf-ml-ctl { display: flex; flex-direction: column; gap: 4px; flex: 1 1 auto; min-width: 0; }
.jwtf-ml-ctl select { font: inherit; color: #ddd; background: #121317; border: 1px solid #30333b; border-radius: 6px; padding: 2px; min-width: 0; width: 100%; }
.jwtf-ml-peek { position: fixed; z-index: 9999; pointer-events: none; background: #111; border: 1px solid #333; border-radius: 8px; padding: 6px;
  box-shadow: 0 8px 30px rgba(0,0,0,.6); font: 11px system-ui; color: #ddd; }
.jwtf-ml-peek img { display: block; max-width: 420px; max-height: 420px; }
.jwtf-ml-viewer { position: fixed; inset: 0; z-index: 10000; background: rgba(5,5,7,.94); overflow: hidden; cursor: grab; user-select: none; }
.jwtf-ml-viewer img { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.jwtf-ml-viewer img.px { image-rendering: pixelated; }
.jwtf-ml-viewer .bar { position: absolute; left: 0; right: 0; top: 0; display: flex; gap: 12px; padding: 8px 12px; font: 12px system-ui; color: #ddd;
  background: linear-gradient(rgba(0,0,0,.7), transparent); pointer-events: none; }
.jwtf-ml-viewer .nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 28px; background: rgba(0,0,0,.4); color: #fff;
  border: none; border-radius: 6px; padding: 6px 12px; cursor: pointer; }
`);

const splitName = (v) => {
    const clean = String(v ?? "").replace(/\s*\[(input|output|temp)\]$/, "");
    const i = clean.lastIndexOf("/");
    return i >= 0 ? { subfolder: clean.slice(0, i), filename: clean.slice(i + 1) } : { subfolder: "", filename: clean };
};
const shortName = (v, n = 18) => {
    const f = splitName(v).filename;
    return f.length > n ? f.slice(0, n - 1) + "…" : f;
};
const thumbUrl = (v) => {
    const { subfolder, filename } = splitName(v);
    return api.apiURL(`/view?${new URLSearchParams({ filename, subfolder, type: "input" })}`);
};

async function inputFiles(force = false) {
    if (!force && performance.now() - filesCache.at < 3000) return filesCache.list;
    try {
        const info = await (await api.fetchApi("/object_info/LoadImage")).json();
        const spec = info?.LoadImage?.input?.required?.image;
        const list = Array.isArray(spec?.[0]) ? spec[0] : spec?.[1]?.options ?? [];
        filesCache = { at: performance.now(), list: list.map(String) };
    } catch { /* keep old cache */ }
    return filesCache.list;
}

async function upload(file) {
    const body = new FormData();
    body.append("image", file, file.name);
    body.append("type", "input");
    const r = await api.fetchApi("/upload/image", { method: "POST", body });
    if (!r.ok) throw new Error(`upload failed (${r.status})`);
    const res = await r.json();
    return res.subfolder ? `${res.subfolder}/${res.name}` : res.name;
}

function setup(node) {
    const store = findWidget(node, "images_json");
    hideWidget(node, store);
    node.properties = node.properties ?? {};
    const view = () => ({ ...DEFAULT_VIEW, ...(node.properties.jwtf_mli_view ?? {}) });
    const setView = (patch) => { node.properties.jwtf_mli_view = { ...view(), ...patch }; render(); };

    let slots = [""];
    const dims = new Map();
    const read = () => {
        try {
            const v = JSON.parse(store?.value ?? "[]");
            return Array.isArray(v) ? v.map((x) => (typeof x === "string" ? x : "")).slice(0, MAX) : [];
        } catch { return []; }
    };
    const write = () => { if (store) store.value = JSON.stringify(slots); };

    // ---- outputs -------------------------------------------------------------------
    function syncOutputs() {
        while ((node.outputs?.length ?? 0) < slots.length) node.addOutput(`image_${node.outputs.length + 1}`, "IMAGE");
        slots.forEach((v, i) => {
            const o = node.outputs[i];
            if (!o) return;
            o.name = `image_${i + 1}`;
            o.label = v ? `P${i + 1} · ${shortName(v, 14)}` : `P${i + 1}`;
        });
    }
    function removeSlot(i) {
        if (slots.length <= 1) { slots = [""]; write(); render(); return; }
        slots.splice(i, 1);
        if (node.outputs?.[i]) node.removeOutput(i);
        write();
        render();
    }

    // ---- UI ------------------------------------------------------------------------
    const list = h("div.jwtf-ml-slots");
    const counter = h("span.jwtf-muted");
    const layoutBtn = h("button.jwtf-btn", { onclick: () => setView({ layout: view().layout === "list" ? "grid" : "list" }) });
    const sizeBtns = Object.keys(SIZES).map((s) => h("button.jwtf-btn", { textContent: s, onclick: () => setView({ size: s }) }));
    const hoverBtn = h("button.jwtf-btn", { textContent: "Peek", title: "Hover preview", onclick: () => setView({ hover: !view().hover }) });
    const refreshBtn = h("button.jwtf-btn", { textContent: "↻", title: "Refresh file list", onclick: async () => { await inputFiles(true); render(); } });
    const status = h("span.jwtf-muted.jwtf-grow", { style: { fontSize: "11px" } });
    let clearArmed = 0;
    const clearBtn = h("button.jwtf-btn", { textContent: "Clear all", onclick: () => {
        if (performance.now() - clearArmed < 2500) {
            clearArmed = 0;
            while (node.outputs.length > 1) node.removeOutput(node.outputs.length - 1);
            slots = [""];
            write();
            render();
        } else {
            clearArmed = performance.now();
            clearBtn.textContent = "Confirm?";
            setTimeout(() => (clearBtn.textContent = "Clear all"), 2500);
        }
    } });
    const fileInput = h("input", { type: "file", accept: "image/*", multiple: true, style: { display: "none" } });
    let uploadTarget = 0;
    fileInput.addEventListener("change", () => { addFiles([...fileInput.files], uploadTarget); fileInput.value = ""; });

    const root = h("div.jwtf-card.jwtf-ml", {},
        h("div.jwtf-row", {}, layoutBtn, ...sizeBtns, hoverBtn, h("span.jwtf-grow"), counter, refreshBtn),
        list,
        h("div.jwtf-row", {},
            h("button.jwtf-btn", { textContent: "+ Slot", onclick: () => { if (slots.length < MAX) { slots.push(""); write(); render(); } } }),
            h("button.jwtf-btn", { textContent: "Paste", onclick: () => pasteFromClipboard() }),
            h("button.jwtf-btn", { textContent: "− Last", onclick: () => removeSlot(slots.length - 1) }),
            clearBtn, status),
        fileInput);

    const say = (t) => { status.textContent = t; clearTimeout(say._t); say._t = setTimeout(() => (status.textContent = ""), 3000); };

    async function addFiles(files, start) {
        const imgs = files.filter((f) => f.type.startsWith("image/"));
        let target = start;
        for (const f of imgs) {
            while (target < slots.length && target !== start && slots[target]) target++;
            if (target >= MAX) { say("16 slot limit reached"); break; }
            try {
                const name = await upload(f);
                if (target >= slots.length) slots.push(name);
                else slots[target] = name;
                target++;
            } catch (e) { say(String(e.message ?? e)); }
        }
        write();
        await inputFiles(true);
        render();
    }
    const firstEmpty = () => { const i = slots.indexOf(""); return i >= 0 ? i : slots.length; };

    async function pasteFromClipboard() {
        try {
            const items = await navigator.clipboard.read();
            const files = [];
            let k = 0;
            for (const it of items) {
                const type = it.types.find((t) => t.startsWith("image/"));
                if (!type) continue;
                const blob = await it.getType(type);
                files.push(new File([blob], `pasted_${Date.now()}_${k++}.${type.split("/")[1] || "png"}`, { type }));
            }
            if (!files.length) return say("No image on the clipboard");
            addFiles(files, firstEmpty());
        } catch {
            say("Clipboard blocked; hover the node and press Ctrl+V");
        }
    }

    // window-level paste while the pointer is over this node
    let hovering = false;
    root.addEventListener("pointerenter", () => (hovering = true));
    root.addEventListener("pointerleave", () => (hovering = false));
    const onPaste = (e) => {
        if (!hovering) return;
        const files = [...(e.clipboardData?.files ?? [])].filter((f) => f.type.startsWith("image/"));
        if (!files.length) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        addFiles(files.map((f, k) => new File([f], `pasted_${Date.now()}_${k}.${f.type.split("/")[1] || "png"}`, { type: f.type })), firstEmpty());
    };
    window.addEventListener("paste", onPaste, true);

    // ---- hover peek -----------------------------------------------------------------------
    let peekEl = null, peekTimer = 0;
    const hidePeek = () => { clearTimeout(peekTimer); peekEl?.remove(); peekEl = null; };
    function peek(th, i) {
        if (!view().hover || !slots[i]) return;
        peekTimer = setTimeout(() => {
            const r = th.getBoundingClientRect();
            const d = dims.get(slots[i]);
            peekEl = h("div.jwtf-ml-peek", {}, h("img", { src: thumbUrl(slots[i]) }),
                h("div", {}, `P${i + 1} · ${splitName(slots[i]).filename}${d ? ` · ${d[0]}×${d[1]}` : ""}`));
            const left = r.right + 10 + 440 < window.innerWidth ? r.right + 10 : Math.max(4, r.left - 450);
            Object.assign(peekEl.style, { left: `${left}px`, top: `${Math.max(4, Math.min(r.top, window.innerHeight - 460))}px` });
            document.body.appendChild(peekEl);
        }, 320);
    }

    // ---- render ----------------------------------------------------------------------------
    async function render() {
        const v = view();
        const [thumb, cell] = SIZES[v.size] ?? SIZES.S;
        list.className = `jwtf-ml-slots${v.layout === "grid" ? " grid" : ""}`;
        list.style.setProperty("--th", `${thumb}px`);
        list.style.setProperty("--cell", `${cell}px`);
        layoutBtn.textContent = v.layout === "grid" ? "Grid" : "List";
        sizeBtns.forEach((b) => b.classList.toggle("on", b.textContent === v.size));
        hoverBtn.classList.toggle("on", !!v.hover);
        counter.textContent = `${slots.filter(Boolean).length} / ${MAX}`;
        syncOutputs();
        const files = filesCache.list;
        list.replaceChildren(...slots.map((val, i) => {
            const th = h("div.jwtf-ml-th", {}, h("span.tag", {}, `P${i + 1}`));
            if (val) {
                th.classList.add("filled");
                th.style.backgroundImage = `url("${thumbUrl(val)}")`;
                const d = dims.get(val);
                if (d) th.append(h("span.dim", {}, `${d[0]}×${d[1]}`));
                else {
                    const probe = new Image();
                    probe.onload = () => { dims.set(val, [probe.naturalWidth, probe.naturalHeight]); th.append(h("span.dim", {}, `${probe.naturalWidth}×${probe.naturalHeight}`)); };
                    probe.src = thumbUrl(val);
                }
                th.addEventListener("click", () => openViewer(i));
                th.addEventListener("pointerenter", () => peek(th, i));
                th.addEventListener("pointerleave", hidePeek);
            }
            const sel = h("select", {}, h("option", { value: "", textContent: "(empty)" }),
                ...(val && !files.includes(val) ? [h("option", { value: val, textContent: `${val} (not in input)` })] : []),
                ...files.map((f) => h("option", { value: f, textContent: f })));
            sel.value = val;
            sel.addEventListener("focus", async () => {
                const before = new Set(filesCache.list);
                for (const f of await inputFiles(true)) if (!before.has(f)) sel.append(h("option", { value: f, textContent: f }));
            });
            sel.addEventListener("change", () => { slots[i] = sel.value; write(); render(); });
            const tile = h("div.jwtf-ml-slot", {}, th, h("div.jwtf-ml-ctl", {}, sel, h("div.jwtf-row", {},
                h("button.jwtf-btn", { textContent: "Upload", onclick: () => { uploadTarget = i; fileInput.click(); } }),
                h("button.jwtf-btn", { textContent: "Clear", onclick: () => { slots[i] = ""; write(); render(); } }),
                h("button.jwtf-btn", { textContent: "✕", title: "Remove slot", onclick: () => removeSlot(i) }))));
            tile.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); tile.classList.add("drop"); });
            tile.addEventListener("dragleave", () => tile.classList.remove("drop"));
            tile.addEventListener("drop", (e) => {
                e.preventDefault();
                e.stopPropagation();
                tile.classList.remove("drop");
                addFiles([...(e.dataTransfer?.files ?? [])], i);
            });
            return tile;
        }));
        resize();
    }

    function resize() {
        const v = view();
        const [thumb, cell] = SIZES[v.size] ?? SIZES.S;
        const width = Math.max(node.size[0], 300) - 24;
        let body;
        if (v.layout === "grid") {
            const cols = Math.max(1, Math.floor(width / cell));
            body = Math.ceil(slots.length / cols) * (cell + 70);
        } else body = slots.length * (Math.max(thumb, 56) + 14);
        node._jwtfMlH = Math.min(900, body) + 80;
        const sz = node.computeSize();
        node.setSize([Math.max(node.size[0], 320), sz[1]]);
        node.setDirtyCanvas(true, true);
    }

    // ---- full-screen viewer (CSS renderer) -------------------------------------------------
    function openViewer(start) {
        const filled = slots.map((v, i) => [v, i]).filter(([v]) => v);
        let k = Math.max(0, filled.findIndex(([, i]) => i === start));
        const img = h("img");
        const info = h("span");
        const meta = h("span.jwtf-muted");
        const overlay = h("div.jwtf-ml-viewer", { tabIndex: 0 }, img, h("div.bar", {}, info, meta, h("span.jwtf-muted", {}, "css")),
            h("button.nav", { textContent: "‹", style: { left: "12px" }, onclick: (e) => { e.stopPropagation(); go(-1); } }),
            h("button.nav", { textContent: "›", style: { right: "12px" }, onclick: (e) => { e.stopPropagation(); go(1); } }));
        let zoom = 1, px = 0, py = 0, fitZoom = 1, nearest = false, drag = null;
        const apply = () => {
            img.style.transform = `translate(${px}px, ${py}px) scale(${zoom})`;
            img.classList.toggle("px", nearest);
            meta.textContent = `${img.naturalWidth}×${img.naturalHeight} · ${k + 1} / ${filled.length} · ${Math.round(zoom * 100)}%`;
        };
        const fit = () => {
            const W = window.innerWidth - 32, H = window.innerHeight - 32;
            fitZoom = Math.min(4, W / img.naturalWidth, H / img.naturalHeight);
            zoom = fitZoom;
            px = (window.innerWidth - img.naturalWidth * zoom) / 2;
            py = (window.innerHeight - img.naturalHeight * zoom) / 2;
            apply();
        };
        const zoomAt = (f, cx = window.innerWidth / 2, cy = window.innerHeight / 2) => {
            const nz = Math.min(64, Math.max(0.02, zoom * f));
            px = cx - ((cx - px) * nz) / zoom;
            py = cy - ((cy - py) * nz) / zoom;
            zoom = nz;
            apply();
        };
        const actual = () => zoomAt(1 / zoom);
        const go = (d) => {
            k = (k + d + filled.length) % filled.length;
            const [v, i] = filled[k];
            info.textContent = `P${i + 1} ${splitName(v).filename}`;
            img.onload = fit;
            img.src = thumbUrl(v);
        };
        const close = () => { overlay.remove(); window.removeEventListener("keydown", onKey, true); };
        const onKey = (e) => {
            e.stopPropagation();
            e.preventDefault();
            const key = e.key;
            if (key === "Escape") close();
            else if (key === "ArrowLeft") go(-1);
            else if (key === "ArrowRight") go(1);
            else if (key === "f" || key === "F") fit();
            else if (key === "1") actual();
            else if (key === "p" || key === "P") { nearest = !nearest; apply(); }
            else if (key === "+" || key === "=") zoomAt(1.25);
            else if (key === "-" || key === "_") zoomAt(0.8);
        };
        overlay.addEventListener("wheel", (e) => { e.preventDefault(); zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY); }, { passive: false });
        overlay.addEventListener("pointerdown", (e) => { if (e.target.closest(".nav")) return; drag = [e.clientX - px, e.clientY - py]; overlay.setPointerCapture(e.pointerId); });
        overlay.addEventListener("pointermove", (e) => { if (drag) { px = e.clientX - drag[0]; py = e.clientY - drag[1]; apply(); } });
        overlay.addEventListener("pointerup", () => (drag = null));
        overlay.addEventListener("dblclick", (e) => (Math.abs(zoom - fitZoom) < 1e-3 ? zoomAt(1 / zoom, e.clientX, e.clientY) : fit()));
        window.addEventListener("keydown", onKey, true);
        document.body.appendChild(overlay);
        overlay.focus();
        go(0);
    }

    node._jwtfMl = {
        render,
        configure() {
            const v = read();
            slots = v.length ? v : [""];
            write();
            render();
        },
        drop(files) { addFiles(files, firstEmpty()); },
        dispose() { window.removeEventListener("paste", onPaste, true); hidePeek(); },
    };

    while ((node.outputs?.length ?? 0) > 1) node.removeOutput(node.outputs.length - 1);
    write();
    node.addDOMWidget("jwtf_multiload", "jwtf_multiload", root, { serialize: false, getMinHeight: () => node._jwtfMlH ?? 160 });
    inputFiles().then(render);
    render();
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.MultiLoadImage",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "JWTFMultiLoadImage") return;
        chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
        chain(nodeType.prototype, "onConfigure", function () { this._jwtfMl?.configure(); });
        chain(nodeType.prototype, "onRemoved", function () { this._jwtfMl?.dispose(); });
        chain(nodeType.prototype, "onResize", function () { this._jwtfMl && requestAnimationFrame(() => this._jwtfMl.render()); });
        nodeType.prototype.onDragOver = function (e) {
            return !!e?.dataTransfer?.types?.includes?.("Files");
        };
        nodeType.prototype.onDragDrop = function (e) {
            const files = [...(e?.dataTransfer?.files ?? [])].filter((f) => f.type.startsWith("image/"));
            if (!files.length) return false;
            this._jwtfMl?.drop(files);
            return true;
        };
    },
});
