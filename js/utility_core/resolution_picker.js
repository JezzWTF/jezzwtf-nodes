import { app } from "../../../scripts/app.js";
import { chain, findWidget, fitHeight, onWidget, setWidgetVisible } from "./_shared.js";

// Resolution Picker: mode-dependent widget visibility plus a live canvas preview that
// mirrors the Python maths (nodes/utility_core/resolution.py).

const RATIO = "Ratio + Megapixels";
const NAMES = ["mode", "aspect_ratio", "custom_ratio_w", "custom_ratio_h", "megapixels", "preset_resolution",
    "snap_presets", "multiple", "swap_orientation", "batch_size"];

const parseRatio = (label) => {
    const m = /^\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)/.exec(String(label ?? ""));
    const rw = m ? parseFloat(m[1]) : 1, rh = m ? parseFloat(m[2]) : 1;
    return rw > 0 && rh > 0 ? [rw, rh] : [1, 1];
};
const parseSize = (label) => {
    const m = /^\s*(\d+)\s*x\s*(\d+)/i.exec(String(label ?? ""));
    const w = m ? parseInt(m[1], 10) : 1024, h = m ? parseInt(m[2], 10) : 1024;
    return w > 0 && h > 0 ? [w, h] : [1024, 1024];
};
const snap = (v, mult) => {
    const m = Math.max(1, Math.trunc(mult) || 1);
    return Math.max(m, Math.floor(v / m + 0.5) * m);
};
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

export function compute(v) {
    let w, h, rw, rh;
    if (v.mode === RATIO) {
        if (v.aspect_ratio === "Custom") {
            rw = clamp(Number(v.custom_ratio_w) || 1, 0.1, 100);
            rh = clamp(Number(v.custom_ratio_h) || 1, 0.1, 100);
        } else [rw, rh] = parseRatio(v.aspect_ratio);
        const pixels = clamp(Number(v.megapixels) || 1, 0.05, 16) * 1024 * 1024;
        const s = Math.sqrt(pixels / (rw * rh));
        w = snap(rw * s, v.multiple);
        h = snap(rh * s, v.multiple);
    } else {
        [w, h] = parseSize(v.preset_resolution);
        [rw, rh] = [w, h];
        if (v.snap_presets) { w = snap(w, v.multiple); h = snap(h, v.multiple); }
    }
    if (v.swap_orientation) [w, h, rw, rh] = [h, w, rh, rw];
    return { w, h, rw, rh };
}

function ratioText(node, v, w, h) {
    const swap = !!v.swap_orientation;
    if (v.mode === RATIO) {
        let txt = v.aspect_ratio === "Custom" ? `${v.custom_ratio_w}:${v.custom_ratio_h}` : String(v.aspect_ratio).split(" ")[0];
        if (swap) txt = txt.split(":").reverse().join(":");
        return txt;
    }
    const target = w / h;
    const labels = findWidget(node, "aspect_ratio")?.options?.values ?? [];
    let best = null;
    for (const l of labels) {
        if (l === "Custom") continue;
        const [a, b] = parseRatio(l);
        const d = Math.abs(Math.log(a / b) - Math.log(target));
        if (d < 0.02 && (!best || d < best.d)) best = { d, txt: l.split(" ")[0] };
    }
    return best ? best.txt : `${(w >= h ? w / h : h / w).toFixed(2)}:1`;
}

function setup(node) {
    const W = Object.fromEntries(NAMES.map((n) => [n, findWidget(node, n)]));
    const vals = () => Object.fromEntries(NAMES.map((n) => [n, W[n]?.value]));
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "width:100%;height:100%;display:block;border-radius:8px;";
    const anim = { w: 0, h: 0, tw: 0, th: 0, pulse: 0, raf: 0 };
    let sig = "";
    let lastVis = "";

    function reconcileVisibility(v) {
        const ratio = v.mode === RATIO;
        const vis = {
            aspect_ratio: ratio, megapixels: ratio,
            custom_ratio_w: ratio && v.aspect_ratio === "Custom", custom_ratio_h: ratio && v.aspect_ratio === "Custom",
            preset_resolution: !ratio, snap_presets: !ratio,
        };
        for (const [n, on] of Object.entries(vis)) setWidgetVisible(node, W[n], on);
        const key = JSON.stringify(vis);
        if (key !== lastVis) {
            lastVis = key;
            fitHeight(node, 340);
        }
    }

    function sync(immediate = false) {
        const v = vals();
        reconcileVisibility(v);
        const { batch_size, ...rest } = v;
        const s = JSON.stringify(rest);
        if (s === sig && !immediate) return;
        sig = s;
        const r = compute(v);
        anim.tw = r.w;
        anim.th = r.h;
        anim.res = r;
        anim.v = v;
        if (immediate || !anim.w) { anim.w = r.w; anim.h = r.h; }
        else anim.pulse = performance.now();
        kick();
    }

    function kick() {
        if (anim.raf) return;
        const step = () => {
            anim.w += (anim.tw - anim.w) * 0.2;
            anim.h += (anim.th - anim.h) * 0.2;
            const settled = Math.abs(anim.tw - anim.w) < 0.5 && Math.abs(anim.th - anim.h) < 0.5 && performance.now() - anim.pulse > 700;
            if (settled) { anim.w = anim.tw; anim.h = anim.th; }
            paint();
            anim.raf = settled ? 0 : requestAnimationFrame(step);
        };
        anim.raf = requestAnimationFrame(step);
    }

    function paint() {
        const dpr = window.devicePixelRatio || 1;
        const cw = canvas.clientWidth, ch = canvas.clientHeight;
        if (!cw || !ch || !anim.res) return;
        if (canvas.width !== Math.round(cw * dpr)) canvas.width = Math.round(cw * dpr);
        if (canvas.height !== Math.round(ch * dpr)) canvas.height = Math.round(ch * dpr);
        const ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.fillStyle = "#101114";
        ctx.fillRect(0, 0, cw, ch);
        ctx.fillStyle = "#2a2c33";
        for (let x = 8; x < cw; x += 14) for (let y = 8; y < ch; y += 14) ctx.fillRect(x, y, 1, 1);

        const { w: rw, h: rh } = anim.res;
        const v = anim.v;
        const headH = 18, footH = 18, padX = 30, padY = 14;
        const availW = cw - padX * 2, availH = ch - headH - footH - padY * 2;
        const maxSide = Math.max(anim.w, anim.h, 1024);
        const scale = Math.min(availW / maxSide, availH / maxSide);
        const cx = cw / 2, cy = headH + padY + availH / 2;
        // 1024 reference square
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = "#3a3d46";
        ctx.strokeRect(cx - 512 * scale, cy - 512 * scale, 1024 * scale, 1024 * scale);
        ctx.setLineDash([]);
        // target frame
        const fw = anim.w * scale, fh = anim.h * scale;
        const fx = cx - fw / 2, fy = cy - fh / 2;
        const mp = (rw * rh) / (1024 * 1024);
        const tHue = clamp((Math.log2(Math.max(mp, 0.05)) + 4.3) / 8.3, 0, 1);
        const hue = 210 + tHue * 120;
        const col = `hsl(${hue % 360} 90% 62%)`;
        ctx.fillStyle = `hsl(${hue % 360} 90% 62% / .12)`;
        ctx.fillRect(fx, fy, fw, fh);
        ctx.shadowColor = col;
        ctx.shadowBlur = 10;
        ctx.strokeStyle = col;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(fx, fy, fw, fh);
        ctx.shadowBlur = 0;
        // thirds
        ctx.strokeStyle = `hsl(${hue % 360} 90% 62% / .25)`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let i = 1; i < 3; i++) {
            ctx.moveTo(fx + (fw * i) / 3, fy); ctx.lineTo(fx + (fw * i) / 3, fy + fh);
            ctx.moveTo(fx, fy + (fh * i) / 3); ctx.lineTo(fx + fw, fy + (fh * i) / 3);
        }
        ctx.stroke();
        // corner ticks
        ctx.strokeStyle = col;
        ctx.lineWidth = 2;
        const tk = Math.min(10, fw / 4, fh / 4);
        for (const [x, y, dx, dy] of [[fx, fy, 1, 1], [fx + fw, fy, -1, 1], [fx, fy + fh, 1, -1], [fx + fw, fy + fh, -1, -1]]) {
            ctx.beginPath(); ctx.moveTo(x + dx * tk, y); ctx.lineTo(x, y); ctx.lineTo(x, y + dy * tk); ctx.stroke();
        }
        // pulse ring
        const pt = (performance.now() - anim.pulse) / 700;
        if (pt < 1) {
            ctx.globalAlpha = 1 - pt;
            ctx.strokeStyle = col;
            ctx.strokeRect(fx - pt * 12, fy - pt * 12, fw + pt * 24, fh + pt * 24);
            ctx.globalAlpha = 1;
        }
        // ratio text
        ctx.fillStyle = "#e6e8ee";
        ctx.font = "700 13px ui-monospace, Consolas, monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(ratioText(node, v, rw, rh), cx, cy);
        // dimension lines
        ctx.fillStyle = "#9aa0ab";
        ctx.font = "11px ui-monospace, Consolas, monospace";
        ctx.fillText(`${rw}`, cx, fy + fh + 9);
        ctx.save();
        ctx.translate(fx - 10, cy);
        ctx.rotate(-Math.PI / 2);
        ctx.fillText(`${rh}`, 0, 0);
        ctx.restore();
        // header / footer
        const orient = rw === rh ? "SQUARE" : rw > rh ? "LANDSCAPE" : "PORTRAIT";
        ctx.textAlign = "left";
        ctx.font = "700 10px system-ui";
        ctx.fillStyle = "#8b8f99";
        ctx.fillText(orient, 8, 10);
        ctx.textAlign = "right";
        ctx.fillText(`${mp.toFixed(2)} MP`, cw - 8, 10);
        ctx.textAlign = "left";
        ctx.font = "600 11px ui-monospace, Consolas, monospace";
        ctx.fillStyle = "#c9ccd4";
        ctx.fillText(`${rw} × ${rh}`, 8, ch - 9);
        const rr = anim.res;
        const drift = Math.abs(rw * rr.rh - rh * rr.rw) / ((rw * rr.rh + rh * rr.rw) / 2);
        if (drift > 0.01) {
            ctx.textAlign = "right";
            ctx.fillStyle = "#f59e0b";
            ctx.fillText(`actual ${(rw / rh).toFixed(3)}`, cw - 8, ch - 9);
        }
    }

    for (const n of NAMES) onWidget(W[n], () => sync());
    node.addDOMWidget("jwtf_res_preview", "jwtf_res_preview", canvas, { serialize: false, getMinHeight: () => 200 });
    new ResizeObserver(() => paint()).observe(canvas);
    node._jwtfRes = { sync, stop: () => cancelAnimationFrame(anim.raf) };
    sync(true);
    fitHeight(node, 340);
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.ResolutionPicker",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "JWTFResolutionPicker") return;
        chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
        chain(nodeType.prototype, "onConfigure", function () { this._jwtfRes?.sync(true); });
        chain(nodeType.prototype, "onDrawForeground", function () { this._jwtfRes?.sync(false); });
        chain(nodeType.prototype, "onRemoved", function () { this._jwtfRes?.stop(); });
        chain(nodeType.prototype, "onResize", function (size) { size[0] = Math.max(size[0], 340); });
    },
});
