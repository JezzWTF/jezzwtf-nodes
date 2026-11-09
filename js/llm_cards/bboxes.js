// Bounding Boxes editor: canvas, layers list, inspector and import/export.
import { app } from "../../../scripts/app.js";
import { api, BASE_CSS, copyText, findWidget, fitNode, h, hideWidget, injectCss, shieldKeys } from "./jwtf_ui.js";

const NODE = "JWTFBoundingBoxes";
const SNAP = 16;
const MAX_STAGE_H = 400;
const HANDLE_PX = 8;

injectCss("jwtf-llm-base", BASE_CSS);
injectCss("jwtf-bbx", `
.jwtf-bbx{gap:0}
.jwtf-bbx .pill{border:1px solid #555;border-radius:9px;padding:0 7px;font-variant-numeric:tabular-nums;opacity:.8}
.jwtf-bbx .stage{position:relative;margin:0 6px;display:flex;justify-content:center}
.jwtf-bbx canvas{display:block;outline:none;border-radius:4px;background:#202020;touch-action:none}
.jwtf-bbx canvas:focus{box-shadow:0 0 0 1px #4a8fe0}
.jwtf-bbx .cols{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:6px;min-height:0}
.jwtf-bbx .layers{max-height:190px;overflow:auto;border:1px solid #333;border-radius:4px}
.jwtf-bbx .layer{display:flex;align-items:center;gap:5px;padding:2px 4px;cursor:pointer;border-bottom:1px solid #2a2a2a}
.jwtf-bbx .layer.sel{background:rgba(74,143,224,.2)}
.jwtf-bbx .layer .sw{width:10px;height:10px;border-radius:2px;flex:none}
.jwtf-bbx .layer .tag{font-size:9px;opacity:.7;width:24px;flex:none}
.jwtf-bbx .layer button{padding:0 4px;font-size:10px}
.jwtf-bbx .insp{display:flex;flex-direction:column;gap:4px;min-width:0}
.jwtf-bbx .insp textarea{width:100%;resize:vertical;min-height:34px;padding:3px}
.jwtf-bbx .insp .xywh{display:grid;grid-template-columns:repeat(4,1fr);gap:3px}
.jwtf-bbx .insp .xywh input{width:100%;padding:1px 3px}
.jwtf-bbx .seg{display:inline-flex}.jwtf-bbx .seg .jwtf-btn{border-radius:0}
.jwtf-bbx .seg .jwtf-btn:first-child{border-radius:4px 0 0 4px}.jwtf-bbx .seg .jwtf-btn:last-child{border-radius:0 4px 4px 0}
.jwtf-bbx .pal{display:flex;gap:4px;flex-wrap:wrap;align-items:center}
.jwtf-bbx .pal span{position:relative;display:inline-block}
.jwtf-bbx .pal input[type=color]{width:22px;height:20px;padding:0;border:1px solid #555;cursor:pointer}
.jwtf-bbx .pal .x{position:absolute;top:-6px;right:-6px;display:none;background:#000;border-radius:50%;width:12px;height:12px;
 font-size:9px;line-height:12px;text-align:center;cursor:pointer}
.jwtf-bbx .pal span:hover .x{display:block}
.jwtf-bbx .drawer textarea{width:100%;height:110px;font-family:monospace;font-size:11px}
.jwtf-ctx{position:fixed;z-index:10001;background:#222;border:1px solid #444;border-radius:5px;padding:3px 0;
 font:12px system-ui,sans-serif;color:#ddd;min-width:140px;box-shadow:0 4px 14px rgba(0,0,0,.5)}
.jwtf-ctx div{padding:3px 12px;cursor:pointer}.jwtf-ctx div:hover{background:#3b5b8a}
`);

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const r6 = (v) => Math.round(v * 1e6) / 1e6;

function hslHex(hue, s, l) {
    s /= 100;
    l /= 100;
    const f = (n) => {
        const k = (n + hue / 30) % 12;
        const c = l - s * Math.min(l, 1 - l) * Math.max(-1, Math.min(k - 3, 9 - k, 1));
        return Math.round(c * 255).toString(16).padStart(2, "0");
    };
    return `#${f(0)}${f(8)}${f(4)}`.toUpperCase();
}
const autoColor = (i) => hslHex((i * 47 + 12) % 360, 72, 60);
const boxColor = (r, i) => (r.palette?.[0] ? r.palette[0] : autoColor(i));

function normPalette(p) {
    return (Array.isArray(p) ? p : [])
        .filter((c) => typeof c === "string" && /^#?[0-9a-f]{6}$/i.test(c.trim()))
        .map((c) => (c.trim().startsWith("#") ? c.trim() : `#${c.trim()}`).toUpperCase())
        .slice(0, 5);
}

function normRegion(r) {
    const type = String(r.type ?? r.label ?? "").toLowerCase() === "text" ? "text" : "obj";
    return { x: +r.x || 0, y: +r.y || 0, w: +r.w || 0, h: +r.h || 0, type, text: String(r.text ?? ""),
        desc: String(r.desc ?? ""), palette: normPalette(r.palette) };
}

function fromPixelBoxes(boxes, W, H) {
    return boxes.map((b) => {
        let { x = 0, y = 0, width = 0, height = 0 } = b;
        if (width < 0) [x, width] = [x + width, -width];
        if (height < 0) [y, height] = [y + height, -height];
        const m = b.metadata || {};
        return normRegion({ x: x / W, y: y / H, w: width / W, h: height / H, type: m.type, text: m.text,
            desc: m.desc, palette: m.palette });
    });
}

function fromElements(items, W, H) {
    return items.filter((e) => Array.isArray(e.bbox) && e.bbox.length === 4).map((e) => {
        const [y0, x0, y1, x1] = e.bbox.map((v) => clamp(+v || 0, 0, 1000) / 1000);
        return normRegion({ x: Math.min(x0, x1), y: Math.min(y0, y1), w: Math.abs(x1 - x0), h: Math.abs(y1 - y0),
            type: e.type ?? e.label, text: e.text, desc: e.desc ?? e.caption, palette: e.color_palette ?? e.palette });
    });
}

function toElements(regions) {
    return regions.map((r) => {
        const g = (v) => clamp(Math.round(v * 1000), 0, 1000);
        let [y0, x0, y1, x1] = [g(r.y), g(r.x), g(r.y + r.h), g(r.x + r.w)];
        if (y0 > y1) [y0, y1] = [y1, y0];
        if (x0 > x1) [x0, x1] = [x1, x0];
        const el = { type: r.type, bbox: [y0, x0, y1, x1] };
        if (r.type === "text") el.text = r.text;
        el.desc = r.desc;
        if (r.palette.length) el.color_palette = r.palette.slice(0, 5);
        return el;
    });
}

function toPixelBoxes(regions, W, H) {
    return regions.map((r) => ({
        x: Math.round(r.x * W), y: Math.round(r.y * H), width: Math.round(r.w * W), height: Math.round(r.h * H),
        metadata: { type: r.type, text: r.type === "text" ? r.text : "", desc: r.desc, palette: r.palette },
    }));
}

function setup(node) {
    const S = { regions: [], sel: -1, tool: "draw", snap: true, serverDims: null, bg: null, bgImg: null, drag: null };
    hideWidget(node, "editor_state");
    hideWidget(node, "last_incoming");

    // ---------------------------------------------------------------- dims + persistence
    const linked = (name) => node.inputs?.some((i) => i.name === name && i.link != null);
    function dims() {
        const wv = Number(findWidget(node, "width")?.value) || 1024;
        const hv = Number(findWidget(node, "height")?.value) || 1024;
        const sd = S.serverDims;
        return [linked("width") && sd ? sd[0] : wv, linked("height") && sd ? sd[1] : hv];
    }
    function commit() {
        const w = findWidget(node, "editor_state");
        if (w) {
            w.value = JSON.stringify({ v: 1, regions: S.regions.map((r) => ({ ...r, x: r6(r.x), y: r6(r.y), w: r6(r.w), h: r6(r.h) })) });
        }
        renderAll();
    }
    function load() {
        const raw = findWidget(node, "editor_state")?.value;
        S.regions = [];
        try {
            const v = raw ? JSON.parse(raw) : null;
            const list = Array.isArray(v) ? v : v?.regions;
            if (Array.isArray(list)) S.regions = list.filter((r) => r && typeof r === "object" && isFinite(r.x)).map(normRegion);
        } catch {
            /* keep empty */
        }
        S.sel = Math.min(S.sel, S.regions.length - 1);
        renderAll();
    }

    // ---------------------------------------------------------------- DOM
    const pill = h("span", { class: "pill" });
    const drawBtn = h("button", { class: "jwtf-btn", text: "Draw", title: "Draw tool (D)", onclick: () => setTool("draw") });
    const selBtn = h("button", { class: "jwtf-btn", text: "Select", title: "Select tool (V)", onclick: () => setTool("select") });
    const snapBtn = h("button", { class: "jwtf-btn", text: "Snap", title: `Snap to ${SNAP}px`, onclick: () => { S.snap = !S.snap; renderToolbar(); } });
    const canvas = h("canvas", { tabindex: "0" });
    const ctx = canvas.getContext("2d");
    const stage = h("div", { class: "stage" }, [canvas]);
    const layers = h("div", { class: "layers" });
    const insp = h("div", { class: "insp" });
    const drawerText = h("textarea", { placeholder: "Paste elements ([{type,bbox,…}]) or pixel boxes ([{x,y,width,height}])" });
    const drawerMsg = h("span", { class: "jwtf-muted jwtf-grow jwtf-ellipsis" });
    const drawer = h("div", { class: "drawer", style: { display: "none", padding: "0 6px 6px" } }, [
        drawerText,
        h("div", { class: "jwtf-row", style: { padding: "4px 0 0" } }, [
            h("button", { class: "jwtf-btn", text: "Load", onclick: importText }),
            h("button", { class: "jwtf-btn", text: "Copy elements", onclick: () => exportText(toElements(S.regions)) }),
            h("button", { class: "jwtf-btn", text: "Copy pixel boxes", onclick: () => exportText(toPixelBoxes(S.regions, ...dims())) }),
            drawerMsg,
        ]),
    ]);
    let clearArmed = 0;
    const clearBtn = h("button", { class: "jwtf-btn", text: "Clear all" });
    clearBtn.addEventListener("click", () => {
        if (Date.now() - clearArmed < 2200) {
            S.regions = [];
            S.sel = -1;
            clearArmed = 0;
            clearBtn.textContent = "Clear all";
            commit();
            return;
        }
        clearArmed = Date.now();
        clearBtn.textContent = "Click again to clear";
        setTimeout(() => {
            if (Date.now() - clearArmed >= 2200) clearBtn.textContent = "Clear all";
        }, 2300);
    });
    const panel = h("div", { class: "jwtf-panel jwtf-bbx" }, [
        h("div", { class: "jwtf-row" }, [h("b", { text: "Layout" }), pill, h("span", { class: "jwtf-grow" }), drawBtn, selBtn, snapBtn]),
        stage,
        h("div", { class: "cols" }, [layers, insp]),
        h("div", { class: "jwtf-row" }, [
            h("button", { class: "jwtf-btn", text: "Import / Export", onclick: () => { drawer.style.display = drawer.style.display ? "" : "none"; fitNode(node); } }),
            h("span", { class: "jwtf-grow" }), clearBtn,
        ]),
        drawer,
    ]);
    shieldKeys(panel);

    function setTool(t) {
        S.tool = t;
        renderToolbar();
    }
    function renderToolbar() {
        const [W, H] = dims();
        pill.textContent = `${W} × ${H}`;
        drawBtn.classList.toggle("on", S.tool === "draw");
        selBtn.classList.toggle("on", S.tool === "select");
        snapBtn.classList.toggle("on", S.snap);
    }

    // ---------------------------------------------------------------- canvas
    function layoutCanvas() {
        const [W, H] = dims();
        const avail = Math.max(120, (stage.clientWidth || node.size[0] - 30));
        let cw = avail;
        let ch = (cw * H) / W;
        if (ch > MAX_STAGE_H) {
            ch = MAX_STAGE_H;
            cw = (ch * W) / H;
        }
        const dpr = window.devicePixelRatio || 1;
        canvas.style.width = `${Math.round(cw)}px`;
        canvas.style.height = `${Math.round(ch)}px`;
        canvas.width = Math.round(cw * dpr);
        canvas.height = Math.round(ch * dpr);
        return { W, H, cw, ch, dpr };
    }

    function drawCanvas() {
        const { W, H, cw, ch, dpr } = layoutCanvas();
        const sx = cw / W;
        const sy = ch / H;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, cw, ch);
        ctx.fillStyle = "#202020";
        ctx.fillRect(0, 0, cw, ch);
        if (S.bgImg?.complete && S.bgImg.naturalWidth) {
            ctx.globalAlpha = 0.4;
            ctx.drawImage(S.bgImg, 0, 0, cw, ch);
            ctx.globalAlpha = 1;
        }
        ctx.strokeStyle = "rgba(255,255,255,.07)";
        ctx.lineWidth = 1;
        for (let i = 1; i < 8; i++) {
            ctx.beginPath();
            ctx.moveTo((cw * i) / 8 + 0.5, 0);
            ctx.lineTo((cw * i) / 8 + 0.5, ch);
            ctx.moveTo(0, (ch * i) / 8 + 0.5);
            ctx.lineTo(cw, (ch * i) / 8 + 0.5);
            ctx.stroke();
        }
        S.regions.forEach((r, i) => {
            const x = r.x * W * sx, y = r.y * H * sy, w = r.w * W * sx, hh = r.h * H * sy;
            const col = boxColor(r, i);
            ctx.fillStyle = `${col}22`;
            ctx.fillRect(x, y, w, hh);
            ctx.setLineDash(r.type === "text" ? [5, 3] : []);
            ctx.strokeStyle = col;
            ctx.lineWidth = i === S.sel ? 2 : 1.5;
            ctx.strokeRect(x + 0.5, y + 0.5, w, hh);
            ctx.setLineDash([]);
            const tag = String(i + 1).padStart(2, "0");
            ctx.font = "bold 10px system-ui,sans-serif";
            const tw = ctx.measureText(tag).width + 6;
            ctx.fillStyle = col;
            ctx.fillRect(x, y, tw, 13);
            ctx.fillStyle = "#000";
            ctx.fillText(tag, x + 3, y + 10);
            const body = r.type === "text" ? `“${r.text}”${r.desc ? ` — ${r.desc}` : ""}` : r.desc;
            if (body && w > 24 && hh > 26) {
                ctx.save();
                ctx.beginPath();
                ctx.rect(x, y, w, hh);
                ctx.clip();
                ctx.fillStyle = "rgba(255,255,255,.85)";
                ctx.font = "11px system-ui,sans-serif";
                wrapText(body, x + 4, y + 26, w - 8, 13, y + hh);
                ctx.restore();
            }
            if (i === S.sel) {
                ctx.fillStyle = "#fff";
                for (const [hx, hy] of handlePoints(x, y, w, hh)) ctx.fillRect(hx - 3, hy - 3, 6, 6);
            }
        });
    }

    function wrapText(text, x, y, maxW, lh, bottom) {
        let line = "";
        for (const word of text.split(/\s+/)) {
            const trial = line ? `${line} ${word}` : word;
            if (line && ctx.measureText(trial).width > maxW) {
                if (y > bottom - 2) return;
                ctx.fillText(line, x, y);
                y += lh;
                line = word;
            } else line = trial;
        }
        if (line && y <= bottom - 2) ctx.fillText(line, x, y);
    }

    const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
    function handlePoints(x, y, w, hh) {
        const cx = x + w / 2, cy = y + hh / 2;
        return [[x, y], [cx, y], [x + w, y], [x + w, cy], [x + w, y + hh], [cx, y + hh], [x, y + hh], [x, cy]];
    }

    // pointer -> image pixel space
    function toPx(e) {
        const rect = canvas.getBoundingClientRect();
        const [W, H] = dims();
        return { x: ((e.clientX - rect.left) / rect.width) * W, y: ((e.clientY - rect.top) / rect.height) * H,
            scale: W / rect.width };
    }
    const snapV = (v) => (S.snap ? Math.round(v / SNAP) * SNAP : v);
    const minSize = () => (S.snap ? 16 : 8);
    function hitBox(p) {
        const [W, H] = dims();
        for (let i = S.regions.length - 1; i >= 0; i--) {
            const r = S.regions[i];
            const x = r.x * W, y = r.y * H;
            if (p.x >= x && p.x <= x + r.w * W && p.y >= y && p.y <= y + r.h * H) return i;
        }
        return -1;
    }
    function hitHandle(p) {
        if (S.sel < 0) return null;
        const [W, H] = dims();
        const r = S.regions[S.sel];
        const pts = handlePoints(r.x * W, r.y * H, r.w * W, r.h * H);
        const tol = HANDLE_PX * p.scale;
        const idx = pts.findIndex(([hx, hy]) => Math.abs(p.x - hx) <= tol && Math.abs(p.y - hy) <= tol);
        return idx >= 0 ? HANDLES[idx] : null;
    }

    canvas.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        canvas.focus();
        e.preventDefault();
        e.stopPropagation();
        canvas.setPointerCapture(e.pointerId);
        const p = toPx(e);
        const [W, H] = dims();
        const handle = hitHandle(p);
        if (handle) {
            const r = S.regions[S.sel];
            S.drag = { mode: "resize", handle, edges: { l: r.x * W, t: r.y * H, r: (r.x + r.w) * W, b: (r.y + r.h) * H } };
            return;
        }
        const hit = hitBox(p);
        if (S.tool === "select" && !e.shiftKey) {
            S.sel = hit;
            if (hit >= 0) {
                const r = S.regions[hit];
                S.drag = { mode: "move", dx: p.x - r.x * W, dy: p.y - r.y * H, moved: false };
            }
            renderAll();
            return;
        }
        S.drag = { mode: "pending", start: { x: e.clientX, y: e.clientY }, anchor: { x: snapV(p.x), y: snapV(p.y) }, hit };
    });

    canvas.addEventListener("pointermove", (e) => {
        const d = S.drag;
        if (!d) return;
        const p = toPx(e);
        const [W, H] = dims();
        if (d.mode === "pending") {
            if (Math.hypot(e.clientX - d.start.x, e.clientY - d.start.y) < 4) return;
            S.regions.push(normRegion({ x: d.anchor.x / W, y: d.anchor.y / H, w: 0, h: 0, type: "obj" }));
            S.sel = S.regions.length - 1;
            d.mode = "draw";
        }
        const r = S.regions[S.sel];
        if (!r) return;
        if (d.mode === "draw") {
            const x2 = clamp(snapV(p.x), 0, W), y2 = clamp(snapV(p.y), 0, H);
            const ax = clamp(d.anchor.x, 0, W), ay = clamp(d.anchor.y, 0, H);
            Object.assign(r, { x: Math.min(ax, x2) / W, y: Math.min(ay, y2) / H, w: Math.abs(x2 - ax) / W, h: Math.abs(y2 - ay) / H });
        } else if (d.mode === "move") {
            const bw = r.w * W, bh = r.h * H;
            const nx = clamp(snapV(p.x - d.dx), 0, W - bw), ny = clamp(snapV(p.y - d.dy), 0, H - bh);
            r.x = nx / W;
            r.y = ny / H;
            d.moved = true;
        } else if (d.mode === "resize") {
            const ed = d.edges, m = minSize();
            const px = clamp(snapV(p.x), 0, W), py = clamp(snapV(p.y), 0, H);
            if (d.handle.includes("w")) ed.l = Math.min(px, ed.r - m);
            if (d.handle.includes("e")) ed.r = Math.max(px, ed.l + m);
            if (d.handle.includes("n")) ed.t = Math.min(py, ed.b - m);
            if (d.handle.includes("s")) ed.b = Math.max(py, ed.t + m);
            ed.l = clamp(ed.l, 0, W);
            ed.r = clamp(ed.r, 0, W);
            ed.t = clamp(ed.t, 0, H);
            ed.b = clamp(ed.b, 0, H);
            Object.assign(r, { x: ed.l / W, y: ed.t / H, w: (ed.r - ed.l) / W, h: (ed.b - ed.t) / H });
        }
        drawCanvas();
    });

    const endDrag = () => {
        const d = S.drag;
        S.drag = null;
        if (!d) return;
        if (d.mode === "pending") {
            S.sel = d.hit;
            renderAll();
            return;
        }
        if (d.mode === "draw") {
            const [W, H] = dims();
            const r = S.regions[S.sel];
            if (!r || r.w * W < minSize() || r.h * H < minSize()) {
                S.regions.splice(S.sel, 1);
                S.sel = -1;
            }
        }
        if (d.mode === "move" && !d.moved) return renderAll();
        commit();
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
    canvas.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const hit = hitBox(toPx(e));
        if (hit >= 0) S.sel = hit;
        renderAll();
        openMenu(e, hit);
    });

    canvas.addEventListener("keydown", (e) => {
        e.stopPropagation();
        const mod = e.ctrlKey || e.metaKey;
        if (e.key === "Delete" || e.key === "Backspace") {
            e.preventDefault();
            removeAt(S.sel);
        } else if (mod && e.key.toLowerCase() === "d") {
            e.preventDefault();
            duplicate(S.sel);
        } else if (!mod && e.key.toLowerCase() === "d") setTool("draw");
        else if (!mod && e.key.toLowerCase() === "v") setTool("select");
        else if (e.key.startsWith("Arrow") && S.sel >= 0) {
            e.preventDefault();
            const [W, H] = dims();
            const step = (S.snap ? SNAP : 1) * (e.shiftKey ? 4 : 1);
            const r = S.regions[S.sel];
            const dx = e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0;
            const dy = e.key === "ArrowUp" ? -step : e.key === "ArrowDown" ? step : 0;
            r.x = clamp(r.x * W + dx, 0, W - r.w * W) / W;
            r.y = clamp(r.y * H + dy, 0, H - r.h * H) / H;
            commit();
        }
    });
    canvas.addEventListener("keyup", (e) => e.stopPropagation());

    // ---------------------------------------------------------------- operations
    function removeAt(i) {
        if (i < 0 || i >= S.regions.length) return;
        S.regions.splice(i, 1);
        S.sel = Math.min(i, S.regions.length - 1);
        if (!S.regions.length) S.sel = -1;
        commit();
    }
    function duplicate(i) {
        if (i < 0) return;
        const [W, H] = dims();
        const r = { ...S.regions[i], palette: [...S.regions[i].palette] };
        r.x = clamp(r.x * W + 16, 0, W - r.w * W) / W;
        r.y = clamp(r.y * H + 16, 0, H - r.h * H) / H;
        S.regions.splice(i + 1, 0, r);
        S.sel = i + 1;
        commit();
    }
    function swap(i, j) {
        if (i < 0 || j < 0 || i >= S.regions.length || j >= S.regions.length) return;
        [S.regions[i], S.regions[j]] = [S.regions[j], S.regions[i]];
        if (S.sel === i) S.sel = j;
        else if (S.sel === j) S.sel = i;
        commit();
    }

    function openMenu(e, i) {
        document.querySelector(".jwtf-ctx")?.remove();
        const items = i >= 0
            ? [["Delete", () => removeAt(i)], ["Duplicate", () => duplicate(i)], ["Bring forward", () => swap(i, i + 1)],
                ["Send backward", () => swap(i, i - 1)],
                [`Make ${S.regions[i].type === "text" ? "object" : "text"}`, () => {
                    S.regions[i].type = S.regions[i].type === "text" ? "obj" : "text";
                    commit();
                }]]
            : [["Delete all", () => {
                if (S.regions.length && confirm(`Delete all ${S.regions.length} boxes?`)) {
                    S.regions = [];
                    S.sel = -1;
                    commit();
                }
            }]];
        const menu = h("div", { class: "jwtf-ctx", style: { left: `${e.clientX}px`, top: `${e.clientY}px` } },
            items.map(([label, fn]) => h("div", { text: label, onclick: () => { menu.remove(); fn(); } })));
        document.body.appendChild(menu);
        const close = (ev) => {
            if (!menu.contains(ev.target)) {
                menu.remove();
                window.removeEventListener("pointerdown", close, true);
            }
        };
        setTimeout(() => window.addEventListener("pointerdown", close, true));
    }

    // ---------------------------------------------------------------- layers + inspector
    function renderLayers() {
        layers.replaceChildren(...S.regions.map((r, i) => {
            const label = (r.type === "text" ? r.text : "") || r.desc || "(no description)";
            const row = h("div", { class: `layer${i === S.sel ? " sel" : ""}` }, [
                h("span", { class: "sw", style: { background: boxColor(r, i) } }),
                h("span", { class: "tag", text: `${String(i + 1).padStart(2, "0")} ${r.type === "text" ? "TXT" : "OBJ"}` }),
                h("span", { class: "jwtf-grow jwtf-ellipsis", text: label }),
                h("button", { class: "jwtf-btn", text: "↑", title: "Move up (towards background)", onclick: (e) => { e.stopPropagation(); swap(i, i - 1); } }),
                h("button", { class: "jwtf-btn", text: "↓", title: "Move down (towards foreground)", onclick: (e) => { e.stopPropagation(); swap(i, i + 1); } }),
                h("button", { class: "jwtf-btn", text: "×", title: "Delete", onclick: (e) => { e.stopPropagation(); removeAt(i); } }),
            ]);
            row.addEventListener("click", () => { S.sel = i; renderAll(); });
            row.addEventListener("contextmenu", (e) => { e.preventDefault(); e.stopPropagation(); S.sel = i; renderAll(); openMenu(e, i); });
            return row;
        }));
        if (!S.regions.length) layers.append(h("div", { class: "jwtf-muted", style: { padding: "6px" }, text: "Draw on the canvas to add boxes." }));
    }

    function softCommit() {
        // Text edits: persist and redraw without rebuilding the inspector (keeps focus).
        const w = findWidget(node, "editor_state");
        if (w) w.value = JSON.stringify({ v: 1, regions: S.regions });
        drawCanvas();
        renderLayers();
    }

    function renderInspector() {
        const r = S.regions[S.sel];
        if (!r) {
            insp.replaceChildren(h("div", { class: "jwtf-muted", text: "Select a box to edit it." }));
            return;
        }
        const [W, H] = dims();
        const i = S.sel;
        const seg = h("span", { class: "seg" }, ["obj", "text"].map((t) => h("button", {
            class: `jwtf-btn${r.type === t ? " on" : ""}`, text: t === "obj" ? "Object" : "Text",
            onclick: () => { r.type = t; commit(); },
        })));
        const textArea = h("textarea", { placeholder: "Text to render" });
        textArea.value = r.text;
        textArea.addEventListener("input", () => { r.text = textArea.value; softCommit(); });
        const descArea = h("textarea", { placeholder: "Description" });
        descArea.value = r.desc;
        descArea.addEventListener("input", () => { r.desc = descArea.value; softCommit(); });
        const pal = h("div", { class: "pal" }, r.palette.map((c, k) => {
            const inp = h("input", { type: "color", value: c.toLowerCase() });
            inp.addEventListener("input", () => { r.palette[k] = inp.value.toUpperCase(); softCommit(); });
            inp.addEventListener("change", () => commit());
            return h("span", {}, [inp, h("i", { class: "x", text: "×", onclick: () => { r.palette.splice(k, 1); commit(); } })]);
        }));
        if (r.palette.length < 5) {
            pal.append(h("button", { class: "jwtf-btn", text: "+", title: "Add colour",
                onclick: () => { r.palette.push(autoColor(i + r.palette.length + 1)); commit(); } }));
        }
        const step = S.snap ? SNAP : 1;
        const num = (label, get, set) => {
            const inp = h("input", { type: "number", step, title: label, value: Math.round(get()) });
            inp.addEventListener("change", () => { set(Number(inp.value) || 0); commit(); });
            return h("label", {}, [h("div", { class: "jwtf-muted", text: label }), inp]);
        };
        insp.replaceChildren(
            h("div", { class: "jwtf-row", style: { padding: 0 } }, [
                seg, h("span", { class: "jwtf-grow" }),
                h("button", { class: "jwtf-btn", text: "Duplicate", onclick: () => duplicate(i) }),
                h("button", { class: "jwtf-btn", text: "Delete", onclick: () => removeAt(i) }),
            ]),
            r.type === "text" ? textArea : "",
            descArea,
            pal,
            h("div", { class: "xywh" }, [
                num("X", () => r.x * W, (v) => { r.x = clamp(v, 0, W - r.w * W) / W; }),
                num("Y", () => r.y * H, (v) => { r.y = clamp(v, 0, H - r.h * H) / H; }),
                num("W", () => r.w * W, (v) => { r.w = clamp(v, 1, W - r.x * W) / W; }),
                num("H", () => r.h * H, (v) => { r.h = clamp(v, 1, H - r.y * H) / H; }),
            ]),
        );
    }

    function renderAll() {
        renderToolbar();
        drawCanvas();
        renderLayers();
        renderInspector();
    }

    // ---------------------------------------------------------------- import/export
    async function exportText(data) {
        const text = JSON.stringify(data, null, 1);
        drawerText.value = text;
        drawerMsg.textContent = (await copyText(text)) ? "Copied to clipboard" : "Copy failed; select the text above";
    }
    function importText() {
        try {
            let v = JSON.parse(drawerText.value);
            if (v && !Array.isArray(v)) {
                const key = ["elements", "items", "boxes", "bboxes", "layout", "regions", "objects"].find((k) => Array.isArray(v[k]));
                v = key ? v[key] : [v];
            }
            if (Array.isArray(v[0])) v = v[0];
            const [W, H] = dims();
            let regions = [];
            if (v.some((e) => Array.isArray(e?.bbox))) regions = fromElements(v, W, H);
            else if (v.some((e) => e && "x" in e && "width" in e)) regions = fromPixelBoxes(v, W, H);
            else throw new Error("expected elements with bbox or pixel boxes with x/width");
            S.regions = regions;
            S.sel = -1;
            drawerMsg.textContent = `Loaded ${regions.length} boxes`;
            commit();
        } catch (err) {
            drawerMsg.textContent = `Could not load: ${err.message || err}`;
        }
    }

    // ---------------------------------------------------------------- widget
    const widget = node.addDOMWidget("nbb_panel", "jwtf_bboxes", panel, {
        serialize: false,
        getMinHeight: () => panel.scrollHeight || 600,
    });
    widget.serialize = false;
    new ResizeObserver(() => drawCanvas()).observe(stage);

    for (const name of ["width", "height"]) {
        const w = findWidget(node, name);
        if (!w) continue;
        const cb = w.callback;
        w.callback = function (...a) {
            const r = cb?.apply(this, a);
            renderAll();
            return r;
        };
    }

    return {
        load,
        renderAll,
        executed(msg) {
            if (Array.isArray(msg?.dims)) S.serverDims = msg.dims.map(Number);
            const boxes = msg?.input_bboxes;
            const key = msg?.input_key?.[0] ?? JSON.stringify(boxes ?? []);
            const last = findWidget(node, "last_incoming");
            if (Array.isArray(boxes) && boxes.length && last && key !== last.value) {
                S.regions = fromPixelBoxes(boxes, ...dims());
                S.sel = -1;
                last.value = key;
                commit();
            }
            const bg = msg?.background_images?.[0];
            if (bg) {
                const q = new URLSearchParams({ filename: bg.filename, subfolder: bg.subfolder || "", type: bg.type || "temp", rand: String(Math.random()) });
                const img = new Image();
                img.onload = () => drawCanvas();
                img.src = api.apiURL(`/view?${q}`);
                S.bgImg = img;
            } else {
                S.bgImg = null;
            }
            renderAll();
        },
    };
}

app.registerExtension({
    name: "JezzWTF.LLMCards.BoundingBoxes",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = created?.apply(this, arguments);
            this._jwtfBbx = setup(this);
            this.setSize([600, 760]);
            this._jwtfBbx.load();
            return r;
        };
        const configure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = configure?.apply(this, arguments);
            this._jwtfBbx?.load();
            return r;
        };
        const conn = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function () {
            const r = conn?.apply(this, arguments);
            this._jwtfBbx?.renderAll();
            return r;
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = executed?.apply(this, arguments);
            this._jwtfBbx?.executed(message);
            return r;
        };
    },
});
