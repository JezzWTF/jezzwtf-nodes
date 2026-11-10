// H3 Upscale Picker: live canvas preview of the same-scale target size.
// The size search is the same function the Python node runs (upscale_math.js, parity-tested).
import { app } from "../../../scripts/app.js";
import { MODES, pickTarget } from "./upscale_math.js";
import { chain, clamp, findWidget, fitHeight, getLink, onWidget, setWidgetVisible } from "./_shared.js";

const NODE = "JWTFH3UpscalePicker";
const PREVIEW_H = 200;
const MAX_DEPTH = 12;
const SUBGRAPH_INPUT_ID = -10;
const RESOLUTION_NODE = "JWTFResolutionPicker";

let resolutionCompute = null; // lazily imported from the utility family; stays null if absent
import("../utility_core/resolution_picker.js").then((m) => { resolutionCompute = m.compute; }).catch(() => {});

// --------------------------------------------------------------------------- upstream size tracing

function inputLink(node, name) {
    const slot = node.inputs?.findIndex((i) => i.name === name) ?? -1;
    if (slot < 0) return null;
    const id = node.inputs[slot].link;
    return id == null ? null : getLink(node.graph, id);
}

function subgraphHost(graph) {
    const root = app.rootGraph ?? app.graph;
    const seen = new Set();
    const stack = [root];
    while (stack.length) {
        const g = stack.pop();
        if (!g || seen.has(g)) continue;
        seen.add(g);
        for (const n of g._nodes ?? []) {
            if (n.subgraph === graph) return n;
            if (n.subgraph) stack.push(n.subgraph);
        }
    }
    return null;
}

/** Follow a link through Reroutes and subgraph input pins; returns {node, slot} or null. */
function traceOrigin(graph, link, depth = 0) {
    if (!link || depth > MAX_DEPTH) return null;
    if (link.origin_id === SUBGRAPH_INPUT_ID) {
        const host = subgraphHost(graph);
        if (!host) return null;
        const id = host.inputs?.[link.origin_slot]?.link;
        return traceOrigin(host.graph, id == null ? null : getLink(host.graph, id), depth + 1);
    }
    const origin = graph.getNodeById?.(link.origin_id) ?? graph._nodes_by_id?.[link.origin_id];
    if (!origin) return null;
    if (origin.type === "Reroute") {
        const id = origin.inputs?.[0]?.link;
        return traceOrigin(origin.graph ?? graph, id == null ? null : getLink(graph, id), depth + 1);
    }
    return { node: origin, slot: link.origin_slot };
}

function widgetValues(node) {
    const v = {};
    for (const w of node.widgets ?? []) v[w.name] = w.value;
    return v;
}

/** Numeric value a traced origin produces, or null when it cannot be known without running. */
function originValue(origin, axis) {
    const { node, slot } = origin;
    const outName = String(node.outputs?.[slot]?.name ?? "").toLowerCase();
    if ((node.comfyClass === RESOLUTION_NODE || node.type === RESOLUTION_NODE) && resolutionCompute) {
        try {
            const r = resolutionCompute(widgetValues(node));
            return outName.startsWith("h") ? r.h : r.w;
        } catch { /* fall through */ }
    }
    const w = findWidget(node, outName) ?? findWidget(node, axis);
    if (w && typeof w.value === "number" && node.outputs?.[slot]?.type === "INT") return w.value;
    if (node.type === "PrimitiveInt" || node.type === "PrimitiveNode") {
        const pw = node.widgets?.[0];
        if (pw && typeof pw.value === "number") return pw.value;
    }
    return null;
}

function upstreamSignature(node) {
    const parts = [];
    for (const axis of ["width", "height"]) {
        const o = traceOrigin(node.graph, inputLink(node, axis));
        parts.push(o ? `${o.node.id}:${o.slot}` : "-");
    }
    return parts.join("|");
}

function sourceSize(node) {
    const out = { w: findWidget(node, "width")?.value ?? 640, h: findWidget(node, "height")?.value ?? 352, linked: false };
    const sig = upstreamSignature(node);
    for (const [axis, key] of [["width", "w"], ["height", "h"]]) {
        const link = inputLink(node, axis);
        if (!link) continue;
        out.linked = true;
        const origin = traceOrigin(node.graph, link);
        const v = origin ? originValue(origin, axis) : null;
        if (typeof v === "number") out[key] = v;
        else if (node._jwtfLastRun && node._jwtfLastRun.sig === sig) out[key] = node._jwtfLastRun[key === "w" ? "sw" : "sh"];
    }
    out.sig = sig;
    return out;
}

// --------------------------------------------------------------------------- drawing

function currentPick(node, src) {
    const v = (n, d) => findWidget(node, n)?.value ?? d;
    return pickTarget(src.w, src.h, v("mode", MODES[0]), v("scale", "2x"), v("custom_scale", 2),
        v("target_megapixels", 0.5), v("multiple", 16));
}

function hueFor(mp) {
    return 200 + clamp(Math.log2(Math.max(mp, 1 / 16) * 4) / 6, 0, 1) * 130;
}

function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(x, y, w, h, r);
    else ctx.rect(x, y, w, h);
}

function arrowLine(ctx, x0, y0, x1, y1) {
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
}

function drawPreview(node, ctx, x, y, width, height) {
    const st = node._jwtfUp;
    const src = sourceSize(node);
    const pick = currentPick(node, src);
    const goal = { sw: src.w, sh: src.h, tw: pick.width, th: pick.height };
    if (!st.cur) st.cur = { ...goal };
    let moving = false;
    for (const k of Object.keys(goal)) {
        const d = goal[k] - st.cur[k];
        if (Math.abs(d) > 0.5) { st.cur[k] += d * 0.2; moving = true; } else st.cur[k] = goal[k];
    }
    const key = `${goal.sw}x${goal.sh}>${goal.tw}x${goal.th}`;
    if (st.key !== key) { st.key = key; st.pulse = 1; }
    if (st.pulse > 0.01) { st.pulse *= 0.9; moving = true; } else st.pulse = 0;
    node._jwtfUpInfo = pick.info;

    const pad = 8;
    const hdr = 22, ftr = 18;
    const bx = x + pad, by = y + hdr, bw = width - pad * 2, bh = height - hdr - ftr;
    ctx.save();
    ctx.fillStyle = "#15171b";
    roundRect(ctx, x + 2, y, width - 4, height, 8);
    ctx.fill();
    ctx.clip();
    // dotted background
    ctx.fillStyle = "rgba(255,255,255,.07)";
    for (let gx = bx; gx < bx + bw; gx += 14) for (let gy = by; gy < by + bh; gy += 14) ctx.fillRect(gx, gy, 1.5, 1.5);

    const cur = st.cur;
    const scale = Math.min((bw - 36) / cur.tw, (bh - 28) / cur.th);
    const cx = bx + bw / 2, cy = by + bh / 2;
    const tw = cur.tw * scale, th = cur.th * scale;
    const sw = Math.min(tw, cur.sw * scale), sh = Math.min(th, cur.sh * scale);
    const outMp = (pick.width * pick.height) / 1048576;
    const hue = hueFor(outMp);
    const pulse = st.pulse;
    // target frame
    ctx.fillStyle = `hsla(${hue}, 70%, 55%, ${0.16 + pulse * 0.18})`;
    ctx.strokeStyle = `hsla(${hue}, 80%, 65%, ${0.85})`;
    ctx.lineWidth = 1.5 + pulse * 2;
    ctx.fillRect(cx - tw / 2, cy - th / 2, tw, th);
    ctx.strokeRect(cx - tw / 2, cy - th / 2, tw, th);
    // source frame, nested on the same centre
    ctx.fillStyle = "rgba(255,255,255,.14)";
    ctx.strokeStyle = "rgba(255,255,255,.7)";
    ctx.lineWidth = 1;
    ctx.fillRect(cx - sw / 2, cy - sh / 2, sw, sh);
    ctx.strokeRect(cx - sw / 2, cy - sh / 2, sw, sh);
    // corner ticks
    ctx.strokeStyle = `hsla(${hue}, 85%, 75%, 1)`;
    ctx.lineWidth = 2;
    const L = 7;
    for (const [px, py, dx, dy] of [[-1, -1, 1, 1], [1, -1, -1, 1], [-1, 1, 1, -1], [1, 1, -1, -1]]) {
        const ox = cx + px * tw / 2, oy = cy + py * th / 2;
        arrowLine(ctx, ox, oy, ox + dx * L, oy);
        arrowLine(ctx, ox, oy, ox, oy + dy * L);
    }
    // dimension lines
    ctx.strokeStyle = "rgba(255,255,255,.4)";
    ctx.fillStyle = "#cfd3dc";
    ctx.lineWidth = 1;
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "center";
    const dimY = cy + th / 2 + 9;
    arrowLine(ctx, cx - tw / 2, dimY, cx + tw / 2, dimY);
    ctx.fillText(`${pick.width}`, cx, dimY + 10);
    const dimX = cx + tw / 2 + 9;
    arrowLine(ctx, dimX, cy - th / 2, dimX, cy + th / 2);
    ctx.save();
    ctx.translate(dimX + 3, cy);
    ctx.rotate(Math.PI / 2);
    ctx.fillText(`${pick.height}`, 0, 0);
    ctx.restore();
    ctx.fillStyle = "rgba(255,255,255,.75)";
    ctx.fillText(`${Math.round(src.w)}x${Math.round(src.h)}`, cx, cy + 3);

    // header
    ctx.textAlign = "left";
    ctx.font = "bold 11px system-ui, sans-serif";
    ctx.fillStyle = "#e8eaf0";
    ctx.fillText(`${pick.scale.toFixed(2)}x`, x + pad + 2, y + 15);
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = "#9aa1af";
    ctx.fillText(`${outMp.toFixed(2)} MP`, x + pad + 46, y + 15);
    let status = "EXACT", color = "#5fd38d";
    if (pick.note) { status = pick.note.toUpperCase(); color = "#f06a6a"; }
    else if (pick.mismatch >= 1e-6) { status = `UNEVEN ${(pick.mismatch * 100).toFixed(1)}%`; color = "#f0b24a"; }
    ctx.textAlign = "right";
    ctx.font = "bold 10px system-ui, sans-serif";
    ctx.fillStyle = color;
    ctx.fillText(status, x + width - pad - 2, y + 15);
    // footer
    ctx.textAlign = "left";
    ctx.font = "10px system-ui, sans-serif";
    ctx.fillStyle = "#8b8f99";
    ctx.fillText(`${pick.scaleW.toFixed(3)}x by ${pick.scaleH.toFixed(3)}x${src.linked ? "  (linked source)" : ""}`,
        x + pad + 2, y + height - 6);
    ctx.restore();
    if (moving) requestAnimationFrame(() => node.setDirtyCanvas(true, false));
}

// --------------------------------------------------------------------------- node wiring

function updateVisibility(node) {
    const mode = findWidget(node, "mode")?.value;
    const scale = findWidget(node, "scale")?.value;
    const scaleMode = mode !== MODES[1];
    setWidgetVisible(node, findWidget(node, "custom_scale"), scaleMode && scale === "Custom");
    setWidgetVisible(node, findWidget(node, "scale"), scaleMode);
    setWidgetVisible(node, findWidget(node, "target_megapixels"), !scaleMode);
    fitHeight(node, 280);
}

function setup(node) {
    node._jwtfUp = { cur: null, key: "", pulse: 0 };
    const widget = {
        name: "jezzwtf_upscale_preview",
        type: "jezzwtf_upscale_preview",
        value: null,
        serialize: false,
        options: { serialize: false },
        computeSize: (w) => [w, PREVIEW_H],
        draw(ctx, n, width, y) { drawPreview(n, ctx, 0, y, width, PREVIEW_H - 6); },
    };
    node.addCustomWidget(widget);
    for (const name of ["width", "height", "mode", "scale", "custom_scale", "target_megapixels", "multiple"]) {
        onWidget(findWidget(node, name), () => { updateVisibility(node); node.setDirtyCanvas(true, false); });
    }
    chain(node, "onConnectionsChange", () => node.setDirtyCanvas(true, true));
    chain(node, "onConfigure", () => updateVisibility(node));
    chain(node, "onExecuted", (message) => {
        const r = message?.jezzwtf_upscale?.[0];
        if (r) node._jwtfLastRun = { sw: r.sw, sh: r.sh, sig: upstreamSignature(node) };
        node.setDirtyCanvas(true, false);
    });
    updateVisibility(node);
}

app.registerExtension({
    name: "JezzWTF.RefMod.UpscalePicker",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
    },
});
