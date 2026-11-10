import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, findWidget } from "./_shared.js";

// Refresh Page (VRAM cleaner): utility buttons plus a live VRAM ring gauge (Canvas2D).

const UI_KEY = "jezzwtf_vram";
const GB = 1024 ** 3;
const gauges = new Set();
let lastVram = null;
let pollTimer = 0;

async function pollOnce() {
    try {
        lastVram = await (await api.fetchApi("/jezzwtf/vram")).json();
    } catch {
        lastVram = null;
    }
    for (const g of gauges) g.update(lastVram);
}

function ensurePolling() {
    const want = [...gauges].some((g) => g.visible) && !document.hidden;
    if (want && !pollTimer) {
        pollOnce();
        pollTimer = setInterval(pollOnce, 2000);
    } else if (!want && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = 0;
    }
}
document.addEventListener("visibilitychange", ensurePolling);

function rampColor(t) {
    // green -> yellow -> pink
    const stops = [[74, 222, 128], [250, 204, 21], [244, 63, 145]];
    const x = Math.min(1, Math.max(0, t)) * 2;
    const i = Math.min(1, Math.floor(x));
    const f = x - i;
    const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
    return `rgb(${c.join(",")})`;
}

function flashLabel(w, text, ms, original) {
    w.name = text;
    w.label = text;
    app.graph?.setDirtyCanvas(true, false);
    clearTimeout(w._jwtfT);
    if (ms) w._jwtfT = setTimeout(() => { w.name = original; w.label = original; app.graph?.setDirtyCanvas(true, false); }, ms);
}

function setup(node) {
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "width:100%;height:100%;display:block;border-radius:8px;background:#0e0f12;";
    const g = {
        visible: false, data: null, used: 0, target: 0, clean: null, cleanAt: 0, ripple: 0, raf: 0, lastFrame: 0,
        update(d) { this.data = d; this.target = d && d.total ? d.used / d.total : 0; kick(); },
    };
    gauges.add(g);

    const btn = (label, fn) => {
        const w = node.addWidget("button", label, null, () => fn(w), { serialize: false });
        return w;
    };
    btn("Reload models", async (w) => {
        const orig = "Reload models";
        flashLabel(w, "Reloading…", 0, orig);
        try {
            const cmd = app.extensionManager?.command;
            if (cmd?.execute) await cmd.execute("Comfy.RefreshNodeDefinitions");
            else if (app.refreshComboInNodes) await app.refreshComboInNodes();
            else return flashLabel(w, "Unsupported", 1500, orig);
            flashLabel(w, "Reloaded", 1500, orig);
        } catch {
            flashLabel(w, "Reload failed", 1500, orig);
        }
    });
    btn("Refresh page", () => location.reload());
    btn("Clean now", async (w) => {
        const orig = "Clean now";
        flashLabel(w, "Cleaning…", 0, orig);
        const val = (n, d) => findWidget(node, n)?.value ?? d;
        try {
            const r = await api.fetchApi("/jezzwtf/clean", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ vram: val("clean_vram", true), cache: val("clear_cache", true),
                    node_cache: val("clear_node_cache", false), kitchen: val("kitchen_backend", "leave as is") }),
            });
            if (r.status === 409) return flashLabel(w, "Busy", 1600, orig);
            if (!r.ok) throw new Error(String(r.status));
            showClean(await r.json());
            flashLabel(w, "Cleaned", 1600, orig);
        } catch {
            flashLabel(w, "Clean failed", 1600, orig);
        }
    });

    function showClean(stats) {
        g.clean = stats;
        g.cleanAt = performance.now();
        if (stats?.freed > 0) g.ripple = performance.now();
        pollOnce();
        kick();
    }

    function kick() {
        if (g.raf || !g.visible) return;
        const step = (t) => {
            g.raf = 0;
            if (t - g.lastFrame >= 33) {
                g.lastFrame = t;
                g.used += (g.target - g.used) * 0.12;
                paint(t);
            }
            const busy = Math.abs(g.target - g.used) > 0.001 || t - g.ripple < 1400 || t - g.cleanAt < 6000;
            if (busy && g.visible) g.raf = requestAnimationFrame(step);
        };
        g.raf = requestAnimationFrame(step);
    }

    function paint(t) {
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth, hgt = canvas.clientHeight;
        if (!w || !hgt) return;
        if (canvas.width !== Math.round(w * dpr)) canvas.width = Math.round(w * dpr);
        if (canvas.height !== Math.round(hgt * dpr)) canvas.height = Math.round(hgt * dpr);
        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, hgt);
        const d = g.data;
        const cx = w / 2, cy = hgt / 2 - 8, r = Math.max(10, Math.min(w, hgt - 40) / 2 - 10);
        const col = rampColor(g.used);
        ctx.lineCap = "round";
        ctx.lineWidth = Math.max(6, r * 0.14);
        ctx.strokeStyle = "#22242a";
        ctx.beginPath();
        ctx.arc(cx, cy, r, Math.PI * 0.75, Math.PI * 2.25);
        ctx.stroke();
        if (d?.total) {
            ctx.strokeStyle = col;
            ctx.shadowColor = col;
            ctx.shadowBlur = 12;
            ctx.beginPath();
            ctx.arc(cx, cy, r, Math.PI * 0.75, Math.PI * (0.75 + 1.5 * Math.max(0.005, g.used)));
            ctx.stroke();
            ctx.shadowBlur = 0;
        }
        const rp = (t - g.ripple) / 1400;
        if (rp >= 0 && rp < 1) {
            ctx.globalAlpha = 1 - rp;
            ctx.lineWidth = 2;
            ctx.strokeStyle = "#4ade80";
            ctx.beginPath();
            ctx.arc(cx, cy, r * (1 + rp * 0.4), 0, Math.PI * 2);
            ctx.stroke();
            ctx.globalAlpha = 1;
        }
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillStyle = "#f2f4f8";
        ctx.font = `700 ${Math.max(12, r * 0.28)}px ui-monospace, Consolas, monospace`;
        if (d?.total) {
            ctx.fillText(`${(d.used / GB).toFixed(1)} / ${(d.total / GB).toFixed(1)} GB`, cx, cy);
        } else {
            ctx.font = "600 12px system-ui";
            ctx.fillText(d ? "No CUDA device" : "VRAM unavailable", cx, cy);
        }
        ctx.font = "11px system-ui";
        ctx.fillStyle = "#9aa0ab";
        let sub = d?.total ? `${Math.round((d.used / d.total) * 100)}% used` : "";
        if (g.clean && t - g.cleanAt < 6000) {
            const c = g.clean;
            sub = `freed ${(c.freed / GB).toFixed(2)} GB · ${Math.round(c.ms)} ms${c.notes?.length ? " · " + c.notes.join(", ") : ""}`;
        }
        ctx.fillText(sub, cx, cy + Math.max(16, r * 0.3), w - 12);
        const k = d?.kitchen;
        const avail = k?.installed ? (k.priority ?? []).filter((b) => k.backends?.[b]) : [];
        ctx.font = "10px ui-monospace, monospace";
        ctx.fillStyle = "#6f737d";
        ctx.fillText(`canvas2d${k?.installed ? " · kitchen: " + (avail.join(" > ") || "none") : ""}`, cx, hgt - 10, w - 12);
    }

    node.addDOMWidget("jwtf_vram_gauge", "jwtf_vram_gauge", canvas, { serialize: false, getMinHeight: () => 150 });
    const io = new IntersectionObserver((entries) => {
        g.visible = entries.some((e) => e.isIntersecting);
        ensurePolling();
        if (g.visible) { g.update(lastVram); kick(); }
    });
    io.observe(canvas);
    new ResizeObserver(() => paint(performance.now())).observe(canvas);

    node._jwtfVram = {
        showClean,
        dispose() {
            io.disconnect();
            cancelAnimationFrame(g.raf);
            gauges.delete(g);
            ensurePolling();
        },
    };
    node.setSize([Math.max(node.size[0], 300), Math.max(node.size[1], 400)]);
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.RefreshPage",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "JWTFRefreshPage") return;
        chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
        chain(nodeType.prototype, "onExecuted", function (msg) {
            const stats = msg?.[UI_KEY]?.[0];
            if (stats) this._jwtfVram?.showClean(stats);
        });
        chain(nodeType.prototype, "onRemoved", function () { this._jwtfVram?.dispose(); });
        chain(nodeType.prototype, "onResize", function (size) {
            size[0] = Math.max(size[0], 300);
            size[1] = Math.max(size[1], 400);
        });
    },
});
