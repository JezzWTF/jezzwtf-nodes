// Character Card PNG Baker preview: a flip card with stats, excerpts and a download link.
import { app } from "../../../scripts/app.js";
import { api, BASE_CSS, h, injectCss } from "./jwtf_ui.js";

const NODE = "JWTFV2PNGBaker";
const HEIGHT = 462;
const MIN_W = 330;
const METERS = [["description", "Description", 3000], ["first_mes", "Greeting", 2000], ["mes_example", "Examples", 1500]];
const RARITY = { common: "#9aa4b1", rare: "#4a8fe0", epic: "#a35ee8", legendary: "#f0a030" };

injectCss("jwtf-llm-base", BASE_CSS);
injectCss("jwtf-card", `
.jwtf-cardwrap{height:${HEIGHT - 8}px;display:flex;flex-direction:column;gap:4px;padding:4px;box-sizing:border-box;
 font:12px/1.35 system-ui,sans-serif;color:#e8e8e8}
.jwtf-card{flex:1;perspective:900px;cursor:pointer;min-height:0}
.jwtf-card .inner{position:relative;width:100%;height:100%;transition:transform .55s cubic-bezier(.2,.7,.2,1);transform-style:preserve-3d}
.jwtf-card.flipped .inner{transform:rotateY(180deg)}
.jwtf-card .face{position:absolute;inset:0;backface-visibility:hidden;border-radius:10px;overflow:hidden;display:flex;flex-direction:column;
 background:linear-gradient(160deg,#26262c,#18181c);border:2px solid var(--rar,#666);box-shadow:0 0 0 1px #000 inset}
.jwtf-card .back{transform:rotateY(180deg);padding:10px;gap:8px;overflow:auto}
.jwtf-card .head{display:flex;align-items:center;gap:6px;padding:6px 8px}
.jwtf-card .name{flex:1;font-weight:700;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jwtf-card .gem{width:12px;height:12px;transform:rotate(45deg);background:var(--rar,#666);box-shadow:0 0 8px var(--rar,#666)}
.jwtf-card .art{flex:1;min-height:80px;margin:0 8px;border-radius:6px;background:#111 center/cover no-repeat;position:relative}
.jwtf-card .tags{display:flex;flex-wrap:wrap;gap:3px;padding:6px 8px 0}
.jwtf-card .tags span{font-size:10px;border-radius:8px;padding:0 6px;background:rgba(255,255,255,.08);animation:jwtf-in .35s both}
@keyframes jwtf-in{from{opacity:0;transform:translateY(4px)}}
.jwtf-card .meters{padding:6px 8px;display:grid;gap:3px}
.jwtf-card .meter{display:grid;grid-template-columns:70px 1fr 40px;align-items:center;gap:6px;font-size:10px}
.jwtf-card .meter b{height:4px;border-radius:2px;background:#333;position:relative;overflow:hidden}
.jwtf-card .meter b i{position:absolute;inset:0 auto 0 0;background:var(--rar,#888)}
.jwtf-card .foot{display:flex;justify-content:space-between;padding:4px 8px 7px;font-size:10px;opacity:.75}
.jwtf-card .stamp{position:absolute;top:40%;left:50%;transform:translate(-50%,-50%) rotate(-12deg);font:900 30px system-ui;letter-spacing:.12em;
 color:var(--rar,#f0a030);border:3px solid currentColor;padding:2px 10px;border-radius:6px;opacity:0;pointer-events:none}
.jwtf-card.baked .stamp{animation:jwtf-stamp 1.6s ease-out both}
@keyframes jwtf-stamp{0%{opacity:0;transform:translate(-50%,-50%) rotate(-12deg) scale(2)}15%{opacity:1;transform:translate(-50%,-50%) rotate(-12deg) scale(1)}75%{opacity:1}100%{opacity:0}}
.jwtf-card.forging .face{box-shadow:0 0 18px var(--rar,#f0a030),0 0 0 1px #000 inset;animation:jwtf-pulse 1s infinite}
.jwtf-card .back h4{margin:0;font-size:11px;opacity:.7;text-transform:uppercase;letter-spacing:.05em}
.jwtf-card .back p{margin:0;white-space:pre-wrap}
.jwtf-card .pills{display:flex;gap:4px;flex-wrap:wrap}
.jwtf-card .pills span{font-size:10px;border:1px solid #555;border-radius:8px;padding:0 6px}
.jwtf-card .empty{flex:1;display:flex;align-items:center;justify-content:center;opacity:.5;text-align:center;padding:20px}
.jwtf-cardwrap .status{font-size:10px;opacity:.75;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jwtf-cardwrap .status.err{color:#e46a6a;opacity:1}
.jwtf-card .foil,.jwtf-card .glare{position:absolute;inset:0;pointer-events:none;border-radius:inherit}
.jwtf-card .foil{background:linear-gradient(115deg,#ff5e5e,#ffd45e,#7dff7d,#5ec8ff,#b45eff,#ff5e5e);background-size:300% 300%;
 background-position:var(--fx-x,50%) var(--fx-y,50%);mix-blend-mode:color-dodge;opacity:calc(var(--fx,.2)*.4)}
.jwtf-card .glare{background:radial-gradient(circle at var(--gx,50%) var(--gy,50%),rgba(255,255,255,.55),transparent 55%);
 mix-blend-mode:overlay;opacity:0;transition:opacity .2s}
.jwtf-card:hover .glare{opacity:calc(var(--fx,.2)*.9 + .1)}
.jwtf-card .embers{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:4}
.jwtf-card .ring{position:absolute;left:50%;top:40%;width:20px;height:20px;margin:-10px;border-radius:50%;
 border:3px solid var(--rar,#f0a030);opacity:0;pointer-events:none;z-index:4}
.jwtf-card.baked .ring{animation:jwtf-ring .9s ease-out both}
@keyframes jwtf-ring{0%{opacity:.9;transform:scale(1)}100%{opacity:0;transform:scale(18)}}
.jwtf-card.landing .inner{animation:jwtf-land .5s cubic-bezier(.2,1.4,.4,1)}
@keyframes jwtf-land{from{transform:translateY(-14px) scale(1.06)}to{transform:none}}
@media (prefers-reduced-motion: reduce){.jwtf-card .inner{transition:none}.jwtf-card.baked .stamp,.jwtf-card .tags span,
 .jwtf-card.baked .ring,.jwtf-card.landing .inner{animation:none}.jwtf-card .glare{display:none}}
`);

const RARITY_FX = { common: 0.15, rare: 0.4, epic: 0.7, legendary: 1 };

const reduceMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function viewUrl(p) {
    const q = new URLSearchParams({ filename: p.filename, subfolder: p.subfolder || "", type: p.type || "output", t: String(Date.now()) });
    return api.apiURL(`/view?${q}`);
}

function setup(node) {
    const card = h("div", { class: "jwtf-card" });
    const inner = h("div", { class: "inner" });
    const front = h("div", { class: "face front" });
    const back = h("div", { class: "face back" });
    inner.append(front, back);
    card.append(inner);
    const flipBtn = h("button", { class: "jwtf-btn", text: "Flip", disabled: true });
    const dl = h("a", { class: "jwtf-btn", text: "Download", style: { display: "none", textDecoration: "none" } });
    const status = h("div", { class: "status jwtf-grow", text: "Run the node to bake a card." });
    const wrap = h("div", { class: "jwtf-cardwrap" }, [card, h("div", { class: "jwtf-row", style: { padding: 0 } }, [status, dl, flipBtn])]);
    let data = null;

    const flip = () => {
        if (!data) return;
        inner.style.transform = "";
        card.classList.toggle("flipped");
    };
    card.addEventListener("click", flip);
    flipBtn.addEventListener("click", flip);

    // ---- effects: eased 3D tilt, foil/glare, ember particles (about 33 fps, paused when hidden)
    const foil = h("div", { class: "foil" });
    const glare = h("div", { class: "glare" });
    const embers = h("canvas", { class: "embers" });
    const ring = h("div", { class: "ring" });
    card.append(embers, ring);
    const ectx = embers.getContext("2d");
    const fx = { tx: 0, ty: 0, cx: 0, cy: 0, active: false, forging: false, visible: true, raf: 0, last: 0, parts: [], w: 0, h: 0 };

    function spawn(n, burst) {
        for (let i = 0; i < n; i++) {
            const angle = burst ? Math.random() * Math.PI * 2 : -Math.PI / 2 + (Math.random() - 0.5) * 0.8;
            const speed = burst ? 40 + Math.random() * 120 : 12 + Math.random() * 28;
            fx.parts.push({
                x: burst ? fx.w / 2 : Math.random() * fx.w, y: burst ? fx.h * 0.4 : fx.h + 4,
                vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
                life: 0, max: 1.2 + Math.random() * 1.8, size: 1 + Math.random() * 2,
            });
        }
        if (fx.parts.length > 160) fx.parts.splice(0, fx.parts.length - 160);
    }

    function tick(now) {
        fx.raf = 0;
        if (!fx.visible || document.hidden) return;
        fx.raf = requestAnimationFrame(tick);
        // eased tilt every frame
        fx.cx += (fx.tx - fx.cx) * 0.15;
        fx.cy += (fx.ty - fx.cy) * 0.15;
        if (!card.classList.contains("flipped") && !reduceMotion() && !card.classList.contains("landing")) {
            inner.style.transform = fx.active || Math.abs(fx.cx) + Math.abs(fx.cy) > 0.002
                ? `rotateY(${fx.cx * 12}deg) rotateX(${-fx.cy * 12}deg)` : "";
        }
        if (now - fx.last < 30) return;
        const dt = Math.min(0.1, (now - fx.last) / 1000);
        fx.last = now;
        if (reduceMotion()) {
            ectx.clearRect(0, 0, fx.w, fx.h);
            return;
        }
        const rate = RARITY_FX[data?.info?.rarity] ?? 0.15;
        if (Math.random() < (fx.forging ? 0.9 : 0.12 + rate * 0.25)) spawn(fx.forging ? 3 : 1, false);
        const speedUp = fx.forging ? 2.2 : 1;
        ectx.clearRect(0, 0, fx.w, fx.h);
        ectx.fillStyle = getComputedStyle(card).getPropertyValue("--rar").trim() || "#f0a030";
        fx.parts = fx.parts.filter((p) => {
            p.life += dt * speedUp;
            p.x += p.vx * dt * speedUp;
            p.y += p.vy * dt * speedUp;
            p.vx *= 0.99;
            if (p.life >= p.max) return false;
            ectx.globalAlpha = Math.max(0, 1 - p.life / p.max) * 0.8;
            ectx.beginPath();
            ectx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
            ectx.fill();
            return true;
        });
        ectx.globalAlpha = 1;
    }
    function resume() {
        if (!fx.raf && fx.visible && !document.hidden) fx.raf = requestAnimationFrame(tick);
    }
    const resizeObs = new ResizeObserver(() => {
        const r = embers.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        fx.w = Math.max(1, Math.round(r.width));
        fx.h = Math.max(1, Math.round(r.height));
        embers.width = Math.round(fx.w * dpr);
        embers.height = Math.round(fx.h * dpr);
        ectx.setTransform(dpr, 0, 0, dpr, 0, 0);
    });
    resizeObs.observe(card);
    const visObs = new IntersectionObserver((entries) => {
        fx.visible = entries.some((e) => e.isIntersecting);
        resume();
    });
    visObs.observe(card);
    document.addEventListener("visibilitychange", resume);
    resume();

    card.addEventListener("pointermove", (e) => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        fx.active = true;
        fx.tx = x;
        fx.ty = y;
        card.style.setProperty("--gx", `${(x + 0.5) * 100}%`);
        card.style.setProperty("--gy", `${(y + 0.5) * 100}%`);
        card.style.setProperty("--fx-x", `${(x + 0.5) * 100}%`);
        card.style.setProperty("--fx-y", `${(y + 0.5) * 100}%`);
        const art = front.querySelector(".art");
        if (art && !reduceMotion()) art.style.backgroundPosition = `${50 + x * 8}% ${50 + y * 8}%`;
    });
    card.addEventListener("pointerleave", () => {
        fx.active = false;
        fx.tx = 0;
        fx.ty = 0;
        const art = front.querySelector(".art");
        if (art) art.style.backgroundPosition = "";
    });

    function renderEmpty(text) {
        front.replaceChildren(h("div", { class: "empty", text }));
        back.replaceChildren();
    }

    function render({ previews, info }, { animate, restored }) {
        data = { previews, info };
        card.style.setProperty("--rar", RARITY[info.rarity] || "#888");
        card.style.setProperty("--fx", String(RARITY_FX[info.rarity] ?? 0.15));
        flipBtn.disabled = false;
        const name = h("div", { class: "name" });
        const art = h("div", { class: "art" }, [h("div", { class: "stamp", text: "BAKED" })]);
        if (previews?.[0]) art.style.backgroundImage = `url("${viewUrl(previews[0])}")`;
        const meters = METERS.map(([key, label, max]) => {
            const n = info.chars?.[key] || 0;
            return h("div", { class: "meter" }, [h("span", { text: label }), h("b", {}, [h("i", { style: { width: `${Math.min(100, (n / max) * 100)}%` } })]),
                h("span", { text: n.toLocaleString() })]);
        });
        const batch = previews?.length > 1 ? ` · ×${previews.length}` : "";
        front.replaceChildren(
            h("div", { class: "head" }, [name, h("span", { class: "gem", title: info.rarity })]),
            art,
            h("div", { class: "tags" }, (info.tags || []).slice(0, 10).map((t, i) => h("span", { text: t, style: { animationDelay: `${i * 40}ms` } }))),
            h("div", { class: "meters" }, meters),
            h("div", { class: "foot" }, [h("span", { text: info.creator ? `by ${info.creator}` : "" }),
                h("span", { text: `V${info.spec_version} · ~${info.tokens} tok · ${info.kb} KB${batch}` })]),
        );
        front.append(foil, glare);
        const excerpt = (title, text) => [h("h4", { text: title }), h("p", { text: text || "—" })];
        back.replaceChildren(
            ...(restored
                ? [h("p", { class: "jwtf-muted", text: "Excerpts are not saved in the workflow. Run the node again to see them." })]
                : [...excerpt("Description", info.excerpt_description), ...excerpt("First message", info.excerpt_first_mes)]),
            h("div", { class: "pills" }, [h("span", { text: `${info.alt_greetings} alt greetings` }),
                h("span", { text: `${info.book_entries} lorebook entries` }), h("span", { text: `~${info.tokens} tokens` }),
                h("span", { text: info.rarity })]),
        );
        if (animate && !reduceMotion()) {
            let i = 0;
            const full = info.name || "Unnamed";
            const tick = () => {
                name.textContent = full.slice(0, ++i);
                if (i < full.length) setTimeout(tick, 28);
            };
            tick();
            card.classList.remove("baked", "landing");
            void card.offsetWidth;
            card.classList.add("baked", "landing");
            setTimeout(() => card.classList.remove("landing"), 600);
            spawn(70, true);
            resume();
        } else name.textContent = info.name || "Unnamed";
        if (previews?.[0]) {
            dl.href = viewUrl(previews[0]);
            dl.download = previews[0].filename;
            dl.style.display = "";
        }
    }

    const widget = node.addDOMWidget("card_preview", "jwtf_card_preview", wrap, {
        serialize: false,
        getMinHeight: () => HEIGHT,
        getMaxHeight: () => HEIGHT,
    });
    widget.serialize = false;
    renderEmpty("No card yet");

    return {
        dispose() {
            fx.visible = false;
            if (fx.raf) cancelAnimationFrame(fx.raf);
            fx.raf = 0;
            resizeObs.disconnect();
            visObs.disconnect();
            document.removeEventListener("visibilitychange", resume);
        },
        forging(on) {
            card.classList.toggle("forging", on);
            fx.forging = on;
            if (on) resume();
            if (on) {
                status.classList.remove("err");
                status.textContent = "Baking…";
            }
        },
        failed(text) {
            card.classList.remove("forging");
            fx.forging = false;
            status.classList.add("err");
            status.textContent = text;
        },
        executed(msg) {
            const info = msg?.card_info?.[0];
            if (!info) return;
            const previews = msg.card_preview || [];
            card.classList.remove("forging", "flipped");
            render({ previews, info }, { animate: true, restored: false });
            const { excerpt_description, excerpt_first_mes, ...safe } = info;
            node.properties = node.properties || {};
            node.properties.jwtf_last_bake = { previews, info: safe };
            status.classList.remove("err");
            const p = previews[0];
            status.textContent = `${p ? `${p.subfolder ? `${p.subfolder}/` : ""}${p.filename}` : "Saved"}${info.notes?.[0] ? ` · ${info.notes[0]}` : ""}`;
            status.title = (info.notes || []).join("\n");
        },
        restore() {
            const saved = node.properties?.jwtf_last_bake;
            if (saved?.info) render(saved, { animate: false, restored: true });
        },
    };
}

const cards = new Set();

app.registerExtension({
    name: "JezzWTF.LLMCards.CardPreview",
    setup() {
        api.addEventListener("executing", (e) => {
            const id = e.detail?.node ?? e.detail;
            for (const n of cards) n._jwtfCard?.forging(id != null && String(n.id) === String(id).split(":").pop());
        });
        const fail = (label) => (e) => {
            const id = e.detail?.node_id;
            for (const n of cards) {
                if (id == null || String(n.id) === String(id).split(":").pop()) n._jwtfCard?.failed(`${label}${e.detail?.exception_message ? `: ${e.detail.exception_message}` : ""}`);
            }
        };
        api.addEventListener("execution_error", fail("Bake failed"));
        api.addEventListener("execution_interrupted", fail("Interrupted"));
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE) return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = created?.apply(this, arguments);
            this._jwtfCard = setup(this);
            cards.add(this);
            this.setSize([Math.max(MIN_W, this.size[0]), this.computeSize()[1]]);
            return r;
        };
        const computeSize = nodeType.prototype.computeSize;
        nodeType.prototype.computeSize = function () {
            const s = computeSize ? computeSize.apply(this, arguments) : [MIN_W, HEIGHT];
            return [Math.max(MIN_W, s[0]), s[1]];
        };
        const resize = nodeType.prototype.onResize;
        nodeType.prototype.onResize = function (size) {
            if (size[0] < MIN_W) size[0] = MIN_W;
            return resize?.apply(this, arguments);
        };
        const configure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = configure?.apply(this, arguments);
            if (this.size[0] < MIN_W) this.setSize([MIN_W, this.size[1]]);
            this._jwtfCard?.restore();
            return r;
        };
        const removed = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            cards.delete(this);
            this._jwtfCard?.dispose();
            return removed?.apply(this, arguments);
        };
        const executed = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = executed?.apply(this, arguments);
            this._jwtfCard?.executed(message);
            return r;
        };
    },
});
