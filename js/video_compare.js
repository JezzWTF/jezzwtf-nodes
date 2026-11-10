import { app } from "../../scripts/app.js";

// Video Compare — synchronized A/B comparison widget.
// The Python node saves both videos to temp and returns them in ui.comparisons.
// A is always the master clock; B follows it at A.currentTime + offset.

const STATE_KEY = "video_compare";
const DRIFT_LIMIT = 0.12; // seconds B may drift from A before it is re-seeked
const CONTROLS_H = 72;
const STYLE_ID = "jezzwtf-video-compare-style";

const CSS = `
.jvc-root { display: flex; flex-direction: column; width: 100%; height: 100%; box-sizing: border-box;
    padding: 4px 6px 6px; font: 12px system-ui, sans-serif; color: #ddd; user-select: none; }
.jvc-media { position: relative; flex: 1 1 auto; min-height: 0; overflow: hidden; border-radius: 8px;
    background: #000; touch-action: none; cursor: pointer; }
.jvc-media.jvc-wipe { cursor: ew-resize; }
.jvc-media.jvc-wipe.jvc-vert { cursor: ns-resize; }
.jvc-media video { position: absolute; top: 0; left: 0; width: 100%; height: 100%;
    object-fit: contain; display: block; pointer-events: none; }
.jvc-divider { position: absolute; z-index: 3; background: #f5a742; box-shadow: 0 0 6px rgba(0,0,0,.8);
    pointer-events: none; }
.jvc-divider::after { content: ""; position: absolute; top: 50%; left: 50%; width: 14px; height: 14px;
    transform: translate(-50%, -50%); border-radius: 50%; background: #f5a742; }
.jvc-badge { position: absolute; z-index: 4; font-weight: 700; font-size: 11px; color: #fff;
    background: rgba(0,0,0,.55); border: 1px solid rgba(255,255,255,.25); padding: 1px 7px;
    border-radius: 6px; pointer-events: none; }
.jvc-empty { position: absolute; inset: 0; z-index: 2; display: grid; place-items: center;
    color: #9999aa; text-align: center; padding: 20px; white-space: pre-line; }
.jvc-controls { flex: 0 0 auto; display: flex; align-items: center; gap: 4px; margin-top: 4px; }
.jvc-spacer { flex: 1 1 auto; }
.jvc-btn { flex: 0 0 auto; min-width: 26px; height: 26px; padding: 0 5px; color: #ddd; background: #2b2b2f;
    border: 1px solid #3d3d44; border-radius: 6px; cursor: pointer; font: 12px system-ui, sans-serif; }
.jvc-btn:hover { background: #38383f; }
.jvc-btn.jvc-on { color: #f5a742; border-color: #f5a742; }
.jvc-range { flex: 0 0 auto; width: 100%; margin: 6px 0 0; accent-color: #f5a742; cursor: pointer; }
.jvc-time { flex: 0 0 auto; color: #aaa; font-variant-numeric: tabular-nums; white-space: nowrap; }
.jvc-sel { flex: 0 0 auto; height: 26px; color: #ddd; background: #2b2b2f; border: 1px solid #3d3d44;
    border-radius: 6px; cursor: pointer; }
`;

function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
}

function el(tag, className, text) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text != null) e.textContent = text;
    return e;
}

function viewUrl(entry) {
    const q = new URLSearchParams({
        filename: entry.filename,
        subfolder: entry.subfolder ?? "",
        type: entry.type ?? "temp",
        t: String(Date.now()), // temp filenames repeat between runs; defeat the cache
    });
    return app.api.apiURL("/view?" + q.toString());
}

function fmt(t) {
    if (!Number.isFinite(t)) return "00:00.0";
    const m = Math.floor(t / 60);
    const s = t - m * 60;
    return `${String(m).padStart(2, "0")}:${s < 10 ? "0" : ""}${s.toFixed(1)}`;
}

// Resolves once the video has decoded data for its current position (or errored).
function whenReady(v) {
    if (v.readyState >= 2) return Promise.resolve(true);
    return new Promise((resolve) => {
        const done = (ok) => {
            v.removeEventListener("loadeddata", onOk);
            v.removeEventListener("error", onErr);
            resolve(ok);
        };
        const onOk = () => done(true);
        const onErr = () => done(false);
        v.addEventListener("loadeddata", onOk);
        v.addEventListener("error", onErr);
    });
}

function seek(v, t) {
    if (!Number.isFinite(v.duration)) return Promise.resolve();
    t = Math.min(Math.max(t, 0), v.duration);
    if (Math.abs(v.currentTime - t) < 0.001) return Promise.resolve();
    return new Promise((resolve) => {
        v.addEventListener("seeked", () => resolve(), { once: true });
        v.currentTime = t;
    });
}

app.registerExtension({
    name: "JezzWTF.VideoCompare",

    nodeCreated(node) {
        if (node.comfyClass !== "VideoCompare" || node.__jvc) return;
        ensureStyle();
        node.__jvc = setup(node);
    },
});

function setup(node) {
    // Persisted view preferences + the last result, so the preview survives a reload.
    const prefs = {
        mode: "slider",   // slider | side | diff
        swapped: false,   // show B on the left/top
        vertical: false,  // wipe top/bottom instead of left/right
        muted: true,
        loop: true,
        divider: 0.5,
        src: null,
    };
    const save = () => { node.properties[STATE_KEY] = { ...prefs }; };

    let ready = false;
    let playing = false;
    let scrubbing = false;
    let dragging = false;
    let loadToken = 0;
    let sizedFor = null;
    let alive = true;
    const lifetime = new AbortController();

    // ------------------------------------------------------------------- DOM
    const root = el("div", "jvc-root");
    const media = el("div", "jvc-media");
    const va = el("video");
    const vb = el("video");
    for (const v of [va, vb]) {
        v.muted = true;
        v.playsInline = true;
        v.preload = "auto";
    }
    const divider = el("div", "jvc-divider");
    const badge1 = el("div", "jvc-badge");
    const badge2 = el("div", "jvc-badge");
    const empty = el("div", "jvc-empty", "Run the workflow to preview A vs B.");

    const btnRestart = el("button", "jvc-btn", "⏮");
    const btnStepB = el("button", "jvc-btn", "◂");
    const btnPlay = el("button", "jvc-btn", "▶");
    const btnStepF = el("button", "jvc-btn", "▸");
    const range = el("input", "jvc-range");
    range.type = "range";
    range.min = "0";
    range.max = "1000";
    range.step = "1";
    range.value = "0";
    const timeEl = el("span", "jvc-time", "00:00.0 / 00:00.0");
    const btnLoop = el("button", "jvc-btn", "⟳");
    const btnMute = el("button", "jvc-btn", "🔇");
    const btnDir = el("button", "jvc-btn", "⟷");
    const btnSwap = el("button", "jvc-btn", "⇄");
    const selMode = el("select", "jvc-sel");
    for (const [v, label] of [["slider", "Wipe"], ["side", "Side by side"], ["diff", "Difference"]]) {
        const o = el("option", null, label);
        o.value = v;
        selMode.appendChild(o);
    }
    btnRestart.title = "Back to start";
    btnStepB.title = "Previous frame";
    btnPlay.title = "Play / pause";
    btnStepF.title = "Next frame";
    btnLoop.title = "Loop";
    btnMute.title = "Audio (from A)";
    btnDir.title = "Wipe direction";
    btnSwap.title = "Swap sides";

    const controls = el("div", "jvc-controls");
    controls.append(btnRestart, btnStepB, btnPlay, btnStepF, timeEl, el("span", "jvc-spacer"),
        btnLoop, btnMute, btnDir, btnSwap, selMode);
    media.append(va, vb, divider, badge1, badge2, empty);
    root.append(media, range, controls);

    // Keep pointer/wheel events inside the widget so the canvas doesn't drag the node.
    for (const evn of ["pointerdown", "mousedown", "wheel", "dblclick"]) {
        root.addEventListener(evn, (e) => e.stopPropagation());
    }

    const widget = node.addDOMWidget("compare_preview", "video_compare", root, {
        serialize: false,
        hideOnZoom: false,
        getMinHeight: () => 180 + CONTROLS_H,
    });
    widget.serialize = false;

    // --------------------------------------------------------------- timing
    const offset = () => Number(prefs.src?.b_offset ?? 0);
    const fps = () => {
        const f = Number(prefs.src?.fps);
        return Number.isFinite(f) && f > 0 ? f : 24;
    };
    const bTimeFor = (tA) => tA + offset();

    function syncB() {
        if (!Number.isFinite(vb.duration)) return Promise.resolve();
        return seek(vb, bTimeFor(va.currentTime));
    }

    async function seekBoth(tA) {
        await Promise.all([seek(va, tA), seek(vb, bTimeFor(tA))]);
        updateProgress();
    }

    async function play() {
        if (!ready) return;
        if (va.ended || va.currentTime >= va.duration - 0.01) await seekBoth(0);
        else await syncB();
        va.muted = prefs.muted;
        try {
            await va.play();
        } catch {
            // Unmuted autoplay can be refused; fall back to muted playback.
            va.muted = true;
            try { await va.play(); } catch { return; }
        }
        playing = true;
        playB();
        renderButtons();
    }

    function playB() {
        const tB = bTimeFor(va.currentTime);
        if (tB >= 0 && tB < vb.duration) vb.play().catch(() => {});
    }

    function pause() {
        playing = false;
        va.pause();
        vb.pause();
        renderButtons();
    }

    const togglePlay = () => (playing ? pause() : play());

    async function step(frames) {
        if (!ready) return;
        pause();
        const dur = Number.isFinite(va.duration) ? va.duration : 0;
        const t = Math.min(Math.max(va.currentTime + frames / fps(), 0), dur);
        await seekBoth(t);
    }

    function updateProgress() {
        const d = Number.isFinite(va.duration) ? va.duration : 0;
        if (!scrubbing) range.value = String(d ? Math.round((va.currentTime / d) * 1000) : 0);
        timeEl.textContent = `${fmt(scrubbing ? (Number(range.value) / 1000) * d : va.currentTime)} / ${fmt(d)}`;
    }

    // Keep B locked to A during playback.
    function tick() {
        if (ready) {
            if (!scrubbing) updateProgress();
            if (playing && !va.paused) {
                const tB = bTimeFor(va.currentTime);
                if (tB < 0 || tB >= vb.duration) {
                    if (!vb.paused) vb.pause();
                    if (tB < 0 && vb.currentTime !== 0) vb.currentTime = 0;
                } else {
                    if (Math.abs(vb.currentTime - tB) > DRIFT_LIMIT) vb.currentTime = tB;
                    if (vb.paused) vb.play().catch(() => {});
                }
            }
        }
        if (alive) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);

    va.addEventListener("ended", async () => {
        if (!playing) return;
        if (prefs.loop) {
            await seekBoth(0);
            va.play().catch(() => {});
            playB();
        } else {
            pause();
        }
    });
    // External pauses (e.g. the browser suspending the tab) keep the button honest.
    va.addEventListener("pause", () => {
        if (playing && !va.ended && !va.seeking) { playing = false; vb.pause(); renderButtons(); }
    });

    // ------------------------------------------------------------ rendering
    // "left" is the video shown left/top; "right" is the one clipped in on the right/bottom.
    const leftVid = () => (prefs.swapped ? vb : va);
    const rightVid = () => (prefs.swapped ? va : vb);

    function placeBadge(b, css) {
        b.style.left = b.style.right = b.style.top = b.style.bottom = "auto";
        Object.assign(b.style, css);
    }

    function render() {
        const mode = prefs.mode;
        const L = leftVid();
        const R = rightVid();
        for (const v of [va, vb]) {
            v.style.clipPath = "";
            v.style.mixBlendMode = "";
            v.style.left = v.style.top = "0";
            v.style.width = v.style.height = "100%";
            v.style.zIndex = "1";
        }
        R.style.zIndex = "2";

        media.classList.toggle("jvc-wipe", mode === "slider");
        media.classList.toggle("jvc-vert", prefs.vertical);
        divider.style.display = mode === "slider" ? "block" : "none";
        btnDir.style.display = mode === "slider" || mode === "side" ? "" : "none";
        btnDir.textContent = prefs.vertical ? "⇕" : "⟷";

        badge1.textContent = prefs.swapped ? "B" : "A";
        badge2.textContent = prefs.swapped ? "A" : "B";
        badge1.style.display = badge2.style.display = mode === "diff" ? "none" : "block";
        placeBadge(badge1, { left: "6px", top: "6px" });
        placeBadge(badge2, prefs.vertical ? { left: "6px", bottom: "6px" } : { right: "6px", top: "6px" });

        if (mode === "diff") {
            R.style.mixBlendMode = "difference";
        } else if (mode === "side") {
            if (prefs.vertical) {
                L.style.height = R.style.height = "50%";
                R.style.top = "50%";
            } else {
                L.style.width = R.style.width = "50%";
                R.style.left = "50%";
            }
        } else {
            updateClip();
        }

        renderButtons();
    }

    function updateClip() {
        if (prefs.mode !== "slider") return;
        const p = (prefs.divider * 100).toFixed(2);
        const R = rightVid();
        if (prefs.vertical) {
            R.style.clipPath = `inset(${p}% 0 0 0)`;
            Object.assign(divider.style, { left: "0", right: "0", top: `${p}%`, bottom: "auto",
                width: "auto", height: "2px", transform: "translateY(-1px)" });
        } else {
            R.style.clipPath = `inset(0 0 0 ${p}%)`;
            Object.assign(divider.style, { top: "0", bottom: "0", left: `${p}%`, right: "auto",
                width: "2px", height: "auto", transform: "translateX(-1px)" });
        }
    }

    function renderButtons() {
        btnPlay.textContent = playing ? "❚❚" : "▶";
        btnLoop.classList.toggle("jvc-on", prefs.loop);
        btnMute.classList.toggle("jvc-on", !prefs.muted);
        btnMute.textContent = prefs.muted ? "🔇" : "🔊";
        btnSwap.classList.toggle("jvc-on", prefs.swapped);
        selMode.value = prefs.mode;
    }

    // Grow the node once per new video shape so the preview isn't letterboxed into a sliver.
    function fitNode() {
        const s = prefs.src;
        if (!s?.width || !s?.height) return;
        const side = prefs.mode === "side";
        let aspect = s.width / s.height;
        if (side) aspect = prefs.vertical ? aspect / 2 : aspect * 2;
        const key = `${s.width}x${s.height}:${prefs.mode}:${prefs.vertical}`;
        if (sizedFor === key) return;
        sizedFor = key;
        requestAnimationFrame(() => {
            const w = media.clientWidth;
            const h = media.clientHeight;
            if (!w || !h) { sizedFor = null; return; }
            const want = Math.min(Math.round(w / aspect), 900);
            const delta = want - h;
            if (delta > 4) {
                node.setSize([node.size[0], node.size[1] + delta]);
                node.setDirtyCanvas(true, true);
            }
        });
    }

    // ------------------------------------------------------------ ingestion
    async function load(r) {
        prefs.src = {
            a: r.a,
            b: r.b,
            width: Number(r.width) || 0,
            height: Number(r.height) || 0,
            b_offset: Number(r.b_offset ?? 0),
            fps: Number(r.fps ?? 0),
        };
        save();

        const token = ++loadToken;
        ready = false;
        pause();
        empty.style.display = "none";
        va.src = viewUrl(r.a);
        vb.src = viewUrl(r.b);
        fitNode();

        const [okA, okB] = await Promise.all([whenReady(va), whenReady(vb)]);
        if (token !== loadToken) return;
        if (!okA || !okB) {
            empty.textContent = "Preview files are gone. Run the workflow again.";
            empty.style.display = "grid";
            return;
        }
        await seekBoth(0);
        if (token !== loadToken) return;
        ready = true;
        updateProgress();
        play();
    }

    // ---------------------------------------------------------- interaction
    function dragTo(e) {
        const r = media.getBoundingClientRect();
        const t = prefs.vertical
            ? (e.clientY - r.top) / Math.max(1, r.height)
            : (e.clientX - r.left) / Math.max(1, r.width);
        prefs.divider = Math.min(1, Math.max(0, t));
        updateClip();
    }

    media.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        if (prefs.mode !== "slider") { togglePlay(); return; }
        dragging = true;
        media.setPointerCapture(e.pointerId);
        dragTo(e);
    });
    media.addEventListener("pointermove", (e) => { if (dragging) dragTo(e); });
    const endDrag = () => { if (dragging) { dragging = false; save(); } };
    media.addEventListener("pointerup", endDrag);
    media.addEventListener("pointercancel", endDrag);
    media.addEventListener("dblclick", () => {
        if (prefs.mode === "slider") { prefs.divider = 0.5; updateClip(); save(); }
    });

    btnPlay.addEventListener("click", togglePlay);
    btnStepF.addEventListener("click", () => step(1));
    btnStepB.addEventListener("click", () => step(-1));
    btnRestart.addEventListener("click", () => { if (ready) { pause(); seekBoth(0); } });

    let resumeAfterScrub = false;
    let lastLiveSeek = 0;
    range.addEventListener("pointerdown", () => {
        if (!ready) return;
        scrubbing = true;
        resumeAfterScrub = playing;
        pause();
    });
    range.addEventListener("input", () => {
        if (!ready) return;
        if (!scrubbing) { scrubbing = true; resumeAfterScrub = playing; pause(); } // keyboard
        const t = (Number(range.value) / 1000) * va.duration;
        updateProgress();
        const now = performance.now();
        if (now - lastLiveSeek > 60) {
            lastLiveSeek = now;
            va.currentTime = t;
            vb.currentTime = Math.min(Math.max(bTimeFor(t), 0), vb.duration || 0);
        }
    });
    async function endScrub() {
        if (!scrubbing) return;
        const t = (Number(range.value) / 1000) * va.duration;
        await seekBoth(t);
        scrubbing = false;
        updateProgress();
        if (resumeAfterScrub) play();
        resumeAfterScrub = false;
    }
    range.addEventListener("change", endScrub);
    // A press that never moves the thumb fires no "change"; release still ends the scrub.
    window.addEventListener("pointerup", () => { if (scrubbing) setTimeout(endScrub, 0); }, { signal: lifetime.signal });
    window.addEventListener("pointercancel", () => { if (scrubbing) setTimeout(endScrub, 0); }, { signal: lifetime.signal });

    btnLoop.addEventListener("click", () => { prefs.loop = !prefs.loop; renderButtons(); save(); });
    btnMute.addEventListener("click", () => {
        prefs.muted = !prefs.muted;
        va.muted = prefs.muted;
        renderButtons();
        save();
    });
    btnDir.addEventListener("click", () => {
        prefs.vertical = !prefs.vertical;
        render();
        fitNode();
        save();
    });
    btnSwap.addEventListener("click", () => {
        prefs.swapped = !prefs.swapped;
        render();
        save();
    });
    selMode.addEventListener("change", () => {
        prefs.mode = selMode.value;
        render();
        fitNode();
        save();
    });

    // ------------------------------------------------------------ lifecycle
    const origExecuted = node.onExecuted;
    node.onExecuted = function (message) {
        origExecuted?.apply(this, arguments);
        const comps = message?.comparisons;
        if (Array.isArray(comps) && comps.length) load(comps[comps.length - 1]);
    };

    // nodeCreated runs before a saved workflow's properties are applied, so restore here.
    const origConfigure = node.onConfigure;
    node.onConfigure = function (info) {
        origConfigure?.apply(this, arguments);
        const saved = info?.properties?.[STATE_KEY];
        if (saved && typeof saved === "object") {
            for (const k of Object.keys(prefs)) if (k in saved) prefs[k] = saved[k];
            sizedFor = prefs.src ? `${prefs.src.width}x${prefs.src.height}:${prefs.mode}:${prefs.vertical}` : null;
            render();
            if (prefs.src?.a && prefs.src?.b) load(prefs.src);
        }
    };

    const origRemoved = node.onRemoved;
    node.onRemoved = function () {
        loadToken++;
        alive = false;
        lifetime.abort();
        for (const v of [va, vb]) { v.pause(); v.removeAttribute("src"); v.load(); }
        origRemoved?.apply(this, arguments);
    };

    if (node.size[0] < 460) node.setSize([460, Math.max(node.size[1], 360)]);
    render();
    save();
    return true;
}
