// Character Chat panel: card header, message log, composer, progress strip and widget repair.
import { app } from "../../../scripts/app.js";
import { api, BASE_CSS, copyText, findWidget, h, hideWidget, injectCss, shieldKeys, uploadToInput } from "./jwtf_ui.js";

const NODE = "JWTFCharacterChat";
const HIDDEN = ["action", "user_message", "history_json"];
const SETTINGS = ["max_length", "temperature", "top_p", "top_k", "min_p", "repetition_penalty", "seed", "control_after_generate",
    "thinking", "context_messages", "presence_penalty", "mtp", "video_max_frames", "sampling_mode"];
const NUM_DEFAULTS = { max_length: 512, temperature: 0.7, top_p: 0.95, top_k: 64, min_p: 0.05, repetition_penalty: 1.05,
    context_messages: 40, presence_penalty: 0, video_max_frames: 8 };
const ACTIONS = ["none", "send", "regenerate"];
const DEFAULT_A = "#f0a030";
const DEFAULT_B = "#e0602a";

injectCss("jwtf-llm-base", BASE_CSS);
injectCss("jwtf-chat", `
.jwtf-chat{height:100%;--ca:${DEFAULT_A};--cb:${DEFAULT_B};position:relative}
.jwtf-chat .hdr{display:flex;gap:8px;align-items:center;padding:6px;border-bottom:1px solid #333;position:relative;z-index:1}
.jwtf-chat .av{width:40px;height:40px;border-radius:50%;object-fit:cover;background:#333;border:2px solid var(--ca);flex:none}
.jwtf-chat .nm{font-weight:700;font-size:14px}
.jwtf-chat .sub{font-size:10px;opacity:.7;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jwtf-chat .sub.err{color:#e46a6a;opacity:1;white-space:normal}
.jwtf-chat .body{flex:1;position:relative;min-height:120px;overflow:hidden}
.jwtf-chat .fx{position:absolute;inset:0;opacity:0;transition:opacity .6s;pointer-events:none;
 background:radial-gradient(60% 50% at 25% 30%,var(--ca),transparent 70%),radial-gradient(50% 60% at 80% 70%,var(--cb),transparent 70%);
 filter:blur(30px) saturate(1.2);animation:jwtf-drift 18s ease-in-out infinite alternate}
.jwtf-chat.fx-on .fx{opacity:.16}.jwtf-chat.fx-on.busy .fx{opacity:.3}
.jwtf-chat.gl-ok .fx{display:none}
.jwtf-chat .fxc{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;mix-blend-mode:screen;opacity:0;transition:opacity .6s}
.jwtf-chat.fx-on.gl-ok .fxc{opacity:1}
@keyframes jwtf-drift{to{transform:translate(4%,-3%) scale(1.15) rotate(6deg)}}
.jwtf-chat .log{position:absolute;inset:0;overflow:auto;padding:8px;display:flex;flex-direction:column;gap:8px}
.jwtf-chat .msg{display:flex;gap:6px;align-items:flex-start;animation:jwtf-in .25s both;max-width:92%}
.jwtf-chat .msg.user{align-self:flex-end;flex-direction:row-reverse}
.jwtf-chat .msg img{width:26px;height:26px;border-radius:50%;object-fit:cover;flex:none;background:#333}
.jwtf-chat .bub{background:rgba(40,40,46,.92);border:1px solid #3a3a42;border-radius:10px;padding:5px 9px;word-break:break-word;position:relative}
.jwtf-chat .msg.user .bub{background:color-mix(in srgb,var(--ca) 22%,#222);border-color:color-mix(in srgb,var(--ca) 45%,#333)}
.jwtf-chat .bub em{opacity:.75}.jwtf-chat .bub q{color:var(--ca);quotes:none}
.jwtf-chat .bub code{background:#111;padding:0 3px;border-radius:3px}
.jwtf-chat .acts{display:none;gap:2px;margin-top:3px}.jwtf-chat .msg:hover .acts{display:flex}
.jwtf-chat.busy .acts{display:none!important}
.jwtf-chat .acts button{padding:0 5px;font-size:10px}
.jwtf-chat .bub textarea{width:100%;min-width:220px;min-height:60px}
.jwtf-chat .swipe{display:flex;gap:4px;align-items:center;font-size:10px;opacity:.8;margin-top:3px}
.jwtf-chat .dots i{display:inline-block;width:5px;height:5px;margin:0 1px;border-radius:50%;background:currentColor;animation:jwtf-pulse 1s infinite}
.jwtf-chat .dots i:nth-child(2){animation-delay:.2s}.jwtf-chat .dots i:nth-child(3){animation-delay:.4s}
.jwtf-chat .errrow{color:#e46a6a;font-size:11px;padding:2px 8px}
.jwtf-chat .prog{display:none;align-items:center;gap:6px;padding:3px 6px;font-size:10px;border-top:1px solid #333}
.jwtf-chat .prog.show{display:flex}
.jwtf-chat .prog .jwtf-bar{flex:1}.jwtf-chat .prog .jwtf-bar>i{background:var(--ca)}
.jwtf-chat .comp{display:flex;gap:6px;padding:6px;border-top:1px solid #333;align-items:flex-end}
.jwtf-chat .comp textarea{flex:1;resize:none;height:32px;max-height:120px;padding:5px}
.jwtf-chat .send{background:var(--ca);color:#111;border-color:transparent;font-weight:700;height:32px}
.jwtf-chat .ftr{display:flex;gap:6px;align-items:center;padding:0 6px 6px;font-size:10px}
@media (prefers-reduced-motion: reduce){.jwtf-chat .fx{animation:none}.jwtf-chat .msg{animation:none}}
`);

const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function format(text) {
    return esc(text)
        .replace(/`([^`\n]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
        .replace(/(&quot;|“)([^\n]*?)(&quot;|”)/g, "<q>$1$2$3</q>")
        .replace(/\n/g, "<br>");
}

function validHistory(raw) {
    try {
        const v = typeof raw === "string" ? JSON.parse(raw) : raw;
        if (!Array.isArray(v)) return null;
        return v.every((m) => m && ["user", "assistant"].includes(m.role) && typeof m.content === "string") ? v : null;
    } catch {
        return null;
    }
}

// ----------------------------------------------------------------------------- theme

function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    if (max === min) return [0, 0, l];
    const d = max - min;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    const hue = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [hue / 6, s, l];
}

function avatarTheme(img) {
    try {
        const c = document.createElement("canvas");
        c.width = c.height = 24;
        const cx = c.getContext("2d", { willReadFrequently: true });
        cx.drawImage(img, 0, 0, 24, 24);
        const px = cx.getImageData(0, 0, 24, 24).data;
        let R = 0, G = 0, B = 0, W = 0;
        for (let i = 0; i < px.length; i += 4) {
            if (px[i + 3] < 128) continue;
            const [, s] = rgbToHsl(px[i], px[i + 1], px[i + 2]);
            const w = s * s * (Math.max(px[i], px[i + 1], px[i + 2]) / 255) + 0.01;
            R += px[i] * w; G += px[i + 1] * w; B += px[i + 2] * w; W += w;
        }
        if (!W) return null;
        const [hue, s, l] = rgbToHsl(R / W, G / W, B / W);
        if (s < 0.12) return null;
        const sat = Math.max(0.55, s);
        const la = Math.min(0.62, Math.max(0.5, l));
        const lb = Math.min(0.68, la + 0.05);
        const css = (hh, ss, ll) => `hsl(${Math.round((hh % 1) * 360)} ${Math.round(ss * 100)}% ${Math.round(ll * 100)}%)`;
        return [css(hue, sat, la), css(hue + 0.09, sat, lb)];
    } catch {
        return null; // tainted canvas or decode error
    }
}

// ----------------------------------------------------------------------------- ambient shader

const FX_VERT = `#version 300 es
in vec2 p;
void main(){ gl_Position = vec4(p, 0., 1.); }`;
const FX_FRAG = `#version 300 es
precision mediump float;
uniform vec2 uRes; uniform float uTime; uniform vec3 uA; uniform vec3 uB; uniform float uGain;
out vec4 o;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p); f = f * f * (3. - 2. * f);
  return mix(mix(hash(i), hash(i + vec2(1., 0.)), f.x), mix(hash(i + vec2(0., 1.)), hash(i + vec2(1., 1.)), f.x), f.y);
}
float fbm(vec2 p){ float v = 0., a = .5; for (int i = 0; i < 4; i++) { v += a * vnoise(p); p *= 2.02; a *= .5; } return v; }
void main(){
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 p = uv * vec2(uRes.x / uRes.y, 1.) * 2.2;
  float t = uTime * .05;
  vec2 q = vec2(fbm(p + t), fbm(p + vec2(5.2, 1.3) - t));
  float f = fbm(p + 3. * q + vec2(1.7, 9.2) + t * .6);
  vec3 c = mix(uA, uB, clamp(f * 1.4, 0., 1.)) * (f * f * 1.6 + .15);
  float vig = smoothstep(1.1, .2, length(uv - .5) * 1.3);
  o = vec4(c * vig * uGain, 1.);
}`;

function cssColorToRgb(css) {
    const hex = /^#([0-9a-f]{6})$/i.exec(css.trim());
    if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16) / 255);
    const m = /hsl\((\d+)\s+(\d+)%\s+(\d+)%\)/.exec(css);
    if (!m) return [0.94, 0.63, 0.19];
    const hh = +m[1], ss = +m[2] / 100, ll = +m[3] / 100;
    const k = (n) => (n + hh / 30) % 12;
    const a = ss * Math.min(ll, 1 - ll);
    return [0, 8, 4].map((n) => ll - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1)));
}

/** Full-panel "nebula" shader, WebGL2 only (no WebGPU path). Returns null when unavailable. */
function createFx(canvas, host, getGain) {
    const gl = canvas.getContext("webgl2", { alpha: false, antialias: false, powerPreference: "low-power" });
    if (!gl) return null;
    const compile = (type, src) => {
        const sh = gl.createShader(type);
        gl.shaderSource(sh, src);
        gl.compileShader(sh);
        return gl.getShaderParameter(sh, gl.COMPILE_STATUS) ? sh : null;
    };
    const vs = compile(gl.VERTEX_SHADER, FX_VERT);
    const fs = compile(gl.FRAGMENT_SHADER, FX_FRAG);
    if (!vs || !fs) return null;
    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const u = (n) => gl.getUniformLocation(prog, n);
    const uRes = u("uRes"), uTime = u("uTime"), uA = u("uA"), uB = u("uB"), uGain = u("uGain");
    const colors = { a: cssColorToRgb(DEFAULT_A), b: cssColorToRgb(DEFAULT_B) };
    let visible = true, raf = 0, last = 0, on = true;
    const t0 = performance.now();

    function resize() {
        const r = canvas.getBoundingClientRect();
        const w = Math.max(2, Math.round(r.width * 0.6));
        const hh = Math.max(2, Math.round(r.height * 0.6));
        if (canvas.width !== w || canvas.height !== hh) {
            canvas.width = w;
            canvas.height = hh;
            gl.viewport(0, 0, w, hh);
        }
    }
    function frame(now) {
        raf = 0;
        if (!on || !visible || document.hidden) return;
        raf = requestAnimationFrame(frame);
        if (now - last < 33) return; // at most about 30 fps
        last = now;
        resize();
        gl.uniform2f(uRes, canvas.width, canvas.height);
        gl.uniform1f(uTime, (now - t0) / 1000);
        gl.uniform3f(uA, ...colors.a);
        gl.uniform3f(uB, ...colors.b);
        gl.uniform1f(uGain, getGain((now - t0) / 1000));
        gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    const kick = () => {
        if (!raf && on && visible && !document.hidden) raf = requestAnimationFrame(frame);
    };
    const io = new IntersectionObserver((entries) => {
        visible = entries.some((e) => e.isIntersecting);
        kick();
    });
    io.observe(host);
    document.addEventListener("visibilitychange", kick);
    let disposed = false;
    const onLost = (e) => {
        e.preventDefault();
        on = false;
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
    };
    canvas.addEventListener("webglcontextlost", onLost);
    return {
        dispose() {
            if (disposed) return;
            disposed = true;
            on = false;
            io.disconnect();
            document.removeEventListener("visibilitychange", kick);
            canvas.removeEventListener("webglcontextlost", onLost);
            if (raf) cancelAnimationFrame(raf);
            raf = 0;
            gl.getExtension("WEBGL_lose_context")?.loseContext();
        },
        setColors(a, b) {
            colors.a = cssColorToRgb(a);
            colors.b = cssColorToRgb(b);
        },
        setEnabled(v) {
            on = v;
            kick();
        },
    };
}

// ----------------------------------------------------------------------------- panel

function setup(node) {
    node.properties = node.properties || {};
    const S = { history: [], info: null, busy: null, error: "", editing: -1, swipe: 0, avatarUrl: "",
        prog: { t0: 0, tFirst: 0, value: 0, max: 0, done: false, hideTimer: 0 }, gotExecuted: false };
    for (const n of HIDDEN) hideWidget(node, n);

    const W = (n) => findWidget(node, n);
    const charName = () => S.info?.name || "Character";
    const userName = () => String(W("user_name")?.value || "").trim() || "User";

    // header
    const av = h("img", { class: "av", alt: "" });
    const nm = h("div", { class: "nm", text: "…" });
    const sub = h("div", { class: "sub" });
    const fileInput = h("input", { type: "file", accept: ".png,.json,.safetensors", style: { display: "none" } });
    const fxBtn = h("button", { class: "jwtf-btn", text: "FX", title: "Ambient background" });
    const setBtn = h("button", { class: "jwtf-btn", text: "⚙", title: "Show sampling settings" });
    const hdr = h("div", { class: "hdr" }, [av, h("div", { class: "jwtf-grow", style: { minWidth: 0 } }, [nm, sub]),
        h("button", { class: "jwtf-btn", text: "⇪", title: "Upload a card (.png, .json, .safetensors)", onclick: () => fileInput.click() }),
        h("button", { class: "jwtf-btn", text: "↻", title: "Refresh the card list", onclick: () => refreshList() }),
        fxBtn, setBtn, fileInput]);

    const log = h("div", { class: "log" });
    const fxCanvas = h("canvas", { class: "fxc" });
    const body = h("div", { class: "body" }, [h("div", { class: "fx" }), fxCanvas, log]);
    const progBar = h("div", { class: "jwtf-bar indet" }, [h("i")]);
    const progText = h("span", { class: "jwtf-muted", text: "queued" });
    const prog = h("div", { class: "prog" }, [progBar, progText,
        h("button", { class: "jwtf-btn", text: "stop", onclick: () => api.interrupt() })]);
    const input = h("textarea", { placeholder: "Message…  (Enter to send, Shift+Enter for a new line)" });
    const sendBtn = h("button", { class: "jwtf-btn send", text: "Send" });
    const count = h("span", { class: "jwtf-grow jwtf-muted" });
    const newBtn = h("button", { class: "jwtf-btn", text: "New chat" });
    const copyBtn = h("button", { class: "jwtf-btn", text: "Copy chat" });
    const saveBtn = h("button", { class: "jwtf-btn", text: "Save chat" });
    const panel = h("div", { class: "jwtf-panel jwtf-chat" }, [hdr, body, prog,
        h("div", { class: "comp" }, [input, sendBtn]), h("div", { class: "ftr" }, [newBtn, copyBtn, saveBtn, count])]);
    shieldKeys(panel);

    // ---------------------------------------------------------------- widget repair
    function repair() {
        const cp = W("card_path");
        if (cp && /^(none|null|undefined)$/i.test(String(cp.value ?? "").trim())) cp.value = "";
        const hj = W("history_json");
        if (hj && !validHistory(hj.value)) {
            const donor = ["user_message", "action", "card_path"].map(W).find((w) => w && validHistory(w.value) && String(w.value).trim().startsWith("["));
            hj.value = donor ? donor.value : "[]";
            if (donor) donor.value = donor.name === "action" ? "none" : "";
        }
        const act = W("action");
        if (act && !ACTIONS.includes(act.value)) act.value = "none";
        if (act?.value === "none" && W("user_message")) W("user_message").value = "";
        for (const [name, def] of Object.entries(NUM_DEFAULTS)) {
            const w = W(name);
            if (!w) continue;
            const v = Number(w.value);
            const { min = -Infinity, max = Infinity } = w.options || {};
            if (!Number.isFinite(v) || v < min || v > max) w.value = def;
        }
        const seed = W("seed");
        if (seed && !Number.isFinite(Number(seed.value))) seed.value = 0;
        const cag = W("control_after_generate");
        if (cag && !(cag.options?.values || ["fixed", "increment", "decrement", "randomize"]).includes(cag.value)) cag.value = "randomize";
        const th = W("thinking");
        if (th && typeof th.value !== "boolean") th.value = false;
        const un = W("user_name");
        if (un && typeof un.value !== "string") un.value = "User";
        const mtp = W("mtp");
        if (mtp && !(mtp.options?.values || []).includes(mtp.value)) mtp.value = "auto";
        const sm = W("sampling_mode");
        if (sm && !["on", "off"].includes(sm.value)) sm.value = "on";
    }

    // ---------------------------------------------------------------- settings + fx
    function applySettings() {
        const show = !!node.properties.jwtf_chat_settings;
        setBtn.classList.toggle("on", show);
        for (const n of SETTINGS) {
            const w = W(n);
            if (!w) continue;
            if (!w._jwtfOrigSize) w._jwtfOrigSize = { cs: w.computeSize, type: w.type };
            w.hidden = !show;
            w.computeSize = show ? w._jwtfOrigSize.cs : () => [0, -4];
        }
        node.setSize([node.size[0], node.computeSize()[1]]);
        node.setDirtyCanvas(true, true);
    }
    setBtn.addEventListener("click", () => {
        node.properties.jwtf_chat_settings = !node.properties.jwtf_chat_settings;
        applySettings();
    });
    // Brightness rises with busy pulsing and token progress.
    const shader = (() => {
        try {
            const fxo = createFx(fxCanvas, body, (t) => {
                const p = S.prog;
                const frac = S.busy && p.max ? Math.min(1, p.value / p.max) : 0;
                return 0.35 + (S.busy ? 0.25 + 0.12 * Math.sin(t * 3) : 0) + frac * 0.3;
            });
            if (fxo) panel.classList.add("gl-ok");
            return fxo;
        } catch {
            return null; // no WebGL2: the CSS gradient stays
        }
    })();
    function applyFx() {
        if (node.properties.jwtf_chat_fx == null) {
            node.properties.jwtf_chat_fx = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        }
        panel.classList.toggle("fx-on", !!node.properties.jwtf_chat_fx);
        fxBtn.classList.toggle("on", !!node.properties.jwtf_chat_fx);
        shader?.setEnabled(!!node.properties.jwtf_chat_fx);
    }
    fxBtn.addEventListener("click", () => {
        node.properties.jwtf_chat_fx = !node.properties.jwtf_chat_fx;
        applyFx();
    });

    // ---------------------------------------------------------------- card info
    const cardKey = () => `${W("character")?.value ?? ""}|${String(W("card_path")?.value ?? "").trim()}`;
    function cardQuery() {
        return new URLSearchParams({ character: W("character")?.value ?? "", user: userName() });
    }
    async function loadInfo() {
        const key = cardKey();
        try {
            const resp = await api.fetchApi(`/jezzwtf/character/info?${cardQuery()}`);
            const data = await resp.json().catch(() => ({ error: `Card info failed (HTTP ${resp.status})` }));
            if (data.error) throw new Error(data.error);
            S.info = data;
            sub.classList.remove("err");
            const bits = [data.source === "refmod" && "RefMod", data.creator && `by ${data.creator}`,
                ...(data.tags || []).slice(0, 4), data.lore_entries && `${data.lore_entries} lore`].filter(Boolean);
            sub.textContent = bits.join(" · ");
            sub.title = data.creator_notes || "";
            nm.textContent = data.name;
            S.avatarUrl = api.apiURL(`/jezzwtf/character/avatar?${cardQuery()}&t=${Date.now()}`);
            av.src = S.avatarUrl;
        } catch (err) {
            S.info = null;
            nm.textContent = "No character";
            sub.classList.add("err");
            sub.textContent = String(err.message || err);
            av.removeAttribute("src");
            S.avatarUrl = "";
        }
        if (node.properties.jwtf_chat_card !== key || !S.history.length) reseed();
        node.properties.jwtf_chat_card = key;
        render();
    }
    av.addEventListener("load", () => {
        const theme = avatarTheme(av) || [DEFAULT_A, DEFAULT_B];
        panel.style.setProperty("--ca", theme[0]);
        panel.style.setProperty("--cb", theme[1]);
        shader?.setColors(theme[0], theme[1]);
    });
    av.addEventListener("error", () => av.removeAttribute("src"));

    function greetings() {
        return S.info ? [S.info.first_mes, ...(S.info.alternate_greetings || [])].filter((g) => g && g.trim()) : [];
    }
    function reseed() {
        const g = greetings();
        S.swipe = 0;
        S.history = g.length ? [{ role: "assistant", content: g[0] }] : [];
        saveHistory();
    }
    function saveHistory() {
        const w = W("history_json");
        if (w) w.value = JSON.stringify(S.history);
    }

    async function refreshList(select) {
        try {
            const data = await (await api.fetchApi("/jezzwtf/character/list")).json();
            const w = W("character");
            if (!w) return;
            w.options.values = data.cards || [];
            if (select && w.options.values.includes(select)) w.value = select;
            else if (!w.options.values.includes(w.value)) w.value = w.options.values[0];
            node.setDirtyCanvas(true, true);
        } catch (err) {
            S.error = `Could not refresh the list: ${err.message || err}`;
            render();
        }
    }
    fileInput.addEventListener("change", async () => {
        const file = fileInput.files?.[0];
        fileInput.value = "";
        if (!file) return;
        try {
            const res = await uploadToInput(file, "characters");
            const rel = res.subfolder && res.subfolder !== "characters" ? `${res.subfolder.replace(/^characters\/?/, "")}/${res.name}` : res.name;
            await refreshList(rel);
            const cp = W("card_path");
            if (cp) cp.value = "";
            S.history = [];
            await loadInfo();
        } catch (err) {
            S.error = String(err.message || err);
            render();
        }
    });

    // ---------------------------------------------------------------- rendering
    function bubble(m, i) {
        const isUser = m.role === "user";
        const b = h("div", { class: "bub" });
        if (S.editing === i) {
            const ta = h("textarea");
            ta.value = m.content;
            const save = () => {
                if (ta.value.trim()) m.content = ta.value;
                S.editing = -1;
                saveHistory();
                render();
            };
            b.append(ta, h("div", { class: "acts", style: { display: "flex" } }, [
                h("button", { class: "jwtf-btn", text: "Save", onclick: save }),
                h("button", { class: "jwtf-btn", text: "Cancel", onclick: () => { S.editing = -1; render(); } }),
            ]));
            setTimeout(() => ta.focus());
        } else {
            const content = h("div");
            content.innerHTML = format(m.content);
            b.append(content);
            const lastAssistant = !isUser && i === S.history.length - 1 && S.history.length > 1;
            b.append(h("div", { class: "acts" }, [
                h("button", { class: "jwtf-btn", text: "Edit", onclick: () => { S.editing = i; render(); } }),
                lastAssistant && h("button", { class: "jwtf-btn", text: "Regenerate", onclick: regenerate }),
                h("button", { class: "jwtf-btn", text: "Copy", onclick: () => copyText(m.content) }),
                h("button", { class: "jwtf-btn", text: "Delete", onclick: () => { S.history.splice(i, 1); saveHistory(); render(); } }),
            ]));
            const g = greetings();
            if (i === 0 && S.history.length === 1 && !isUser && g.length > 1) {
                const go = (d) => {
                    S.swipe = (S.swipe + d + g.length) % g.length;
                    m.content = g[S.swipe];
                    saveHistory();
                    render();
                };
                b.append(h("div", { class: "swipe" }, [h("button", { class: "jwtf-btn", text: "‹", onclick: () => go(-1) }),
                    h("span", { text: `${S.swipe + 1} / ${g.length}` }), h("button", { class: "jwtf-btn", text: "›", onclick: () => go(1) })]));
            }
        }
        const row = h("div", { class: `msg ${isUser ? "user" : "bot"}` }, [isUser ? "" : h("img", { src: S.avatarUrl || null }), b]);
        return row;
    }

    function render() {
        const rows = S.history.map(bubble);
        if (S.busy) {
            rows.push(h("div", { class: "msg bot" }, [h("img", { src: S.avatarUrl || null }),
                h("div", { class: "bub jwtf-muted" }, [`${charName()} is thinking `, h("span", { class: "dots" }, [h("i"), h("i"), h("i")])])]));
        }
        if (S.error) rows.push(h("div", { class: "errrow", text: S.error }));
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
        log.replaceChildren(...rows);
        if (atBottom || S.busy) log.scrollTop = log.scrollHeight;
        panel.classList.toggle("busy", !!S.busy);
        sendBtn.disabled = !!S.busy;
        count.textContent = `${S.history.length} message${S.history.length === 1 ? "" : "s"}`;
    }

    // ---------------------------------------------------------------- progress
    let progTimer = 0;
    function progStart() {
        clearTimeout(S.prog.hideTimer);
        Object.assign(S.prog, { t0: 0, tFirst: 0, value: 0, max: 0, done: false });
        prog.classList.add("show");
        progBar.className = "jwtf-bar indet";
        progText.textContent = "queued";
        clearInterval(progTimer);
        progTimer = setInterval(paintProg, 250);
    }
    function paintProg() {
        const p = S.prog;
        if (p.done || !p.t0) return;
        const now = performance.now();
        const el = (now - p.t0) / 1000;
        if (!p.max) {
            progText.textContent = `prefill · ${el.toFixed(1)}s`;
            return;
        }
        const genT = p.tFirst ? (now - p.tFirst) / 1000 : 0;
        const rate = genT > 0 ? p.value / genT : 0;
        const eta = rate > 0 ? (p.max - p.value) / rate : 0;
        progBar.className = "jwtf-bar";
        progBar.firstChild.style.width = `${Math.min(100, (p.value / p.max) * 100)}%`;
        progText.textContent = `${p.value} / ${p.max} tok · ${el.toFixed(1)}s${rate ? ` · ${rate.toFixed(1)} tok/s · ETA ${eta.toFixed(0)}s` : ""}`;
    }
    function progEnd(text) {
        S.prog.done = true;
        clearInterval(progTimer);
        progBar.className = "jwtf-bar done";
        progText.textContent = text;
        S.prog.hideTimer = setTimeout(() => prog.classList.remove("show"), 6000);
    }

    // ---------------------------------------------------------------- send / regenerate
    function queue(action, text, before) {
        repair();
        W("action").value = action;
        W("user_message").value = text;
        W("history_json").value = JSON.stringify(before);
        S.gotExecuted = false;
        S.error = "";
        progStart();
        app.queuePrompt(0, 1);
    }
    function send() {
        const text = input.value.trim();
        if (!text || S.busy) return;
        S.busy = { kind: "send", text };
        queue("send", text, S.history);
        S.history.push({ role: "user", content: text });
        input.value = "";
        grow();
        render();
    }
    function regenerate() {
        if (S.busy) return;
        const popped = [];
        while (S.history.length > 1 && S.history[S.history.length - 1].role === "assistant") popped.unshift(S.history.pop());
        S.busy = { kind: "regenerate", popped };
        queue("regenerate", "", S.history);
        render();
    }
    function revert(message) {
        const b = S.busy;
        if (!b) return;
        if (b.kind === "send") {
            const last = S.history[S.history.length - 1];
            if (last?.role === "user" && last.content === b.text) S.history.pop();
            input.value = b.text;
            grow();
        } else S.history.push(...b.popped);
        S.busy = null;
        S.error = message;
        W("action").value = "none";
        W("user_message").value = "";
        saveHistory();
        progEnd(message);
        render();
    }

    sendBtn.addEventListener("click", send);
    const grow = () => {
        input.style.height = "32px";
        input.style.height = `${Math.min(120, input.scrollHeight)}px`;
    };
    input.addEventListener("input", grow);
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    });
    let newArmed = 0;
    newBtn.addEventListener("click", () => {
        if (S.history.length > 1 && Date.now() - newArmed > 2200) {
            newArmed = Date.now();
            newBtn.textContent = "Click again";
            setTimeout(() => (newBtn.textContent = "New chat"), 2300);
            return;
        }
        newBtn.textContent = "New chat";
        reseed();
        render();
    });
    copyBtn.addEventListener("click", async () => {
        const text = S.history.map((m) => `${m.role === "assistant" ? charName() : userName()}: ${m.content}`).join("\n\n");
        copyBtn.textContent = (await copyText(text)) ? "Copied" : "Copy failed";
        setTimeout(() => (copyBtn.textContent = "Copy chat"), 1200);
    });

    saveBtn.addEventListener("click", async () => {
        saveBtn.disabled = true;
        try {
            const resp = await api.fetchApi("/jezzwtf/character/save_chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ history: S.history, character_name: charName(), user_name: userName() }),
            });
            const data = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }));
            if (data.error) throw new Error(data.error);
            saveBtn.title = data.saved;
            saveBtn.textContent = "Saved";
        } catch (err) {
            saveBtn.title = String(err.message || err);
            saveBtn.textContent = "Save failed";
        }
        saveBtn.disabled = false;
        setTimeout(() => (saveBtn.textContent = "Save chat"), 2500);
    });

    // ---------------------------------------------------------------- widget
    const widget = node.addDOMWidget("nbc_panel", "jwtf_chat", panel, {
        serialize: false,
        getMinHeight: () => 420,
    });
    widget.serialize = false;

    for (const n of ["character", "card_path", "user_name"]) {
        const w = W(n);
        if (!w) continue;
        const cb = w.callback;
        w.callback = function (...a) {
            const r = cb?.apply(this, a);
            loadInfo();
            return r;
        };
    }

    return {
        dispose() {
            clearInterval(progTimer);
            clearTimeout(S.prog.hideTimer);
            shader?.dispose();
        },
        init() {
            repair();
            S.history = validHistory(W("history_json")?.value) || [];
            applySettings();
            applyFx();
            render();
            loadInfo();
        },
        executed(msg) {
            S.gotExecuted = true;
            let data = null;
            try {
                data = JSON.parse(msg?.jwtf_chat?.[0] ?? "null");
            } catch {
                data = null;
            }
            if (!data) return;
            if (data.card?.name) {
                // The node ran with the card it really resolved (combo, card_path or a wired path).
                S.info = data.card;
                sub.classList.remove("err");
                const bits = [data.card.source === "refmod" && "RefMod", data.card.creator && `by ${data.card.creator}`,
                    ...(data.card.tags || []).slice(0, 4), data.card.lore_entries && `${data.card.lore_entries} lore`].filter(Boolean);
                sub.textContent = bits.join(" · ");
                sub.title = data.card.creator_notes || "";
                nm.textContent = data.card.name;
                if (data.card.avatar) {
                    S.avatarUrl = data.card.avatar;
                    av.src = S.avatarUrl;
                }
            }
            S.history = validHistory(data.history) || S.history;
            S.busy = null;
            S.error = "";
            W("action").value = "none";
            W("user_message").value = "";
            saveHistory();
            const st = data.stats;
            progEnd(st && st.seconds > 0
                ? `${st.tokens} tokens in ${st.seconds}s · ${(st.tokens / st.seconds).toFixed(1)} tok/s`
                : "Done");
            render();
        },
        executing() {
            if (!S.busy) return;
            S.prog.t0 = performance.now();
            progText.textContent = "prefill";
        },
        progress(d) {
            if (!S.busy) return;
            if (!S.prog.tFirst && d.value > 0) S.prog.tFirst = performance.now();
            S.prog.value = d.value;
            S.prog.max = d.max;
            if (!S.prog.t0) S.prog.t0 = performance.now();
            paintProg();
        },
        failed(message) {
            revert(message);
        },
        finished() {
            if (!S.busy) return;
            setTimeout(() => {
                if (S.busy && !S.gotExecuted) revert("The node didn't run (muted, bypassed or cached). Change a value or the seed and try again.");
            }, 600);
        },
        get busy() {
            return !!S.busy;
        },
        repair,
    };
}

const chats = new Set();
const forNode = (id) => {
    const key = String(id ?? "");
    const tail = key.split(":").pop();
    return [...chats].filter((n) => String(n.id) === key || String(n.id) === tail);
};

app.registerExtension({
    name: "JezzWTF.LLMCards.CharacterChat",
    setup() {
        api.addEventListener("executing", (e) => {
            const id = e.detail?.node ?? e.detail;
            for (const n of forNode(id)) n._jwtfChat?.executing();
        });
        api.addEventListener("progress", (e) => {
            for (const n of forNode(e.detail?.node)) n._jwtfChat?.progress(e.detail);
        });
        api.addEventListener("execution_error", (e) => {
            for (const n of chats) if (n._jwtfChat?.busy) n._jwtfChat.failed(e.detail?.exception_message || "Execution failed");
        });
        api.addEventListener("execution_interrupted", () => {
            for (const n of chats) if (n._jwtfChat?.busy) n._jwtfChat.failed("Interrupted");
        });
        api.addEventListener("execution_success", () => {
            for (const n of chats) n._jwtfChat?.finished();
        });
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = created?.apply(this, arguments);
            this._jwtfChat = setup(this);
            chats.add(this);
            this.setSize([520, 720]);
            // Defer so saved widget values (onConfigure) land before the first load.
            requestAnimationFrame(() => {
                if (!this._jwtfChatInit) {
                    this._jwtfChatInit = true;
                    this._jwtfChat.init();
                }
            });
            return r;
        };
        const configure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = configure?.apply(this, arguments);
            this._jwtfChatInit = true;
            this._jwtfChat?.init();
            return r;
        };
        const removed = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            chats.delete(this);
            this._jwtfChat?.dispose();
            return removed?.apply(this, arguments);
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = executed?.apply(this, arguments);
            this._jwtfChat?.executed(message);
            return r;
        };
    },
});
