import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, findWidget, h, injectCss, onWidget, viewUrl } from "./_shared.js";

// Folder Image / Video Batch: scan card, run whole folder by auto-chaining prompts, stop/resume.

const TYPES = { JWTFFolderImageBatch: "image", JWTFFolderVideoBatch: "video" };
const loaders = new Set();
let currentPrompt = null;

injectCss("jwtf-folder", `
.jwtf-fb { gap: 5px; }
.jwtf-fb-thumb { position: relative; height: 150px; border-radius: 8px; overflow: hidden; background: #0d0e11; flex: none; }
.jwtf-fb-bg { position: absolute; inset: -20px; background: center/cover no-repeat; filter: blur(16px) brightness(.45); }
.jwtf-fb-img { position: absolute; inset: 0; background: center/contain no-repeat; }
.jwtf-fb-chip { position: absolute; top: 6px; font: 700 10px system-ui; padding: 2px 7px; border-radius: 10px;
  background: rgba(0,0,0,.6); border: 1px solid rgba(255,255,255,.18); color: #e6e8ee; }
.jwtf-fb-chip.kind { left: 6px; text-transform: uppercase; }
.jwtf-fb-chip.pos { right: 6px; transition: transform .2s; }
.jwtf-fb-chip.pos.pop { transform: scale(1.25); }
.jwtf-fb-cap { position: absolute; left: 0; right: 0; bottom: 0; padding: 14px 8px 5px; font: 11px ui-monospace, monospace;
  color: #e6e8ee; background: linear-gradient(transparent, rgba(0,0,0,.75)); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.jwtf-fb-bar { height: 8px; border-radius: 4px; background: #24262d; overflow: hidden; }
.jwtf-fb-bar > div { height: 100%; width: 0; background: linear-gradient(90deg, #4ade80, #22d3ee); transition: width .3s; }
.jwtf-fb-sub { height: 3px; border-radius: 2px; background: #1d1f24; overflow: hidden; }
.jwtf-fb-sub > div { height: 100%; width: 0; background: #818cf8; transition: width .2s; }
.jwtf-fb-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; font-size: 11px; }
.jwtf-fb-stats b { display: block; font: 600 12px ui-monospace, monospace; color: #e6e8ee; }
.jwtf-fb-map { width: 100%; height: 22px; display: block; }
.jwtf-fb-status { font-size: 11px; min-height: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.jwtf-fb-status.ok { color: #4ade80; } .jwtf-fb-status.warn { color: #f59e0b; } .jwtf-fb-status.err { color: #f43f5e; }
.jwtf-fb-status.info { color: #8b8f99; }
`);

const fmtTime = (s) => {
    s = Math.max(0, Math.round(s));
    const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
    return hh ? `${hh}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}` : `${mm}:${String(ss).padStart(2, "0")}`;
};

async function postJson(path, body) {
    return api.fetchApi(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
}

async function queueIsEmpty() {
    try {
        const q = await (await api.fetchApi("/queue")).json();
        return !(q.queue_running?.length || q.queue_pending?.length);
    } catch {
        return false;
    }
}

function setup(node, kind) {
    const W = {
        folder: findWidget(node, "folder_path"), sort: findWidget(node, "sort_mode"),
        index: findWidget(node, "index"), auto: findWidget(node, "auto_run_folder"),
    };
    const ui = {};
    ui.bg = h("div.jwtf-fb-bg");
    ui.img = h("div.jwtf-fb-img");
    ui.pos = h("span.jwtf-fb-chip.pos", {}, "0 / 0");
    ui.cap = h("div.jwtf-fb-cap", {}, "No folder scanned");
    ui.bar = h("div");
    ui.pct = h("span.jwtf-muted");
    ui.count = h("span.jwtf-muted");
    ui.sub = h("div");
    ui.rate = h("b", {}, "--");
    ui.eta = h("b", {}, "--");
    ui.elapsed = h("b", {}, "0:00");
    ui.map = h("canvas.jwtf-fb-map");
    ui.status = h("div.jwtf-fb-status.info");
    ui.run = h("button.jwtf-btn", { onclick: () => startRun() });
    ui.stop = h("button.jwtf-btn", { textContent: "Stop", disabled: true, onclick: () => stopRun() });
    const stepBtn = (d, label) => h("button.jwtf-btn", { textContent: label, onclick: () => stepIndex(d) });
    const root = h("div.jwtf-card.jwtf-fb", {},
        (ui.thumb = h("div.jwtf-fb-thumb", {}, ui.bg, ui.img, h("span.jwtf-fb-chip.kind", {}, kind), ui.pos, ui.cap)),
        h("div.jwtf-row", {}, h("div.jwtf-fb-bar.jwtf-grow", {}, ui.bar), ui.pct, ui.count),
        h("div.jwtf-fb-sub", {}, ui.sub),
        h("div.jwtf-fb-stats", {}, h("div.jwtf-muted", {}, "items/min", ui.rate), h("div.jwtf-muted", {}, "ETA", ui.eta),
            h("div.jwtf-muted", {}, "elapsed", ui.elapsed)),
        ui.map,
        h("div.jwtf-row", {}, ui.run, ui.stop, stepBtn(-1, "◀ Prev"), stepBtn(1, "Next ▶"),
            h("button.jwtf-btn", { textContent: "Rescan", onclick: () => scan() })),
        ui.status);

    const st = { total: 0, run: null, scanToken: 0, scanTimer: 0, tick: 0 };

    const setStatus = (text, tone = "info") => { ui.status.textContent = text; ui.status.className = `jwtf-fb-status ${tone}`; };
    const autoOn = () => !!W.auto?.value;
    const setIndex = (v) => { if (W.index) { W.index.value = v; node.setDirtyCanvas(true, false); } };

    function setPreview(pv, name, idx, total) {
        if (pv?.filename) {
            const url = `url("${viewUrl(api, pv)}")`;
            ui.img.style.backgroundImage = url;
            ui.bg.style.backgroundImage = url;
        }
        if (name != null) ui.cap.textContent = name;
        const txt = `${total ? idx + 1 : 0} / ${total}`;
        if (ui.pos.textContent !== txt) {
            ui.pos.textContent = txt;
            ui.pos.classList.add("pop");
            setTimeout(() => ui.pos.classList.remove("pop"), 200);
        }
    }

    function renderRunLabel() {
        ui.run.textContent = autoOn() ? "▶ Run folder" : "▶ Run single";
        const running = !!st.run && st.run.state === "running";
        ui.run.disabled = running;
        ui.stop.disabled = !running;
    }

    function confetti() {
        const box = ui.thumb;
        const c = h("canvas", { style: { position: "absolute", inset: "0", width: "100%", height: "100%", pointerEvents: "none" } });
        box.append(c);
        c.width = box.clientWidth || 300;
        c.height = box.clientHeight || 150;
        const ctx = c.getContext("2d");
        const colors = ["#4ade80", "#22d3ee", "#818cf8", "#f472b6", "#fbbf24"];
        const bits = Array.from({ length: 40 }, () => ({
            x: c.width / 2, y: c.height * 0.8, vx: (Math.random() - 0.5) * 7, vy: -Math.random() * 7 - 2,
            r: 2 + Math.random() * 3, color: colors[Math.floor(Math.random() * colors.length)],
        }));
        const t0 = performance.now();
        const step = (t) => {
            const age = t - t0;
            ctx.clearRect(0, 0, c.width, c.height);
            for (const b of bits) {
                b.x += b.vx; b.y += b.vy; b.vy += 0.22;
                ctx.globalAlpha = Math.max(0, 1 - age / 1400);
                ctx.fillStyle = b.color;
                ctx.fillRect(b.x, b.y, b.r, b.r);
            }
            if (age < 1400 && c.isConnected) requestAnimationFrame(step);
            else c.remove();
        };
        requestAnimationFrame(step);
    }

    // ---- scanning --------------------------------------------------------------
    function scheduleScan(ms = 350) {
        if (st.run?.state === "running") return;
        clearTimeout(st.scanTimer);
        st.scanTimer = setTimeout(scan, ms);
    }

    async function scan() {
        const token = ++st.scanToken;
        renderRunLabel();
        const folder = String(W.folder?.value ?? "").trim();
        if (!folder) {
            setStatus("Set a folder path to begin.", "info");
            return;
        }
        const q = new URLSearchParams({ folder, sort: String(W.sort?.value ?? ""), kind, index: String(W.index?.value ?? 0) });
        let res;
        try {
            res = await (await api.fetchApi(`/jezzwtf/folder_batch/scan?${q}`)).json();
        } catch {
            if (token === st.scanToken) setStatus("Scan failed: backend unreachable.", "err");
            return;
        }
        if (token !== st.scanToken) return;
        if (!res.ok) {
            st.total = 0;
            setPreview(null, "No files", 0, 0);
            setStatus(res.error, "err");
            drawMap();
            return;
        }
        st.total = res.total;
        setPreview(res.preview, res.name, res.index, res.total);
        const reqIdx = res.requested_index;
        if (autoOn() && reqIdx >= res.total) {
            setStatus(`Index ${reqIdx} is past the end (${res.total} files); set index to 0.`, "warn");
        } else {
            setStatus(`${res.total} ${kind === "video" ? "videos" : "images"} · ${res.first} … ${res.last}`, "info");
        }
        updateProgress();
    }

    function stepIndex(d) {
        const max = Math.max(0, st.total - 1);
        setIndex(Math.max(0, Math.min(max, Number(W.index?.value ?? 0) + d)));
        scheduleScan(50);
    }

    // ---- run bookkeeping ------------------------------------------------------------
    function newRun(startIndex) {
        st.run = {
            state: "running", startIndex, expected: autoOn() ? Math.max(1, st.total - startIndex) : 1,
            tracked: new Map(), pending: new Set(), dead: new Set(), ended: new Set(), queuedNext: new Set(),
            done: new Set(), errors: new Set(), chainEnded: false, stopping: false, startedAt: performance.now(),
            lastItemAt: performance.now(), ema: 0, started: false, sub: 0, current: startIndex,
        };
        clearInterval(st.tick);
        st.tick = setInterval(updateProgress, 500);
        renderRunLabel();
        return st.run;
    }

    async function startRun() {
        if (st.run?.state === "running") return;
        await scan();
        if (!st.total) return;
        const requested = Number(W.index?.value ?? 0);
        if (autoOn() && requested >= st.total) {
            setStatus(`Index ${requested} is past the end (${st.total} files); set index to 0.`, "err");
            return;
        }
        const start = requested % st.total;
        const run = newRun(start);
        setStatus(autoOn() ? `Running folder from #${start + 1}…` : "Running single item…", "info");
        app.queuePrompt(0, 1);
        setTimeout(async () => {
            if (st.run === run && !run.started && run.state === "running" && (await queueIsEmpty())) finish("stopped", "Nothing started; check the queue for errors.");
        }, 20000);
    }

    async function stopRun() {
        const run = st.run;
        if (!run || run.state !== "running") return;
        run.stopping = true;
        for (const id of [...run.tracked.keys(), ...run.pending]) run.dead.add(id);
        const pending = [...run.pending];
        if (pending.length) postJson("/queue", { delete: pending }).catch(() => {});
        const runningOurs = currentPrompt && run.tracked.has(currentPrompt) && !run.ended.has(currentPrompt);
        if (runningOurs) {
            postJson("/interrupt", {}).catch(() => {});
            setStatus("Stopping…", "warn");
        } else {
            finish("stopped");
        }
    }

    function firstUnfinished(run) {
        for (let i = run.startIndex; i < st.total; i++) if (!run.done.has(i)) return i;
        return run.startIndex;
    }

    function finish(state, message) {
        const run = st.run;
        if (!run || run.state !== "running") return;
        run.state = state;
        clearInterval(st.tick);
        // Done returns to where the run started; stop/error resume at the first unfinished item.
        let next = state === "done" ? run.startIndex : firstUnfinished(run);
        next = Math.max(0, Math.min(next, Math.max(0, st.total - 1)));
        setIndex(next);
        if (state === "done") confetti();
        const n = run.done.size;
        if (state === "done") setStatus(message ?? `Done: ${n} item${n === 1 ? "" : "s"} in ${fmtTime((performance.now() - run.startedAt) / 1000)}.`, "ok");
        else if (state === "error") setStatus(message ?? "Run failed.", "err");
        else setStatus(message ?? `Stopped after ${n} item${n === 1 ? "" : "s"}; Run resumes at #${next + 1}.`, "warn");
        updateProgress();
        renderRunLabel();
        scheduleScan(300);
    }

    function maybeFinish() {
        const run = st.run;
        if (!run || run.state !== "running") return;
        const indexed = [...run.tracked.values()].filter((v) => v != null).length;
        if (run.chainEnded && run.pending.size === 0 && run.done.size >= indexed) finish("done");
    }

    function updateProgress() {
        const run = st.run;
        const done = run ? run.done.size : 0;
        const expected = run ? run.expected : 0;
        const p = expected ? Math.min(1, done / expected) : 0;
        ui.bar.style.width = `${p * 100}%`;
        ui.pct.textContent = `${Math.floor(p * 100)}%`;
        ui.count.textContent = `${done} / ${expected}`;
        ui.sub.style.width = `${(run?.state === "running" ? run.sub : 0) * 100}%`;
        if (run) {
            const el = ((run.state === "running" ? performance.now() : run.endedAt ?? performance.now()) - run.startedAt) / 1000;
            if (run.state !== "running" && !run.endedAt) run.endedAt = performance.now();
            ui.elapsed.textContent = fmtTime(el);
            ui.rate.textContent = el > 0 && done ? (done / (el / 60)).toFixed(1) : "--";
            ui.eta.textContent = run.state === "running" && run.ema ? fmtTime(run.ema * Math.max(0, expected - done)) : "--";
        }
        drawMap();
    }

    function drawMap() {
        const c = ui.map;
        const dpr = window.devicePixelRatio || 1;
        const w = c.clientWidth, hgt = c.clientHeight;
        if (!w || !hgt) return;
        c.width = Math.round(w * dpr);
        c.height = Math.round(hgt * dpr);
        const ctx = c.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, hgt);
        const total = st.total;
        if (!total) return;
        const segs = Math.min(total, Math.max(1, Math.floor(w / 4)));
        const per = Math.ceil(total / segs);
        const n = Math.ceil(total / per);
        const sw = w / n;
        const run = st.run;
        const pulse = 0.55 + 0.45 * Math.sin(performance.now() / 180);
        for (let s = 0; s < n; s++) {
            const lo = s * per, hi = Math.min(total, lo + per);
            let color = "#2a2c33";
            if (run) {
                let allDone = true, anyErr = false, running = false;
                for (let i = lo; i < hi; i++) {
                    if (run.errors.has(i)) anyErr = true;
                    if (!run.done.has(i)) allDone = false;
                    if (run.state === "running" && run.current === i) running = true;
                }
                if (anyErr) color = "#f43f5e";
                else if (running) color = `rgba(129,140,248,${pulse})`;
                else if (allDone) color = "#4ade80";
            }
            ctx.fillStyle = color;
            ctx.fillRect(s * sw + 0.5, 8, Math.max(1, sw - 1), hgt - 8);
        }
        const cur = run?.state === "running" ? run.current : Number(W.index?.value ?? 0) % total;
        const x = (Math.floor(cur / per) + 0.5) * sw;
        ctx.fillStyle = "#e6e8ee";
        ctx.beginPath();
        ctx.moveTo(x - 4, 0); ctx.lineTo(x + 4, 0); ctx.lineTo(x, 6);
        ctx.fill();
    }

    // ---- execution hooks ------------------------------------------------------------
    async function onLoaderExecuted(msg) {
        const [idx, total] = msg?.batch_info ?? [0, 0];
        const auto = !!msg?.auto_run?.[0];
        const next = msg?.next_index?.[0] ?? -1;
        st.total = total;
        setPreview(msg?.preview?.[0], msg?.file_name?.[0], idx, total);
        let run = st.run;
        if (!run || run.state !== "running") run = newRun(idx);
        run.started = true;
        run.current = idx;
        if (currentPrompt) {
            run.tracked.set(currentPrompt, idx);
            run.pending.delete(currentPrompt);
        }
        run.sub = 0;
        if (!auto || next < 0) {
            run.chainEnded = true;
        } else if (!run.stopping && !run.queuedNext.has(next)) {
            run.queuedNext.add(next);
            setIndex(next);
            try {
                const p = await app.graphToPrompt();
                const res = await api.queuePrompt(0, p);
                const id = res?.prompt_id;
                if (id) {
                    run.pending.add(id);
                    if (run.stopping) {
                        run.dead.add(id);
                        run.pending.delete(id);
                        postJson("/queue", { delete: [id] }).catch(() => {});
                    }
                }
            } catch (e) {
                console.warn("[jezzwtf] folder batch: queueing next failed", e);
                run.chainEnded = true;
                app.queuePrompt(0, 1); // let ComfyUI surface its own error
            }
        }
        updateProgress();
    }

    function onPromptStart(id) {
        const run = st.run;
        if (!run || run.state !== "running") return;
        if (run.dead.has(id)) {
            postJson("/interrupt", {}).catch(() => {});
            return;
        }
        run.started = true;
        if (!run.tracked.has(id)) run.tracked.set(id, null);
        run.pending.delete(id);
        run.sub = 0;
    }

    function onPromptEnd(id) {
        const run = st.run;
        if (!run || run.state !== "running" || !run.tracked.has(id) || run.ended.has(id)) return;
        run.ended.add(id);
        const idx = run.tracked.get(id);
        if (idx == null) {
            run.chainEnded = true; // our loader was cached for this prompt
        } else {
            run.done.add(idx);
            const t = performance.now();
            const dur = (t - run.lastItemAt) / 1000;
            run.lastItemAt = t;
            run.ema = run.ema ? run.ema * 0.7 + dur * 0.3 : dur;
        }
        updateProgress();
        maybeFinish();
    }

    function onPromptError(d) {
        const run = st.run;
        if (!run || run.state !== "running" || !run.tracked.has(d?.prompt_id)) return;
        const idx = run.tracked.get(d.prompt_id);
        if (idx != null) run.errors.add(idx);
        const first = String(d?.exception_message ?? "").split("\n")[0];
        finish("error", `Error in ${d?.node_type ?? "node"}: ${first}`);
    }

    function onProgress(d) {
        const run = st.run;
        if (!run || run.state !== "running" || (d?.prompt_id && !run.tracked.has(d.prompt_id))) return;
        if (d?.max) run.sub = Math.max(run.sub, d.value / d.max);
        ui.sub.style.width = `${run.sub * 100}%`;
    }

    let idle = 0;
    function onQueueStatus(remaining) {
        clearTimeout(idle);
        if (remaining !== 0 || st.run?.state !== "running") return;
        idle = setTimeout(() => {
            const run = st.run;
            if (!run || run.state !== "running") return;
            if (run.chainEnded && run.pending.size === 0) finish("done");
            else if (run.started) finish("stopped");
        }, 1500);
    }

    for (const w of Object.values(W)) onWidget(w, () => { renderRunLabel(); scheduleScan(); });
    node.addDOMWidget("jwtf_folder_card", "jwtf_folder_card", root, { serialize: false, getMinHeight: () => 352 });
    new ResizeObserver(() => drawMap()).observe(ui.map);
    renderRunLabel();
    updateProgress();
    setTimeout(() => scheduleScan(0), 400);

    node._jwtfFb = {
        onLoaderExecuted, onPromptStart, onPromptEnd, onPromptError, onProgress, onQueueStatus,
        interrupted: () => st.run?.state === "running" && finish("stopped"),
        configure: () => setTimeout(() => scheduleScan(0), 300),
        dispose: () => { clearInterval(st.tick); clearTimeout(st.scanTimer); clearTimeout(idle); },
    };
    node.setSize([Math.max(node.size[0], 360), node.computeSize()[1]]);
}

const each = (fn) => { for (const n of loaders) if (n._jwtfFb) fn(n._jwtfFb); };

app.registerExtension({
    name: "JezzWTF.UtilityCore.FolderBatch",
    setup() {
        api.addEventListener("execution_start", (e) => {
            currentPrompt = e.detail?.prompt_id ?? null;
            if (currentPrompt) each((f) => f.onPromptStart(currentPrompt));
        });
        api.addEventListener("execution_success", (e) => each((f) => f.onPromptEnd(e.detail?.prompt_id ?? currentPrompt)));
        api.addEventListener("executing", (e) => {
            const d = e.detail;
            const nodeId = d && typeof d === "object" ? d.node : d;
            if (nodeId == null) each((f) => f.onPromptEnd((d && d.prompt_id) ?? currentPrompt));
        });
        api.addEventListener("execution_error", (e) => each((f) => f.onPromptError(e.detail)));
        api.addEventListener("execution_interrupted", () => each((f) => f.interrupted()));
        api.addEventListener("progress", (e) => each((f) => f.onProgress(e.detail)));
        api.addEventListener("status", (e) => {
            const info = e.detail?.exec_info ?? e.detail?.status?.exec_info;
            if (info?.queue_remaining != null) each((f) => f.onQueueStatus(info.queue_remaining));
        });
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        const kind = TYPES[nodeData.name];
        if (!kind) return;
        chain(nodeType.prototype, "onNodeCreated", function () {
            loaders.add(this);
            setup(this, kind);
        });
        chain(nodeType.prototype, "onConfigure", function () { this._jwtfFb?.configure(); });
        chain(nodeType.prototype, "onExecuted", function (msg) { this._jwtfFb?.onLoaderExecuted(msg); });
        chain(nodeType.prototype, "onRemoved", function () {
            loaders.delete(this);
            this._jwtfFb?.dispose();
        });
    },
});
