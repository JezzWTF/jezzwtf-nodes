// LM Studio Bridge console + LM Studio Prompt Box panels.
import { app } from "../../../scripts/app.js";
import {
    api, BASE_CSS, copyText, findWidget, fitNode, h, hideWidget, injectCss, makeGrip, shieldKeys, uploadToInput, viewUrl,
} from "./jwtf_ui.js";

const BRIDGE = "JWTFLMStudio";
const BOX = "JWTFLMStudioPromptBox";
const EVENT = "jezzwtf.lmstudio.progress";
const DEFAULT_URL = "http://127.0.0.1:1234";
const INT_DEFAULTS = { video_frames: 8, max_tokens: 512, seed: 0 };
const PREVIEW_H = 64;

injectCss("jwtf-llm-base", BASE_CSS);
injectCss("jwtf-lms", `
.jwtf-lms .tail{padding:2px 8px 6px;min-height:2.8em;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;opacity:.85;white-space:pre-wrap;word-break:break-word}
.jwtf-lms .rate{font-variant-numeric:tabular-nums;opacity:.75}
.jwtf-lms .drop{margin:0 6px 6px;border:1px dashed #555;border-radius:5px;display:flex;align-items:center;justify-content:center;
 min-height:28px;cursor:pointer;opacity:.75;position:relative}
.jwtf-lms .drop.over{border-color:#4a8fe0;opacity:1;background:rgba(74,143,224,.08)}
.jwtf-lms .prev{margin:0 6px;position:relative;border-radius:5px;overflow:hidden;background:#111}
.jwtf-lms .prev img{width:100%;height:100%;object-fit:cover;display:block;cursor:pointer}
.jwtf-lms .prev img.contain{object-fit:contain}
.jwtf-lms .prev .tools{position:absolute;top:3px;right:3px;display:flex;gap:3px}
.jwtf-lms .prev .tools button{padding:0 5px;opacity:.85}
.jwtf-lightbox{position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;cursor:zoom-out}
.jwtf-lightbox img{max-width:95vw;max-height:95vh}
.jwtf-box .out{padding:6px 8px;overflow:auto;white-space:pre-wrap;word-break:break-word;transition:background .4s}
.jwtf-box .out.flash{background:rgba(74,143,224,.18)}
`);

const bridges = new Set(); // live bridge nodes (ids can change when a node is added to a graph)

function controllerFor(id) {
    const key = String(id);
    const tail = key.split(":").pop(); // subgraph execution ids look like "outer:inner"
    let match = null;
    for (const n of bridges) {
        if (String(n.id) === key) return n._jwtfLms;
        if (String(n.id) === tail) match = n._jwtfLms;
    }
    return match;
}

// --------------------------------------------------------------------------- bridge console

function setupBridge(node) {
    const status = h("span", { class: "jwtf-grow jwtf-ellipsis", text: "Idle" });
    const led = h("span", { class: "jwtf-led" });
    const rate = h("span", { class: "rate" });
    const bar = h("div", { class: "jwtf-bar" }, [h("i")]);
    const tail = h("div", { class: "tail jwtf-muted" });
    const modelsBtn = h("button", { class: "jwtf-btn", text: "models", title: "Fetch models from the server" });
    const stopBtn = h("button", { class: "jwtf-btn", text: "stop", title: "Interrupt the queue", onclick: () => api.interrupt() });
    const fileInput = h("input", { type: "file", accept: "image/*", style: { display: "none" } });
    const img = h("img", { draggable: "false" });
    const prev = h("div", { class: "prev", style: { display: "none", height: `${PREVIEW_H}px` } }, [img]);
    const drop = h("div", { class: "drop", text: "Drop, paste or click to attach an image" });
    const panel = h("div", { class: "jwtf-panel jwtf-lms" }, [
        h("div", { class: "jwtf-row" }, [led, status, rate, modelsBtn, stopBtn]),
        bar, tail, prev, drop, fileInput,
    ]);
    const grip = makeGrip(prev, {
        min: 48, max: 480, initial: PREVIEW_H,
        onChange: (hgt, final) => {
            if (!final) return;
            const info = readEmbedded();
            if (info) writeEmbedded({ ...info, h: hgt });
            fitNode(node);
        },
    });
    prev.after(grip);
    grip.style.display = "none";

    const state = { t0: 0, tFirst: 0, tokens: 0, max: 0 };
    let modelCursor = -1;

    function setLed(kind) {
        led.className = `jwtf-led ${kind || ""}`;
    }
    function setBar(kind, frac) {
        bar.className = `jwtf-bar ${kind || ""}`;
        bar.firstChild.style.width = frac == null ? "" : `${Math.max(0, Math.min(1, frac)) * 100}%`;
    }

    // ---- embedded image
    const embeddedWidget = () => findWidget(node, "embedded_image");
    function readEmbedded() {
        const raw = embeddedWidget()?.value;
        if (!raw || !String(raw).trim()) return null;
        try {
            return JSON.parse(raw);
        } catch {
            return null;
        }
    }
    function writeEmbedded(info) {
        const w = embeddedWidget();
        if (w) w.value = info ? JSON.stringify(info) : "";
        showPreview();
    }
    function showPreview() {
        const info = readEmbedded();
        prev.style.display = info ? "" : "none";
        grip.style.display = info ? "" : "none";
        drop.textContent = info ? "Drop, paste or click to replace" : "Drop, paste or click to attach an image";
        if (info) {
            prev.style.height = `${info.h || PREVIEW_H}px`;
            img.src = viewUrl(info);
        }
        fitNode(node);
    }
    async function attach(file) {
        if (!file || !file.type.startsWith("image/")) return;
        try {
            status.textContent = "Uploading image…";
            const res = await uploadToInput(file, "jezzwtf_lms", { unique: true });
            const old = readEmbedded();
            writeEmbedded({ name: res.name, subfolder: res.subfolder ?? "jezzwtf_lms", type: res.type ?? "input",
                ...(old?.h ? { h: old.h } : {}) });
            status.textContent = `Attached ${res.name}`;
        } catch (err) {
            setLed("error");
            status.textContent = String(err.message || err);
        }
    }

    const tools = h("div", { class: "tools" }, [
        h("button", { class: "jwtf-btn", text: "⤢", title: "Expand", onclick: (e) => { e.stopPropagation(); lightbox(img.src); } }),
        h("button", { class: "jwtf-btn", text: "×", title: "Remove", onclick: (e) => { e.stopPropagation(); writeEmbedded(null); } }),
    ]);
    prev.append(tools);
    img.addEventListener("click", () => img.classList.toggle("contain"));
    img.addEventListener("dblclick", () => fileInput.click());
    drop.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
        attach(fileInput.files?.[0]);
        fileInput.value = "";
    });
    panel.addEventListener("dragover", (e) => {
        if ([...(e.dataTransfer?.items || [])].some((i) => i.kind === "file")) {
            e.preventDefault();
            e.stopPropagation();
            drop.classList.add("over");
        }
    });
    panel.addEventListener("dragleave", () => drop.classList.remove("over"));
    panel.addEventListener("drop", (e) => {
        const file = [...(e.dataTransfer?.files || [])].find((f) => f.type.startsWith("image/"));
        drop.classList.remove("over");
        if (!file) return;
        e.preventDefault();
        e.stopPropagation();
        attach(file);
    });
    let hovering = false;
    panel.addEventListener("pointerenter", () => (hovering = true));
    panel.addEventListener("pointerleave", () => (hovering = false));
    const onPaste = (e) => {
        if (!hovering) return;
        const tag = document.activeElement?.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return;
        const file = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith("image/"));
        if (!file) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        attach(file);
    };
    document.addEventListener("paste", onPaste, true);

    // ---- model refresh
    modelsBtn.addEventListener("click", async () => {
        const base = (findWidget(node, "server_url")?.value || DEFAULT_URL).trim().replace(/\/+$/, "") || DEFAULT_URL;
        setLed("busy");
        status.textContent = "Fetching models…";
        let names = [];
        let error = "";
        try {
            const r = await fetch(`${base}/v1/models`);
            const data = await r.json();
            names = (data.data || []).map((m) => m.id).filter(Boolean);
        } catch {
            try {
                const r = await api.fetchApi(`/jezzwtf/lmstudio/models?base=${encodeURIComponent(base)}`);
                const data = await r.json();
                names = data.models || [];
                error = data.error || "";
            } catch (err) {
                error = String(err.message || err);
            }
        }
        if (!names.length) {
            setLed("error");
            status.textContent = error ? `No models: ${error}` : "No models found";
            return;
        }
        const w = findWidget(node, "model_name");
        const current = names.indexOf(w?.value);
        modelCursor = ((current >= 0 ? current : modelCursor) + 1) % names.length;
        if (w) {
            w.value = names[modelCursor];
            w.callback?.(w.value);
        }
        setLed("done");
        status.textContent = `${names.length} model${names.length === 1 ? "" : "s"} · ${names[modelCursor]}`;
        node.setDirtyCanvas(true, true);
    });

    // ---- progress
    const controller = {
        queued() {
            setLed("busy");
            setBar("indet");
            status.textContent = "Queued";
            rate.textContent = "";
        },
        event(d) {
            const now = performance.now();
            if (d.state === "start") {
                Object.assign(state, { t0: now, tFirst: 0, tokens: 0, max: d.max_tokens || 0 });
                const m = d.media || {};
                const media = [m.image && `${m.image} img`, m.video && `${m.video} frames`, m.audio && `${m.audio} audio`]
                    .filter(Boolean).join(", ");
                setLed("busy");
                setBar("indet");
                status.textContent = `Rendering · ${d.model}${media ? ` · ${media}` : ""}`;
                tail.textContent = "";
                rate.textContent = "";
            } else if (d.state === "stream") {
                if (!state.tFirst) state.tFirst = now;
                state.tokens = d.tokens;
                setLed("live");
                if (state.max > 0) setBar("live", d.tokens / state.max);
                else setBar("live indet");
                status.textContent = `Streaming · ${d.tokens}${state.max ? ` / ${state.max}` : ""}`;
                const elapsed = (now - state.t0) / 1000;
                const ttft = ((state.tFirst - state.t0) / 1000).toFixed(2);
                rate.textContent = elapsed < 0.3 ? `TTFT ${ttft}s` : `${(d.tokens / elapsed).toFixed(1)} tok/s · TTFT ${ttft}s`;
                tail.textContent = d.tail || "";
            } else if (d.state === "done") {
                setLed("done");
                setBar("done");
                status.textContent = `Done · ${d.tokens} tokens in ${Number(d.elapsed).toFixed(2)}s`;
                if (d.elapsed > 0 && d.tokens) rate.textContent = `${(d.tokens / d.elapsed).toFixed(1)} tok/s`;
                tail.textContent = d.tail || "";
            } else if (d.state === "error") {
                setLed("error");
                setBar("error");
                status.textContent = `Error: ${d.error}`;
                rate.textContent = "";
            }
        },
        restore: showPreview,
        dispose() {
            document.removeEventListener("paste", onPaste, true);
        },
    };

    const widget = node.addDOMWidget("lms_console", "jwtf_lms_console", panel, {
        serialize: false,
        getMinHeight: () => panel.scrollHeight || 110,
    });
    widget.serialize = false;
    shieldKeys(panel);
    hideWidget(node, "embedded_image");
    return controller;
}

function lightbox(src) {
    const box = h("div", { class: "jwtf-lightbox" }, [h("img", { src })]);
    const close = () => {
        box.remove();
        window.removeEventListener("keydown", onKey, true);
    };
    const onKey = (e) => {
        if (e.key === "Escape") {
            e.stopPropagation();
            close();
        }
    };
    box.addEventListener("click", close);
    window.addEventListener("keydown", onKey, true);
    document.body.appendChild(box);
}

function sanitiseInts(node) {
    for (const [name, def] of Object.entries(INT_DEFAULTS)) {
        const w = findWidget(node, name);
        if (!w || w._jwtfSanitised) continue;
        w._jwtfSanitised = true;
        w.serializeValue = () => {
            const v = Number(w.value);
            return w.value === "" || w.value == null || !Number.isFinite(v) ? def : v;
        };
    }
}

// --------------------------------------------------------------------------- prompt box

function setupBox(node) {
    const led = h("span", { class: "jwtf-led" });
    const chip = h("span", { class: "jwtf-chip", text: "LOCAL" });
    const count = h("span", { class: "jwtf-grow jwtf-muted", text: "0 chars" });
    const out = h("div", { class: "out jwtf-muted", text: "Run the graph to see the combined prompt." });
    const copy = h("button", {
        class: "jwtf-btn", text: "copy",
        onclick: async () => {
            const ok = await copyText(out.dataset.value || "");
            copy.textContent = ok ? "copied" : "failed";
            setTimeout(() => (copy.textContent = "copy"), 1200);
        },
    });
    node.properties = node.properties || {};
    const height = () => Number(node.properties.lms_box_h) || 132;
    out.style.height = `${height()}px`;
    const panel = h("div", { class: "jwtf-panel jwtf-box" }, [h("div", { class: "jwtf-row" }, [led, chip, count, copy]), out]);
    panel.append(makeGrip(out, {
        min: 48, max: 480, initial: 132,
        onChange: (hgt, final) => {
            node.properties.lms_box_h = hgt;
            if (final) fitNode(node);
        },
    }));
    const refreshChip = () => {
        const inp = node.inputs?.find((i) => i.name === "prompt_in");
        const linked = inp?.link != null;
        chip.textContent = linked ? "LINKED" : "LOCAL";
        chip.style.borderColor = linked ? "#4caf50" : "#555";
    };
    const widget = node.addDOMWidget("lms_box", "jwtf_lms_box", panel, {
        serialize: false,
        getMinHeight: () => height() + 40,
    });
    widget.serialize = false;
    shieldKeys(panel);
    return {
        refreshChip,
        restore() {
            out.style.height = `${height()}px`;
            refreshChip();
        },
        show(text) {
            out.dataset.value = text;
            out.textContent = text || "(empty)";
            out.classList.toggle("jwtf-muted", !text);
            count.textContent = `${text.length} chars`;
            led.className = "jwtf-led done";
            out.classList.add("flash");
            setTimeout(() => out.classList.remove("flash"), 450);
        },
    };
}

// --------------------------------------------------------------------------- registration

let promptHooked = false;
function hookGraphToPrompt() {
    if (promptHooked) return;
    promptHooked = true;
    const orig = app.graphToPrompt;
    app.graphToPrompt = async function (...args) {
        const res = await orig.apply(this, args);
        try {
            for (const [id, entry] of Object.entries(res?.output || {})) {
                if (entry?.class_type !== BRIDGE) continue;
                const node = app.graph.getNodeById(Number(id)) ?? app.graph.getNodeById(id);
                const w = node && findWidget(node, "embedded_image");
                if (w) entry.inputs.embedded_image = w.value ?? "";
            }
        } catch (err) {
            console.warn("[JezzWTF LM Studio] could not patch the prompt", err);
        }
        return res;
    };
}

app.registerExtension({
    name: "JezzWTF.LLMCards.LMStudio",

    setup() {
        hookGraphToPrompt();
        api.addEventListener(EVENT, (e) => controllerFor(e.detail?.node)?.event(e.detail));
        api.addEventListener("execution_start", () => {
            for (const n of bridges) n._jwtfLms?.queued();
        });
    },

    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name === BRIDGE) {
            const created = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = created?.apply(this, arguments);
                this._jwtfLms = setupBridge(this);
                sanitiseInts(this);
                bridges.add(this);
                if (this.size[0] < 360) this.setSize([360, this.size[1]]);
                return r;
            };
            const configure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                const r = configure?.apply(this, arguments);
                // Saved widget values are applied by now, so the preview can come back on reload.
                this._jwtfLms?.restore();
                return r;
            };
            const removed = nodeType.prototype.onRemoved;
            nodeType.prototype.onRemoved = function () {
                this._jwtfLms?.dispose();
                bridges.delete(this);
                return removed?.apply(this, arguments);
            };
        }
        if (nodeData.name === BOX) {
            const created = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = created?.apply(this, arguments);
                this._jwtfBox = setupBox(this);
                this._jwtfBox.refreshChip();
                return r;
            };
            const configure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                const r = configure?.apply(this, arguments);
                this._jwtfBox?.restore();
                return r;
            };
            const conn = nodeType.prototype.onConnectionsChange;
            nodeType.prototype.onConnectionsChange = function () {
                const r = conn?.apply(this, arguments);
                this._jwtfBox?.refreshChip();
                return r;
            };
            const executed = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                const r = executed?.apply(this, arguments);
                this._jwtfBox?.show(String(message?.text?.[0] ?? ""));
                return r;
            };
        }
    },
});
