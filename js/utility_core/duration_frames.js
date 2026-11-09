import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, findWidget, h, injectCss, onWidget } from "./_shared.js";

// Duration to Frames: lockable expression, preset sync and a live preview computed server-side
// (the server's evaluator is the single source of truth for Python rounding semantics).

const UI_KEY = "jezzwtf_duration_frames";
const CUSTOM = "Custom";
const SAMPLES = [2, 3, 4, 5, 6, 8, 10, 12, 15];
let presetsCache = null;

async function presets() {
    if (!presetsCache) {
        presetsCache = api.fetchApi("/jezzwtf/duration_frames/presets").then((r) => r.json()).catch((e) => {
            presetsCache = null;
            throw e;
        });
    }
    return presetsCache;
}

injectCss("jwtf-duration", `
.jwtf-df { gap: 4px; }
.jwtf-df-big { font: 700 34px/1 ui-monospace, Consolas, monospace; color: #fff; }
.jwtf-df-big small { font-size: 12px; color: #8b8f99; font-weight: 500; margin-left: 4px; }
.jwtf-df-err { display: none; color: #fda4af; background: #3b1219; border: 1px solid #7f1d2d; border-radius: 6px; padding: 3px 6px;
  font-size: 11px; white-space: pre-wrap; }
.jwtf-df-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(62px, 1fr)); gap: 3px; }
.jwtf-df-cell { background: #121317; border: 1px solid #2a2c33; border-radius: 5px; padding: 2px 4px; font: 11px ui-monospace, monospace; }
.jwtf-df-cell b { color: #e6e6e6; }
.jwtf-df-cell.bad { color: #f43f5e; }
`);

function setup(node) {
    const durW = findWidget(node, "duration");
    const presetW = findWidget(node, "preset");
    const exprW = findWidget(node, "expression");
    const fpsW = findWidget(node, "fps");
    node.properties = node.properties ?? {};
    const isLocked = () => node.properties.jwtf_locked !== false;

    const lockW = node.addWidget("button", "lock", null, () => {
        node.properties.jwtf_locked = !isLocked();
        applyLock();
    }, { serialize: false });
    // Move the lock button directly below the expression widget. `options.serialize` keeps it out
    // of the prompt; `widget.serialize` stays unset so the workflow's widgets_values keep a
    // placeholder for it (LiteGraph writes values by index but reads them sequentially).
    node.widgets.splice(node.widgets.indexOf(lockW), 1);
    node.widgets.splice(node.widgets.indexOf(exprW) + 1, 0, lockW);

    const big = h("div.jwtf-df-big", {}, "—");
    const line = h("div.jwtf-muted");
    const err = h("div.jwtf-df-err");
    const note = h("div.jwtf-muted", { style: { fontSize: "11px" } });
    const grid = h("div.jwtf-df-grid");
    const root = h("div.jwtf-card.jwtf-df", {}, big, line, err, note, grid);
    node.addDOMWidget("jwtf_duration_preview", "jwtf_duration_preview", root, { serialize: false, getMinHeight: () => 160 });

    function applyLock() {
        const locked = isLocked();
        lockW.name = locked ? "\u{1F512} expression locked" : "\u{1F513} expression editable";
        lockW.label = lockW.name;
        const ta = exprW?.element ?? exprW?.inputEl;
        if (ta) {
            ta.readOnly = locked;
            ta.style.opacity = locked ? "0.55" : "";
            ta.style.cursor = locked ? "not-allowed" : "";
        }
        if (fpsW) fpsW.disabled = locked || presetW?.value !== CUSTOM;
        node.setDirtyCanvas(true, true);
    }

    async function onPreset(value) {
        if (value === CUSTOM) {
            node.properties.jwtf_locked = false;
        } else {
            try {
                const p = (await presets())[value];
                if (p) {
                    exprW.value = p.expression;
                    fpsW.value = p.fps;
                }
            } catch { /* backend unreachable; refresh() reports it */ }
        }
        applyLock();
        refresh();
    }

    const ta = exprW?.element ?? exprW?.inputEl;
    ta?.addEventListener("input", async () => {
        if (isLocked() || presetW?.value === CUSTOM) return;
        try {
            const p = (await presets())[presetW.value];
            if (p && ta.value !== p.expression) {
                presetW.value = CUSTOM;
                applyLock();
            }
        } catch { /* ignore */ }
        refresh();
    });

    let seq = 0;
    let timer = 0;
    let lastRun = null;
    function refresh() {
        clearTimeout(timer);
        timer = setTimeout(run, 120);
    }
    async function run() {
        const my = ++seq;
        const linked = node.inputs?.some((i) => i.name === "duration" && i.link != null);
        let current = Number(durW?.value ?? 0);
        note.textContent = "";
        if (linked) {
            if (lastRun) {
                current = Number(lastRun.duration);
                note.textContent = "duration is linked; showing the last run";
            } else {
                current = null;
                note.textContent = "duration is linked; run the graph to see the result";
            }
        }
        const values = [...(current == null ? [] : [current]), ...SAMPLES.filter((s) => s !== current)];
        let data;
        try {
            const r = await api.fetchApi("/jezzwtf/duration_frames/eval", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ preset: presetW?.value, expression: exprW?.value, fps: fpsW?.value, values }),
            });
            data = await r.json();
        } catch {
            if (my !== seq) return;
            big.textContent = "—";
            line.textContent = "backend unreachable";
            err.style.display = "none";
            return;
        }
        if (my !== seq) return;
        const rows = data.rows ?? [];
        const head = current == null ? null : rows.shift();
        if (head == null) {
            big.textContent = "…";
            line.textContent = "";
            err.style.display = "none";
        } else if (head.error) {
            big.textContent = "—";
            line.textContent = "";
            err.textContent = head.error;
            err.style.display = "block";
        } else {
            err.style.display = "none";
            big.replaceChildren(String(head.frames), h("small", {}, "frames"));
            line.textContent = `${current} s @ ${data.fps} fps → ${head.seconds.toFixed(3)} s actual`;
        }
        grid.replaceChildren(...rows.map((r) => r.error
            ? h("div.jwtf-df-cell.bad", { title: r.error }, `${r.a}s ×`)
            : h("div.jwtf-df-cell", {}, `${r.a}s `, h("b", {}, String(r.frames)))));
    }

    onWidget(presetW, onPreset);
    onWidget(durW, refresh);
    onWidget(fpsW, refresh);
    onWidget(exprW, refresh);

    node._jwtfDf = {
        refresh,
        applyLock,
        executed(info) { lastRun = info; refresh(); },
        async configure() {
            if (presetW?.value !== CUSTOM) {
                try {
                    const p = (await presets())[presetW.value];
                    if (p) { exprW.value = p.expression; fpsW.value = p.fps; }
                } catch { /* ignore */ }
            }
            applyLock();
            refresh();
        },
    };
    applyLock();
    refresh();
    node.setSize([Math.max(node.size[0], 400), node.computeSize()[1]]);
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.DurationFrames",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "JWTFDurationFrames") return;
        chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
        chain(nodeType.prototype, "onConfigure", function () { this._jwtfDf?.configure(); });
        chain(nodeType.prototype, "onConnectionsChange", function () { this._jwtfDf?.refresh(); });
        chain(nodeType.prototype, "onExecuted", function (msg) {
            const info = msg?.[UI_KEY]?.[0];
            if (info) this._jwtfDf?.executed(info);
        });
        chain(nodeType.prototype, "onResize", function (size) {
            if (size[0] < 400) size[0] = 400;
        });
    },
});
