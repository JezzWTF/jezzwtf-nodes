// LoRA Inspector card for JWTFLoraInspector: Civitai lookup result shown on the node.
// The payload is cached in node.properties.nli_meta so the card re-renders on load without a request.
import { app } from "../../../scripts/app.js";
import {
    api, chain, copyText, findWidget, fitNode, getJson, h, injectCss, onWidget, toast,
} from "./_shared.js";

const NODE = "JWTFLoraInspector";
const EV_PROGRESS = "jezzwtf.lora_inspector.progress";
const EV_METADATA = "jezzwtf.lora_inspector.metadata";
const EV_ERROR = "jezzwtf.lora_inspector.error";
const PALETTE = ["#3b82f6", "#a855f7", "#14b8a6", "#f59e0b", "#ec4899", "#22c55e"];
const VIDEO_EXT = /\.(mp4|webm|mov|m4v)(?:[?#]|$)/i;

injectCss("jwtf-ml-inspector", `
.jwtf-li-title { font-weight: 600; font-size: 13px; color: #eee; word-break: break-word; }
.jwtf-li-bar { height: 5px; border-radius: 3px; background: #2a2c33; overflow: hidden; position: relative; }
.jwtf-li-bar > div { height: 100%; width: 0; background: #5672b4; transition: width .15s; }
.jwtf-li-bar.indeterminate > div { width: 100%; background: repeating-linear-gradient(45deg, #5672b4 0 10px, #3c4f7a 10px 20px);
  background-size: 28px 28px; animation: jwtf-li-stripe .8s linear infinite; }
@keyframes jwtf-li-stripe { to { background-position: 28px 0; } }
.jwtf-li-badge { font-size: 10px; padding: 1px 7px; border-radius: 9px; background: #2d3a55; color: #b8c8f0; }
.jwtf-li-badge.nsfw { background: #5a2330; color: #fca5a5; }
.jwtf-li-strip { position: relative; }
.jwtf-li-scroll { display: flex; gap: 6px; overflow-x: auto; scroll-snap-type: x mandatory; scrollbar-width: none; }
.jwtf-li-scroll::-webkit-scrollbar { display: none; }
.jwtf-li-item { position: relative; flex: none; width: 120px; height: 150px; border-radius: 6px; overflow: hidden;
  scroll-snap-align: start; background: #121317; cursor: pointer; }
.jwtf-li-item img, .jwtf-li-item video { width: 100%; height: 100%; object-fit: cover; display: block; }
.jwtf-li-item .tag { position: absolute; left: 3px; bottom: 3px; font-size: 9px; padding: 0 5px; border-radius: 6px;
  background: rgba(0,0,0,.65); color: #ddd; }
.jwtf-li-nav { position: absolute; top: 50%; transform: translateY(-50%); width: 22px; height: 40px; border: 0;
  border-radius: 6px; background: rgba(0,0,0,.6); color: #fff; cursor: pointer; z-index: 1; }
.jwtf-li-nav:disabled { opacity: .25; cursor: default; }
.jwtf-li-info { display: grid; grid-template-columns: auto 1fr; gap: 1px 10px; font-size: 11px; }
.jwtf-li-info dt { color: #8b8f99; } .jwtf-li-info dd { margin: 0; color: #cfd2da; word-break: break-word; }
.jwtf-li-desc { font-size: 11px; color: #9aa0ad; line-height: 1.4; user-select: text; }
.jwtf-li-foot { font-size: 10px; color: #7d8190; display: flex; gap: 8px; align-items: center; }
.jwtf-li-foot a { color: #8fb0ff; text-decoration: none; }
.jwtf-li-msg { font-size: 11px; color: #9aa0ad; }
.jwtf-li-msg.err { color: #fb7185; }
`);

function hashColor(s) {
    let hsh = 0;
    for (let i = 0; i < s.length; i++) hsh = (Math.imul(hsh, 31) + s.charCodeAt(i)) >>> 0;
    return PALETTE[hsh % 6];
}

// Only https URLs on civitai.com (or a subdomain) are ever rendered; nli_meta comes from the
// saved workflow and is untrusted.
function civitaiUrl(value) {
    if (typeof value !== "string") return null;
    try {
        const u = new URL(value.trim());
        const host = u.hostname.toLowerCase();
        if (u.protocol !== "https:" || !(host === "civitai.com" || host.endsWith(".civitai.com"))) return null;
        return u.href;
    } catch {
        return null;
    }
}

function mediaType(img) {
    if (img.type === "video" || img.type === "image") return img.type;
    return VIDEO_EXT.test(img.url ?? "") ? "video" : "image";
}

function setupInspector(node) {
    const loraW = findWidget(node, "lora_name");
    const sourceW = findWidget(node, "source");

    let payload = node.properties?.nli_meta ?? null;
    let busy = false;
    let queued = null; // {force}
    let debounce = 0;
    let stage = "";
    let message = "";
    let isError = false;

    const dot = h("span.jwtf-ml-dot");
    const title = h("b.jwtf-ml-grow", {}, "LoRA Inspector");
    const stageEl = h("span.jwtf-ml-muted", {}, "");
    const inspectBtn = h("button.jwtf-ml-btn", { title: "Inspect (uses cache)" }, "Inspect");
    const forceBtn = h("button.jwtf-ml-btn", { title: "Force refresh from Civitai" }, "Refresh");
    const bar = h("div.jwtf-li-bar", {}, h("div"));
    const msgEl = h("div.jwtf-li-msg");
    const card = h("div");
    const root = h("div.jwtf-ml", { style: { userSelect: "text" } },
        h("div.jwtf-ml-row", {}, dot, title, stageEl, inspectBtn, forceBtn), bar, msgEl, card);

    const setProgress = (value, indeterminate) => {
        bar.classList.toggle("indeterminate", !!indeterminate);
        bar.firstChild.style.width = indeterminate ? "100%" : `${Math.round(clamp01(value) * 100)}%`;
    };
    const clamp01 = (v) => Math.max(0, Math.min(1, Number(v) || 0));

    function renderStatus() {
        dot.className = "jwtf-ml-dot" + (isError ? " err" : busy ? " busy" : payload ? " live" : "");
        stageEl.textContent = stage ? `${stage}${stage === "done" ? "" : "..."}` : "";
        msgEl.textContent = message;
        msgEl.className = "jwtf-li-msg" + (isError ? " err" : "");
        msgEl.style.display = message ? "" : "none";
        inspectBtn.disabled = busy;
        forceBtn.disabled = busy;
    }

    function copyChip(text, label) {
        return h("button.jwtf-ml-chip", { title: "Click to copy", onclick: async () => {
            toast((await copyText(text)) ? "Copied" : "Copy failed", "ok");
        } }, label ?? text);
    }

    function renderCard() {
        card.replaceChildren();
        if (!payload) return;
        const p = payload;
        const local = p.local ?? {};
        const name = p.model_name || local.modelspec_title || p.lora_file;
        card.style.cssText = "display:flex;flex-direction:column;gap:6px";

        const badges = h("div.jwtf-ml-row.jwtf-ml-wrap", {});
        for (const b of [p.version_name, p.model_type, p.format]) if (b) badges.append(h("span.jwtf-li-badge", {}, b));
        if (p.nsfw) badges.append(h("span.jwtf-li-badge.nsfw", {}, "NSFW"));
        const base = p.base_model || local.base_model_version;
        if (base) badges.append(h("span.jwtf-li-badge", { style: { background: hashColor(String(base)), color: "#fff" } }, base));
        card.append(h("div.jwtf-li-title", {}, name), badges);

        const words = Array.isArray(p.trigger_words) ? p.trigger_words : [];
        if (words.length) {
            const row = h("div.jwtf-ml-row.jwtf-ml-wrap", {}, words.map((w) => copyChip(w)));
            if (words.length >= 2) row.append(h("button.jwtf-ml-btn", { onclick: async () => {
                toast((await copyText(words.join(", "))) ? "Copied all" : "Copy failed", "ok");
            } }, "Copy all"));
            card.append(row);
        } else if (p.found) {
            card.append(h("div.jwtf-ml-muted", {}, "No trigger words listed"));
        }

        const images = (Array.isArray(p.images) ? p.images : []).filter((i) => civitaiUrl(i?.url));
        if (images.length) card.append(buildStrip(images));

        const rows = [
            ["File", p.lora_file],
            ["Training", [local.resolution, local.clip_skip != null ? `clip skip ${local.clip_skip}` : null,
                local.steps != null ? `${local.steps} steps` : null].filter(Boolean).join(" · ")],
            ["Stats", [p.downloads != null ? `${Number(p.downloads).toLocaleString()} downloads` : null,
                p.rating != null ? `rating ${Number(p.rating).toFixed(1)}` : null,
                p.file_size_kb != null ? `${(p.file_size_kb / 1024).toFixed(1)} MB` : null].filter(Boolean).join(" · ")],
        ].filter(([, v]) => v);
        if (rows.length) card.append(h("dl.jwtf-li-info", {}, rows.flatMap(([k, v]) => [h("dt", {}, k), h("dd", {}, v)])));
        if (p.description) {
            card.append(h("div.jwtf-li-desc", {}, p.description.length > 200 ? `${p.description.slice(0, 200)}...` : p.description));
        }
        const foot = h("div.jwtf-li-foot", {}, h("span", {}, p.source || "local only"),
            p.sha256 ? h("span", { title: p.sha256 }, String(p.sha256).slice(0, 10)) : null);
        const pageUrl = civitaiUrl(p.url);
        if (pageUrl) foot.append(h("a", { href: pageUrl, target: "_blank", rel: "noopener noreferrer" }, "Civitai"));
        card.append(foot);
    }

    function buildStrip(images) {
        const scroll = h("div.jwtf-li-scroll");
        for (const raw of images) {
            const url = civitaiUrl(raw?.url);
            if (!url) continue;
            const img = { ...raw, url };
            const type = mediaType(img);
            const media = type === "video"
                ? h("video", { src: `${img.url}#t=0.1`, muted: true, loop: true, preload: "metadata", playsInline: true,
                    referrerPolicy: "no-referrer" })
                : h("img", { src: img.url, loading: "lazy", referrerPolicy: "no-referrer", draggable: false });
            const item = h("div.jwtf-li-item", {}, media,
                img.nsfw && img.nsfw !== "None" ? h("span.tag", {}, `NSFW ${img.nsfw}`) : null);
            media.addEventListener("error", () => { item.style.display = "none"; });
            if (type === "video") {
                item.addEventListener("mouseenter", () => media.play().catch(() => {}));
                item.addEventListener("mouseleave", () => { media.pause(); media.currentTime = 0; });
            }
            item.addEventListener("click", async () => {
                const prompt = img.meta?.prompt ?? img.meta?.Prompt;
                if (!prompt) { toast("No prompt on this sample", "warn"); return; }
                toast((await copyText(String(prompt))) ? "Prompt copied" : "Copy failed", "ok");
            });
            scroll.append(item);
        }
        const prev = h("button.jwtf-li-nav", { style: { left: "2px" }, onclick: () => scroll.scrollBy({ left: -192, behavior: "smooth" }) }, "‹");
        const next = h("button.jwtf-li-nav", { style: { right: "2px" }, onclick: () => scroll.scrollBy({ left: 192, behavior: "smooth" }) }, "›");
        const ends = () => {
            prev.disabled = scroll.scrollLeft <= 1;
            next.disabled = scroll.scrollLeft + scroll.clientWidth >= scroll.scrollWidth - 1;
        };
        scroll.addEventListener("scroll", ends, { passive: true });
        scroll.addEventListener("wheel", (e) => {
            if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { e.preventDefault(); scroll.scrollLeft += e.deltaY; }
        }, { passive: false });
        setTimeout(ends, 50);
        return h("div.jwtf-li-strip", {}, prev, scroll, next);
    }

    function render() {
        renderStatus();
        renderCard();
        requestAnimationFrame(fit);
    }

    let panelH = 120;
    function fit() {
        panelH = Math.max(80, root.offsetHeight + 2);
        fitNode(node, 340);
    }

    async function inspect(force) {
        const lora = String(loraW?.value ?? "");
        if (!lora || lora === "undefined") return;
        if (busy) { queued = { force: force || !!queued?.force }; return; }
        busy = true;
        isError = false;
        message = "";
        stage = "start";
        setProgress(0, false);
        render();
        try {
            const result = await getJson("/jezzwtf/lora_inspector/inspect", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ lora, source: String(sourceW?.value ?? "auto"), client_id: String(api.clientId ?? ""),
                    node: String(node.id), force: force ? "1" : "0" }),
            });
            applyPayload(result);
        } catch (err) {
            isError = true;
            message = String(err?.message ?? err);
            stage = "";
            setProgress(0, false);
        } finally {
            busy = false;
            render();
            if (queued) { const q = queued; queued = null; inspect(q.force); }
        }
    }

    function applyPayload(result) {
        payload = result;
        node.properties = node.properties ?? {};
        node.properties.nli_meta = result;
        if (result?.warning) { isError = true; message = result.warning; } else { isError = false; message = ""; }
        stage = "done";
        setProgress(1, false);
    }

    inspectBtn.addEventListener("click", () => inspect(false));
    forceBtn.addEventListener("click", () => inspect(true));
    onWidget(loraW, () => {
        clearTimeout(debounce);
        debounce = setTimeout(() => inspect(false), 400);
    });

    node._jwtfEvent = (kind, d) => {
        if (kind === "progress") {
            stage = d.stage;
            if (d.stage === "fetch" && Number(d.value) === 0) setProgress(0, true);
            else setProgress(d.stage === "done" ? 1 : d.value, false);
            renderStatus();
            stageEl.title = d.message ?? "";
        } else if (kind === "metadata") {
            applyPayload(d.payload);
            render();
        } else if (kind === "error") {
            isError = true;
            message = d.message ?? "error";
            stage = "";
            render();
        }
    };
    node._jwtfSync = () => {
        payload = node.properties?.nli_meta ?? payload;
        render();
    };

    const widget = node.addDOMWidget("nli_panel", "nli_panel", root, { serialize: false, getMinHeight: () => panelH, hideOnZoom: false });
    widget.computeSize = (w) => [w, panelH];
    new ResizeObserver(() => requestAnimationFrame(fit)).observe(root);
    node.setSize([Math.max(node.size[0], 360), node.size[1]]);
    render();
}

function route(kind) {
    return (ev) => {
        const d = ev.detail ?? {};
        const node = app.graph?.getNodeById?.(Number(d.node)) ?? app.graph?.getNodeById?.(d.node);
        if (node?.comfyClass === NODE) node._jwtfEvent?.(kind, d);
    };
}

app.registerExtension({
    name: "JezzWTF.ModelLoaders.LoraInspector",
    setup() {
        api.addEventListener(EV_PROGRESS, route("progress"));
        api.addEventListener(EV_METADATA, route("metadata"));
        api.addEventListener(EV_ERROR, route("error"));
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        chain(nodeType.prototype, "onNodeCreated", function () { setupInspector(this); });
        chain(nodeType.prototype, "onConfigure", function () { setTimeout(() => this._jwtfSync?.(), 0); });
    },
});
