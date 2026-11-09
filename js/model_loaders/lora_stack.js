// LoRA stack editor for JWTFLoraStack, JWTFLoraFolderStack and JWTFLoraFolderStackMulti.
// The hidden `lora_data` widget is the source of truth: {"loras": [{on, name, model, clip, split}]}.
import { app } from "../../../scripts/app.js";
import {
    chain, clamp, findWidget, fitNode, getJson, h, hideWidget, injectCss, loadJson, onWidget, round2, saveJson,
} from "./_shared.js";

const NODES = ["JWTFLoraStack", "JWTFLoraFolderStack", "JWTFLoraFolderStackMulti"];
const FAV_KEY = "jezzwtf_lora_favorites";
const MODE_PROP = "Show Strengths";
const SINGLE = "Single Strength";
const SEPARATE = "Separate Model & Clip";
const LIMIT = 10;
const VIS = 2; // visual range of a stepper: -2 .. +2

injectCss("jwtf-ml-lora", `
.jwtf-ls-head { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #8b8f99; }
.jwtf-ls-cols { display: flex; gap: 4px; margin-left: auto; }
.jwtf-ls-cols span { width: 92px; text-align: center; }
.jwtf-ls-list { display: flex; flex-direction: column; gap: 3px; }
.jwtf-ls-row { position: relative; display: flex; align-items: center; gap: 6px; padding: 3px 4px; border-radius: 6px;
  background: #23252c; border: 1px solid transparent; }
.jwtf-ls-row:hover { border-color: #3a3d46; }
.jwtf-ls-row.off { opacity: .55; }
.jwtf-ls-row.off .jwtf-ls-name b { text-decoration: line-through; }
.jwtf-ls-row.drop-before::before, .jwtf-ls-row.drop-after::after { content: ""; position: absolute; left: 0; right: 0;
  height: 2px; background: #5672b4; }
.jwtf-ls-row.drop-before::before { top: -3px; } .jwtf-ls-row.drop-after::after { bottom: -3px; }
.jwtf-ls-row.dragging { opacity: .4; }
.jwtf-ls-pill { width: 26px; height: 14px; border-radius: 8px; background: #3a3d46; position: relative; flex: none;
  cursor: pointer; border: 0; padding: 0; }
.jwtf-ls-pill::after { content: ""; position: absolute; top: 2px; left: 2px; width: 10px; height: 10px; border-radius: 50%;
  background: #aaa; transition: left .12s; }
.jwtf-ls-pill.on { background: #4a64a0; } .jwtf-ls-pill.on::after { left: 14px; background: #fff; }
.jwtf-ls-pill.mid { background: #5a5f78; } .jwtf-ls-pill.mid::after { left: 8px; background: #ddd; }
.jwtf-ls-name { flex: 1 1 auto; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; cursor: pointer; }
.jwtf-ls-name i { color: #7d8190; font-style: normal; }
.jwtf-ls-name b { font-weight: 600; }
.jwtf-ls-badge { font-size: 10px; color: #fca5a5; border: 1px solid #7f3a44; border-radius: 8px; padding: 0 5px; flex: none; }
.jwtf-ls-grip, .jwtf-ls-x { visibility: hidden; cursor: grab; color: #7d8190; flex: none; width: 14px; text-align: center; }
.jwtf-ls-x { cursor: pointer; }
.jwtf-ls-x:hover { color: #f43f5e; }
.jwtf-ls-row:hover .jwtf-ls-grip, .jwtf-ls-row:hover .jwtf-ls-x { visibility: visible; }
.jwtf-ls-step { position: relative; display: flex; align-items: center; width: 92px; height: 20px; flex: none;
  background: #121317; border: 1px solid #30333b; border-radius: 5px; overflow: hidden; cursor: ew-resize; }
.jwtf-ls-fill { position: absolute; top: 0; bottom: 0; background: linear-gradient(90deg, #b45309, #f59e0b); opacity: .75; }
.jwtf-ls-fill.neg { background: linear-gradient(90deg, #f43f5e, #9f1239); }
.jwtf-ls-tick { position: absolute; top: 0; bottom: 0; width: 1px; background: #444855; }
.jwtf-ls-val { position: relative; flex: 1; text-align: center; font-variant-numeric: tabular-nums; pointer-events: none; }
.jwtf-ls-val.out { color: #fbbf24; font-weight: 700; }
.jwtf-ls-arr { position: relative; width: 14px; text-align: center; color: #9aa0b0; cursor: pointer; }
.jwtf-ls-arr:hover { color: #fff; }
.jwtf-ls-edit { position: absolute; inset: 0; width: 100%; text-align: center; z-index: 2; border-radius: 0; }
.jwtf-ls-empty { text-align: center; color: #6b6f7b; padding: 10px 0; }
.jwtf-ls-pick { position: fixed; z-index: 10000; width: 340px; max-height: 420px; display: flex; flex-direction: column;
  gap: 6px; padding: 8px; background: #1f2127; border: 1px solid #3a3d46; border-radius: 10px;
  box-shadow: 0 8px 30px rgba(0,0,0,.5); font: 12px system-ui, sans-serif; color: #ddd; }
.jwtf-ls-plist { overflow-y: auto; display: flex; flex-direction: column; min-height: 80px; }
.jwtf-ls-item { display: flex; align-items: center; gap: 6px; padding: 3px 6px; border-radius: 5px; cursor: pointer; }
.jwtf-ls-item:hover, .jwtf-ls-item.hl { background: #2e3140; }
.jwtf-ls-item.in { background: #29344f; }
.jwtf-ls-star { color: #6b6f7b; cursor: pointer; width: 14px; text-align: center; }
.jwtf-ls-star.fav { color: #fbbf24; }
.jwtf-ls-sep { height: 1px; background: #30333b; margin: 3px 0; }
.jwtf-ls-menu { position: fixed; z-index: 10000; min-width: 150px; background: #1f2127; border: 1px solid #3a3d46;
  border-radius: 8px; padding: 4px; font: 12px system-ui, sans-serif; color: #ddd; box-shadow: 0 8px 30px rgba(0,0,0,.5); }
.jwtf-ls-menu div { padding: 4px 10px; border-radius: 5px; cursor: pointer; }
.jwtf-ls-menu div:hover { background: #2e3140; }
`);

const splitName = (name) => {
    const n = String(name).replace(/\\/g, "/");
    const i = n.lastIndexOf("/");
    return i < 0 ? ["", n] : [n.slice(0, i + 1), n.slice(i + 1)];
};
const fmt = (v) => (v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
const finite = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d);

function normalise(item) {
    const name = String(item?.name ?? item?.lora ?? "").trim();
    if (!name || name.toUpperCase() === "NONE") return null;
    let model;
    let clip;
    if (item.strength != null) {
        model = clip = finite(item.strength, 1);
    } else {
        model = finite(item.model, 1);
        clip = finite(item.clip, model);
    }
    return {
        on: item.on == null ? true : !!item.on,
        name,
        model: round2(clamp(model, -LIMIT, LIMIT)),
        clip: round2(clamp(clip, -LIMIT, LIMIT)),
        split: item.split == null ? Math.abs(clip - model) > 1e-6 : !!item.split,
    };
}

function parseStack(raw) {
    let data;
    try { data = JSON.parse(raw || "{}"); } catch { return []; }
    if (data && !Array.isArray(data)) data = data.loras;
    return (Array.isArray(data) ? data : []).map(normalise).filter(Boolean);
}

// ------------------------------------------------------------------ stepper

function makeStepper(getValue, setValue, isOff) {
    const fill = h("div.jwtf-ls-fill");
    const val = h("div.jwtf-ls-val");
    const left = h("div.jwtf-ls-arr", {}, "◀");
    const right = h("div.jwtf-ls-arr", {}, "▶");
    const el = h("div.jwtf-ls-step", {}, fill, h("div.jwtf-ls-tick", { style: { left: "50%" } }),
        h("div.jwtf-ls-tick", { style: { left: `${50 + 50 / VIS}%` } }), left, val, right);

    const render = () => {
        const v = getValue();
        const f = clamp(v, -VIS, VIS) / VIS / 2; // -0.5 .. 0.5 of the width from the centre
        fill.style.left = `${50 + Math.min(0, f) * 100}%`;
        fill.style.width = `${Math.abs(f) * 100}%`;
        fill.classList.toggle("neg", v < 0);
        fill.style.opacity = isOff() ? ".35" : ".75";
        val.textContent = fmt(v);
        val.classList.toggle("out", Math.abs(v) > VIS);
    };
    const step = (dir, shift) => setValue(round2(clamp(getValue() + dir * (shift ? 0.01 : 0.05), -LIMIT, LIMIT)));

    left.addEventListener("click", (e) => { e.stopPropagation(); step(-1, e.shiftKey); });
    right.addEventListener("click", (e) => { e.stopPropagation(); step(1, e.shiftKey); });
    el.addEventListener("wheel", (e) => {
        e.preventDefault();
        e.stopPropagation();
        step(e.deltaY < 0 ? 1 : -1, e.shiftKey);
    }, { passive: false });

    el.addEventListener("pointerdown", (e) => {
        if (e.button !== 0 || e.target === left || e.target === right || e.target.classList.contains("jwtf-ls-edit")) return;
        e.stopPropagation();
        if (e.altKey) { setValue(1); return; }
        const x0 = e.clientX;
        const v0 = getValue();
        let dragging = false;
        el.setPointerCapture(e.pointerId);
        const move = (ev) => {
            const dx = ev.clientX - x0;
            if (!dragging && Math.abs(dx) < 3) return;
            dragging = true;
            setValue(round2(clamp(v0 + dx * (ev.shiftKey ? 0.005 : 0.05), -LIMIT, LIMIT)));
        };
        const up = () => {
            el.removeEventListener("pointermove", move);
            el.removeEventListener("pointerup", up);
            el.removeEventListener("pointercancel", up);
            if (!dragging) edit();
        };
        el.addEventListener("pointermove", move);
        el.addEventListener("pointerup", up);
        el.addEventListener("pointercancel", up);
    });

    function edit() {
        const input = h("input.jwtf-ml-input.jwtf-ls-edit", { value: String(getValue()), type: "text" });
        let done = false;
        const finish = (commit) => {
            if (done) return;
            done = true;
            const n = parseFloat(input.value.replace("−", "-"));
            input.remove();
            if (commit && Number.isFinite(n)) setValue(round2(clamp(n, -LIMIT, LIMIT)));
        };
        input.addEventListener("keydown", (e) => {
            e.stopPropagation();
            if (e.key === "Enter") finish(true);
            else if (e.key === "Escape") finish(false);
        });
        input.addEventListener("blur", () => finish(true));
        el.append(input);
        input.focus();
        input.select();
    }

    return { el, render };
}

// ------------------------------------------------------------------ popups

let openPopup = null;
function closePopup() {
    openPopup?.();
    openPopup = null;
}

function placeNear(el, x, y) {
    document.body.append(el);
    const r = el.getBoundingClientRect();
    el.style.left = `${clamp(x, 4, window.innerWidth - r.width - 4)}px`;
    el.style.top = `${clamp(y, 4, window.innerHeight - r.height - 4)}px`;
}

function contextMenu(x, y, items) {
    closePopup();
    const menu = h("div.jwtf-ls-menu", {}, items.map(([label, fn]) => h("div", {
        onclick: () => { closePopup(); fn(); },
    }, label)));
    placeNear(menu, x, y);
    const away = (e) => { if (!menu.contains(e.target)) closePopup(); };
    setTimeout(() => document.addEventListener("pointerdown", away, true), 0);
    openPopup = () => { menu.remove(); document.removeEventListener("pointerdown", away, true); };
}

// ------------------------------------------------------------------ editor

function setupStack(node) {
    const isFolderNode = node.comfyClass !== "JWTFLoraStack";
    const dataW = findWidget(node, "lora_data");
    const folderW = findWidget(node, "folder");
    hideWidget(dataW);

    let stack = [];
    let files = []; // full relative names for the picker
    let folders = []; // folder chips
    let fileSet = new Set();
    let lastWritten = null;
    let armedClear = 0;
    let panelH = 90;
    const favs = new Set(loadJson(FAV_KEY, []));

    const getMode = () => node.properties?.[MODE_PROP] ?? SINGLE;
    const setMode = (mode) => {
        node.properties = node.properties ?? {};
        node.properties[MODE_PROP] = mode;
        if (mode === SEPARATE) {
            for (const e of stack) if (!Number.isFinite(e.clip)) e.clip = e.model;
        } else {
            for (const e of stack) { e.clip = e.model; e.split = false; }
        }
        commit();
    };
    const separate = () => getMode() === SEPARATE;

    const list = h("div.jwtf-ls-list");
    const countEl = h("span", {}, "");
    const toggleAll = h("button.jwtf-ls-pill", { title: "Toggle all" });
    const modeBtn = h("button.jwtf-ml-btn", { title: "Single / separate model and clip strength" });
    const clearBtn = h("button.jwtf-ml-btn", {}, "Clear");
    const cols = h("div.jwtf-ls-cols");
    const head = h("div.jwtf-ls-head", {}, toggleAll, countEl, modeBtn, clearBtn, cols);

    const addBtn = h("button.jwtf-ml-btn.jwtf-ml-grow", {}, "+ Add LoRA");
    const rollMin = h("input.jwtf-ml-input", { type: "number", value: "0.4", step: "0.05", style: { width: "52px" }, title: "Roll minimum" });
    const rollMax = h("input.jwtf-ml-input", { type: "number", value: "1", step: "0.05", style: { width: "52px" }, title: "Roll maximum" });
    const rollBtn = h("button.jwtf-ml-btn", { title: "Randomise the strength of every enabled LoRA" }, "Roll");
    const foot = h("div.jwtf-ml-row", {}, addBtn, rollMin, rollMax, rollBtn);
    const root = h("div.jwtf-ml", {}, head, list, foot);

    // -------- persistence
    function write() {
        const json = JSON.stringify({
            loras: stack.map((e) => ({
                on: e.on, name: e.name, model: e.model, clip: separate() ? e.clip : e.model,
                split: separate() ? e.split : false,
            })),
        });
        lastWritten = json;
        if (dataW) dataW.value = json;
        node.setDirtyCanvas(true, true);
    }
    function commit() {
        write();
        render();
    }

    function load(raw) {
        stack = parseStack(raw);
        if (node.properties?.[MODE_PROP] == null) {
            node.properties = node.properties ?? {};
            node.properties[MODE_PROP] = stack.some((e) => e.split) ? SEPARATE : SINGLE;
        }
        render();
    }

    // -------- file list
    let refreshToken = 0;
    async function refreshFiles() {
        const token = ++refreshToken; // a newer request supersedes this one
        try {
            if (isFolderNode) {
                const folder = encodeURIComponent(String(folderW?.value ?? ""));
                const [f, fl] = await Promise.all([
                    getJson(`/jezzwtf/lora_folder?folder=${folder}`), getJson("/jezzwtf/lora_folders"),
                ]);
                if (token !== refreshToken) return;
                files = (f.loras ?? []).filter((l) => l.present).map((l) => l.filename);
                folders = fl.folders ?? [];
            } else {
                const listed = await getJson("/jezzwtf/loras");
                if (token !== refreshToken) return;
                files = listed.map((n) => String(n).replace(/\\/g, "/"));
                folders = [...new Set(files.map((n) => splitName(n)[0].replace(/\/$/, "")))].sort((a, b) => a.localeCompare(b));
            }
        } catch {
            if (token !== refreshToken) return;
            files = [];
            folders = [];
        }
        fileSet = new Set(files.map((n) => (isFolderNode ? splitName(n)[1] : n)));
        render();
    }

    // -------- rows
    function reorder(from, to) {
        if (from === to || from < 0) return;
        const [item] = stack.splice(from, 1);
        stack.splice(clamp(to, 0, stack.length), 0, item);
        commit();
    }

    function rowMenu(i, x, y) {
        const e = stack[i];
        contextMenu(x, y, [
            [e.on ? "Disable" : "Enable", () => { e.on = !e.on; commit(); }],
            ["Move up", () => reorder(i, i - 1)],
            ["Move down", () => reorder(i, i + 1)],
            ["Remove", () => { stack.splice(i, 1); commit(); }],
        ]);
    }

    function startDrag(ev, i, rowEl) {
        ev.preventDefault();
        ev.stopPropagation();
        rowEl.classList.add("dragging");
        let target = i;
        const rows = [...list.children];
        const move = (e) => {
            rows.forEach((r) => r.classList.remove("drop-before", "drop-after"));
            let idx = rows.findIndex((r) => e.clientY < r.getBoundingClientRect().top + r.offsetHeight / 2);
            if (idx < 0) idx = rows.length;
            target = idx;
            if (idx < rows.length) rows[idx].classList.add("drop-before");
            else rows[rows.length - 1]?.classList.add("drop-after");
        };
        const up = () => {
            document.removeEventListener("pointermove", move);
            document.removeEventListener("pointerup", up);
            document.removeEventListener("pointercancel", cancel);
            rowEl.classList.remove("dragging");
            if (target !== i && target !== i + 1) reorder(i, target > i ? target - 1 : target);
            else render();
        };
        const cancel = () => {
            document.removeEventListener("pointermove", move);
            document.removeEventListener("pointerup", up);
            document.removeEventListener("pointercancel", cancel);
            rowEl.classList.remove("dragging");
            render();
        };
        document.addEventListener("pointermove", move);
        document.addEventListener("pointerup", up);
        document.addEventListener("pointercancel", cancel);
    }

    function buildRow(e, i) {
        const [dir, base] = splitName(e.name);
        const pill = h("button.jwtf-ls-pill" + (e.on ? ".on" : ""), {
            onclick: () => { e.on = !e.on; commit(); },
        });
        const present = fileSet.size === 0 || fileSet.has(isFolderNode ? splitName(e.name)[1] : e.name);
        const name = h("div.jwtf-ls-name", { title: e.name, onclick: (ev) => openPicker(ev, "swap", i) },
            dir ? h("i", {}, dir) : null, h("b", {}, base));
        const grip = h("div.jwtf-ls-grip", { title: "Drag to reorder" }, "⋮⋮");
        const row = h("div.jwtf-ls-row" + (e.on ? "" : ".off"), {
            oncontextmenu: (ev) => { ev.preventDefault(); rowMenu(i, ev.clientX, ev.clientY); },
        }, pill, grip, name, present ? null : h("span.jwtf-ls-badge", {}, "missing"));
        grip.addEventListener("pointerdown", (ev) => startDrag(ev, i, row));

        const steppers = [];
        const modelStep = makeStepper(() => e.model, (v) => {
            e.model = v;
            if (!separate()) e.clip = v;
            write();
            steppers.forEach((s) => s.render());
        }, () => !e.on);
        steppers.push(modelStep);
        row.append(modelStep.el);
        if (separate()) {
            const clipStep = makeStepper(() => e.clip, (v) => { e.clip = v; e.split = true; write(); steppers.forEach((s) => s.render()); }, () => !e.on);
            steppers.push(clipStep);
            row.append(clipStep.el);
        }
        row.append(h("div.jwtf-ls-x", { title: "Remove", onclick: () => { stack.splice(i, 1); commit(); } }, "✕"));
        steppers.forEach((s) => s.render());
        return row;
    }

    function render() {
        list.replaceChildren();
        const sep = separate();
        head.style.display = stack.length ? "" : "none";
        const onCount = stack.filter((e) => e.on).length;
        toggleAll.className = "jwtf-ls-pill" + (onCount === stack.length && stack.length ? " on" : onCount ? " mid" : "");
        countEl.textContent = `${onCount}/${stack.length}`;
        modeBtn.textContent = sep ? "Separate" : "Single";
        modeBtn.classList.toggle("on", sep);
        clearBtn.textContent = armedClear ? "Sure?" : "Clear";
        clearBtn.classList.toggle("armed", !!armedClear);
        cols.replaceChildren(...(sep ? ["Model", "Clip"] : ["Strength"]).map((t) => h("span", {}, t)));
        if (!stack.length) list.append(h("div.jwtf-ls-empty", {}, "No LoRAs. Add one below."));
        stack.forEach((e, i) => list.append(buildRow(e, i)));
        rollBtn.disabled = !onCount;
        scheduleFit();
    }

    let fitT = 0;
    function fit() {
        panelH = Math.max(60, root.offsetHeight + 2);
        fitNode(node);
    }
    function scheduleFit() {
        cancelAnimationFrame(fitT);
        fitT = requestAnimationFrame(fit);
    }

    // -------- picker
    function openPicker(ev, mode, swapIndex = -1) {
        closePopup();
        const search = h("input.jwtf-ml-input", { placeholder: `Search ${files.length} files...`, style: { width: "100%" } });
        const chipRow = h("div.jwtf-ml-row.jwtf-ml-wrap");
        const plist = h("div.jwtf-ls-plist");
        const title = h("div.jwtf-ml-row", {}, h("b.jwtf-ml-grow", {}, mode === "swap" ? "Replace LoRA" : "Add LoRAs"),
            h("span.jwtf-ml-muted", {}, `${stack.length} in stack`));
        const pop = h("div.jwtf-ls-pick", {}, title, search, chipRow, plist);
        let folderFilter = null; // null = all
        let hl = 0;
        let shown = [];

        const keyOf = (n) => (isFolderNode ? splitName(n)[1] : n);
        const inStack = (n) => stack.some((e) => e.name === keyOf(n));
        const saveFavs = () => saveJson(FAV_KEY, [...favs]);

        function toggleFile(n) {
            if (mode === "swap") {
                if (stack[swapIndex]) stack[swapIndex].name = keyOf(n);
                commit();
                closePopup();
                return;
            }
            const idx = stack.findIndex((e) => e.name === keyOf(n));
            if (idx >= 0) stack.splice(idx, 1);
            else stack.push({ on: true, name: keyOf(n), model: 1, clip: 1, split: false });
            commit();
            title.lastChild.textContent = `${stack.length} in stack`;
            drawList();
        }

        function drawChips() {
            chipRow.replaceChildren();
            if (isFolderNode) {
                if (folders.length < 1) return;
                for (const f of folders) {
                    chipRow.append(h("button.jwtf-ml-chip" + ((folderW?.value ?? "") === f ? ".on" : ""), {
                        onclick: () => {
                            if (folderW) { folderW.value = f; folderW.callback?.(f); }
                            refreshFiles().then(() => { drawChips(); drawList(); });
                        },
                    }, f || "root"));
                }
                return;
            }
            if (folders.length < 2) return;
            const chip = (label, val) => h("button.jwtf-ml-chip" + (folderFilter === val ? ".on" : ""), {
                onclick: () => { folderFilter = val; drawChips(); drawList(); },
            }, label);
            chipRow.append(chip("All", null), ...folders.map((f) => chip(f || "root", f)));
        }

        function drawList() {
            const q = search.value.trim().toLowerCase();
            const match = files.filter((n) => {
                if (q && !n.toLowerCase().includes(q)) return false;
                if (!isFolderNode && folderFilter !== null) return splitName(n)[0].replace(/\/$/, "") === folderFilter;
                return true;
            });
            const fav = match.filter((n) => favs.has(n)).sort((a, b) => a.localeCompare(b));
            const rest = match.filter((n) => !favs.has(n));
            shown = [...fav, ...rest];
            hl = clamp(hl, 0, Math.max(0, shown.length - 1));
            plist.replaceChildren();
            const item = (n, i) => {
                const [dir, base] = splitName(n);
                const star = h("div.jwtf-ls-star" + (favs.has(n) ? ".fav" : ""), {
                    onclick: (e) => { e.stopPropagation(); favs.has(n) ? favs.delete(n) : favs.add(n); saveFavs(); drawList(); },
                }, favs.has(n) ? "★" : "☆");
                return h("div.jwtf-ls-item" + (inStack(n) ? ".in" : "") + (i === hl ? ".hl" : ""), {
                    onclick: () => toggleFile(n),
                }, star, h("span.jwtf-ls-name", {}, dir ? h("i", {}, dir) : null, h("b", {}, base)),
                mode === "multi" && inStack(n) ? h("span", {}, "✓") : null);
            };
            shown.forEach((n, i) => {
                if (i === fav.length && fav.length) plist.append(h("div.jwtf-ls-sep"));
                plist.append(item(n, i));
            });
            if (!shown.length) plist.append(h("div.jwtf-ls-empty", {}, "No matches"));
            plist.children[hl]?.scrollIntoView?.({ block: "nearest" });
        }

        search.addEventListener("input", () => { hl = 0; drawList(); });
        search.addEventListener("keydown", (e) => {
            e.stopPropagation();
            if (e.key === "ArrowDown") { hl = Math.min(hl + 1, shown.length - 1); drawList(); e.preventDefault(); }
            else if (e.key === "ArrowUp") { hl = Math.max(hl - 1, 0); drawList(); e.preventDefault(); }
            else if (e.key === "Enter" && shown[hl]) toggleFile(shown[hl]);
            else if (e.key === "Escape") closePopup();
        });
        drawChips();
        drawList();
        placeNear(pop, ev.clientX, ev.clientY);
        search.focus();
        const away = (e) => { if (!pop.contains(e.target)) closePopup(); };
        setTimeout(() => document.addEventListener("pointerdown", away, true), 0);
        openPopup = () => { pop.remove(); document.removeEventListener("pointerdown", away, true); };
    }

    // -------- header / footer actions
    toggleAll.addEventListener("click", () => {
        const allOn = stack.length && stack.every((e) => e.on);
        for (const e of stack) e.on = !allOn;
        commit();
    });
    modeBtn.addEventListener("click", () => setMode(separate() ? SINGLE : SEPARATE));
    clearBtn.addEventListener("click", () => {
        if (armedClear) {
            clearTimeout(armedClear);
            armedClear = 0;
            stack = [];
            commit();
            return;
        }
        armedClear = setTimeout(() => { armedClear = 0; render(); }, 2000);
        render();
    });
    addBtn.addEventListener("click", (e) => openPicker(e, "multi"));
    rollBtn.addEventListener("click", () => {
        let lo = parseFloat(rollMin.value);
        let hi = parseFloat(rollMax.value);
        if (!Number.isFinite(lo)) lo = 0.4;
        if (!Number.isFinite(hi)) hi = 1;
        if (lo > hi) [lo, hi] = [hi, lo];
        for (const e of stack) {
            if (!e.on) continue;
            e.model = round2(clamp(lo + Math.random() * (hi - lo), -LIMIT, LIMIT));
            if (!separate()) e.clip = e.model;
            else e.clip = e.model, e.split = false;
        }
        commit();
    });

    // external edits to the hidden widget
    onWidget(dataW, (v) => {
        const s = String(v ?? "");
        if (s !== lastWritten) { lastWritten = s; load(s); }
    });
    let folderDebounce = 0;
    if (folderW) onWidget(folderW, () => {
        clearTimeout(folderDebounce);
        folderDebounce = setTimeout(refreshFiles, 250);
    });

    // node right-click menu
    const prevMenu = node.getExtraMenuOptions;
    node.getExtraMenuOptions = function (canvas, options) {
        prevMenu?.apply(this, arguments);
        options.push(null,
            { content: `${separate() ? "" : "✓ "}Single strength`, callback: () => setMode(SINGLE) },
            { content: `${separate() ? "✓ " : ""}Separate model & clip`, callback: () => setMode(SEPARATE) },
            { content: "Toggle all", callback: () => toggleAll.click() });
    };

    const widget = node.addDOMWidget("jwtf_lora_stack", "jwtf_lora_stack", root, {
        serialize: false, getMinHeight: () => panelH, hideOnZoom: false,
    });
    widget.computeSize = (w) => [w, panelH];

    node._jwtfSync = () => {
        if (dataW && String(dataW.value ?? "") !== lastWritten) { lastWritten = String(dataW.value ?? ""); load(lastWritten); }
        hideWidget(dataW);
        refreshFiles();
        setTimeout(fit, 60);
        setTimeout(fit, 400);
    };
    node._jwtfStop = () => { closePopup(); clearTimeout(armedClear); cancelAnimationFrame(fitT); };

    lastWritten = String(dataW?.value ?? "{}");
    load(lastWritten);
    refreshFiles();
    node.setSize([Math.max(node.size[0], 440), node.size[1]]);
    setTimeout(fit, 60);
    setTimeout(fit, 400);
    new ResizeObserver(() => scheduleFit()).observe(root);
}

app.registerExtension({
    name: "JezzWTF.ModelLoaders.LoraStack",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODES.includes(nodeData.name)) return;
        chain(nodeType.prototype, "onNodeCreated", function () { setupStack(this); });
        chain(nodeType.prototype, "onConfigure", function () { setTimeout(() => this._jwtfSync?.(), 0); });
        chain(nodeType.prototype, "onRemoved", function () { this._jwtfStop?.(); });
    },
});
