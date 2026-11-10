import { app } from "../../../scripts/app.js";
import { chain, findWidget, h, hideWidget, injectCss } from "./_shared.js";

// Title Font: a decorative banner node. All native widgets are hidden behind one panel.

const PRESETS = [
    ["Sunset", "#ff512f", "#f09819", "Gradient"], ["Ocean", "#2193b0", "#6dd5ed", "Gradient"],
    ["Candy", "#ff6ec4", "#7873f5", "Gradient"], ["Lime", "#11998e", "#38ef7d", "Gradient"],
    ["Neon", "#00f0ff", "#ff00e5", "Neon"], ["Chrome", "#e6ebf2", "#8893a3", "Chrome"],
];
const STYLES = ["Solid", "Gradient", "Neon", "Rainbow", "Outline", "Chrome"];
const ANIMS = ["None", "Pulse", "Float", "Shimmer", "Rainbow Shift", "Glow Pulse"];
const ANIM_CLASS = { Pulse: "pulse", Float: "float", Shimmer: "shimmer", "Rainbow Shift": "hue", "Glow Pulse": "glow" };
const FIELDS = ["text", "font_size", "bold", "glow", "style", "color_a", "color_b", "animate", "url"];

injectCss("jwtf-title", `
.jwtf-tf { gap: 6px; }
.jwtf-tf-strip { height: 3px; border-radius: 2px; background: linear-gradient(90deg, var(--a), var(--b), var(--a));
  background-size: 200% 100%; animation: jwtf-strip 4s linear infinite; }
@keyframes jwtf-strip { to { background-position: -200% 0; } }
.jwtf-tf-prev { position: relative; display: grid; place-items: center; min-height: 80px; padding: 14px 10px;
  border-radius: 8px; background: radial-gradient(circle at 50% 40%, var(--tint), transparent 70%), #101114;
  overflow: hidden; text-align: center; }
.jwtf-tf-title { line-height: 1.1; word-break: break-word; text-decoration: none; display: inline-block; }
.jwtf-tf-title.placeholder { opacity: .3; }
.jwtf-tf-link { position: absolute; top: 6px; right: 8px; font-size: 10px; color: #9ab; }
.jwtf-tf-title.pulse { animation: jwtf-pulse 1.6s ease-in-out infinite; }
.jwtf-tf-title.float { animation: jwtf-float 2.4s ease-in-out infinite; }
.jwtf-tf-title.shimmer { animation: jwtf-shimmer 2s ease-in-out infinite; }
.jwtf-tf-title.hue { animation: jwtf-hue 4s linear infinite; }
.jwtf-tf-title.glow { animation: jwtf-glow 2s ease-in-out infinite; }
@keyframes jwtf-pulse { 50% { transform: scale(1.04); opacity: .85; } }
@keyframes jwtf-float { 50% { transform: translateY(-7px); } }
@keyframes jwtf-shimmer { 50% { filter: brightness(1.5) contrast(1.2); } }
@keyframes jwtf-hue { to { filter: hue-rotate(360deg); } }
@keyframes jwtf-glow { 0%,100% { filter: drop-shadow(0 0 8px var(--a)); } 50% { filter: drop-shadow(0 0 14px var(--b)); } }
.jwtf-tf-swatch { width: 22px; height: 18px; border-radius: 5px; border: 1px solid #444; cursor: pointer; padding: 0; }
.jwtf-tf input[type=color] { width: 30px; height: 22px; padding: 0; border: 1px solid #333; background: none; }
.jwtf-tf select { font: inherit; color: #ddd; background: #121317; border: 1px solid #30333b; border-radius: 6px; padding: 2px 4px; }
`);

function hexA(hex, alpha) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex ?? ""));
    if (!m) return `rgba(255,255,255,${alpha})`;
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${alpha})`;
}

function renderTitle(el, v) {
    const size = Math.max(8, Math.min(240, Number(v.font_size) || 56));
    const a = v.color_a, b = v.color_b;
    const s = el.style;
    s.cssText = "";
    s.fontSize = `${size}px`;
    s.fontWeight = v.bold ? "900" : "700";
    s.setProperty("--a", a);
    s.setProperty("--b", b);
    const clip = (bg) => { s.backgroundImage = bg; s.webkitBackgroundClip = "text"; s.backgroundClip = "text"; s.color = "transparent"; };
    const shadows = [];
    switch (v.style) {
        case "Solid": s.color = a; break;
        case "Gradient": clip(`linear-gradient(90deg, ${a}, ${b})`); break;
        case "Neon": {
            s.color = "#fff";
            const r = Math.max(2, Math.round(size / 14));
            shadows.push(`0 0 ${r}px #fff`, `0 0 ${r * 2}px ${a}`, `0 0 ${r * 4}px ${b}`);
            break;
        }
        case "Rainbow": clip("linear-gradient(90deg,#ff3b3b,#ff9f1a,#ffe11a,#3bff6e,#1ad1ff,#7a5cff,#ff3bd4)"); break;
        case "Outline":
            s.color = "transparent";
            s.webkitTextStroke = `${Math.max(1, Math.round(size / 28))}px ${a}`;
            break;
        case "Chrome": clip("linear-gradient(180deg,#ffffff 0%,#c9d1dc 45%,#6f7b8b 52%,#e9edf3 100%)"); break;
    }
    if (v.glow) {
        const g = Math.max(6, Math.round(size / 5));
        shadows.push(`0 0 ${g}px ${a}`, `0 0 ${Math.round(g * 1.8)}px ${hexA(b, 0.8)}`);
    }
    if (shadows.length) {
        // Clipped/transparent text can't carry text-shadow; use drop-shadow filters instead.
        if (s.color === "transparent") s.filter = shadows.slice(0, 3).map((x) => `drop-shadow(${x})`).join(" ");
        else s.textShadow = shadows.join(", ");
    }
}

function setup(node) {
    const W = Object.fromEntries(FIELDS.map((n) => [n, findWidget(node, n)]));
    const hideAll = () => Object.values(W).forEach((w) => hideWidget(node, w));
    hideAll();
    const val = () => Object.fromEntries(FIELDS.map((n) => [n, W[n]?.value]));
    const write = (name, v) => {
        if (!W[name]) return;
        W[name].value = v;
        W[name].callback?.(v);
        render();
        node.setDirtyCanvas(true, false);
    };

    const strip = h("div.jwtf-tf-strip");
    const title = h("a.jwtf-tf-title", { rel: "noopener", target: "_blank" });
    const linkBadge = h("span.jwtf-tf-link", { textContent: "\u{1F517} link" });
    const prev = h("div.jwtf-tf-prev", {}, title, linkBadge);
    const text = h("input.jwtf-input.jwtf-grow", { type: "text", placeholder: "Title text", oninput: (e) => write("text", e.target.value) });
    const range = h("input.jwtf-grow", { type: "range", min: 8, max: 240, step: 1, oninput: (e) => write("font_size", Number(e.target.value)) });
    const num = h("input.jwtf-input", { type: "number", min: 8, max: 240, style: { width: "56px" },
        onchange: (e) => write("font_size", Math.max(8, Math.min(240, Math.round(Number(e.target.value) || 56)))) });
    const colA = h("input", { type: "color", oninput: (e) => write("color_a", e.target.value) });
    const colB = h("input", { type: "color", oninput: (e) => write("color_b", e.target.value) });
    const presets = PRESETS.map(([name, a, b, st]) => h("button.jwtf-tf-swatch", {
        title: name, style: { background: `linear-gradient(135deg, ${a}, ${b})` },
        onclick: () => { W.color_a.value = a; W.color_b.value = b; write("style", st); },
    }));
    const bold = h("button.jwtf-btn.jwtf-pill", { textContent: "Bold", onclick: () => write("bold", !W.bold.value) });
    const glow = h("button.jwtf-btn.jwtf-pill", { textContent: "Glow", onclick: () => write("glow", !W.glow.value) });
    const style = h("select", { onchange: (e) => write("style", e.target.value) }, STYLES.map((s) => h("option", { value: s, textContent: s })));
    const anim = h("select", { onchange: (e) => write("animate", e.target.value) }, ANIMS.map((s) => h("option", { value: s, textContent: s })));
    const url = h("input.jwtf-input.jwtf-grow", { type: "text", placeholder: "https://...", oninput: (e) => write("url", e.target.value.trim()) });
    const open = h("button.jwtf-btn", { textContent: "Open", onclick: () => W.url.value && window.open(W.url.value, "_blank", "noopener") });

    const root = h("div.jwtf-card.jwtf-tf", {}, strip, prev,
        h("div.jwtf-row", {}, text),
        h("div.jwtf-row", {}, h("span.jwtf-muted", {}, "Size"), range, num),
        h("div.jwtf-row", {}, colA, colB, ...presets),
        h("div.jwtf-row", {}, bold, glow, style, anim),
        h("div.jwtf-row", {}, url, open));

    let lastAnim = null;
    function render() {
        hideAll();
        const v = val();
        const empty = !String(v.text ?? "").trim();
        title.textContent = empty ? "Your title" : v.text;
        renderTitle(title, v);
        title.classList.toggle("placeholder", empty);
        if (v.animate !== lastAnim) {
            Object.values(ANIM_CLASS).forEach((c) => title.classList.remove(c));
            if (ANIM_CLASS[v.animate]) title.classList.add(ANIM_CLASS[v.animate]);
            lastAnim = v.animate;
        }
        if (v.url) title.setAttribute("href", v.url);
        else title.removeAttribute("href");
        linkBadge.style.display = v.url ? "" : "none";
        prev.style.setProperty("--tint", hexA(v.color_a, 0.22));
        strip.style.setProperty("--a", v.color_a);
        strip.style.setProperty("--b", v.color_b);
        if (text.value !== String(v.text ?? "")) text.value = String(v.text ?? "");
        if (url.value !== String(v.url ?? "")) url.value = String(v.url ?? "");
        range.value = String(v.font_size);
        num.value = String(v.font_size);
        colA.value = /^#[0-9a-f]{6}$/i.test(v.color_a) ? v.color_a : "#ffffff";
        colB.value = /^#[0-9a-f]{6}$/i.test(v.color_b) ? v.color_b : "#ffffff";
        bold.classList.toggle("on", !!v.bold);
        glow.classList.toggle("on", !!v.glow);
        style.value = v.style;
        anim.value = v.animate;
        open.disabled = !v.url;
        requestAnimationFrame(() => {
            const want = root.scrollHeight + 8;
            if (Math.abs((node._jwtfH ?? 0) - want) > 2) {
                node._jwtfH = want;
                const sz = node.computeSize();
                node.setSize([Math.max(node.size[0], 340), sz[1]]);
                node.setDirtyCanvas(true, true);
            }
        });
    }

    node._jwtfRender = render;
    node.addDOMWidget("jwtf_title", "jwtf_title", root, { serialize: false, getMinHeight: () => node._jwtfH ?? 300 });
    render();
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.TitleFont",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "JWTFTitleFont") return;
        chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
        chain(nodeType.prototype, "onConfigure", function () { this._jwtfRender?.(); });
    },
});
