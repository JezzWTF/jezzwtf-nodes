import { app } from "../../../scripts/app.js";
import { chain, findWidget, getLink, h, hideWidget, injectCss } from "./_shared.js";

// Text Box and Text Encode (Zero Negative): custom text cards bound to hidden widgets.

injectCss("jwtf-textbox", `
.jwtf-tb-head { display: flex; align-items: center; gap: 6px; font-weight: 600; color: #c9ccd4; }
.jwtf-tb-foot { display: flex; align-items: center; gap: 6px; font-size: 11px; }
.jwtf-tb-ta { flex: 1 1 auto; min-height: 130px; }
.jwtf-tag { font-size: 10px; padding: 1px 6px; border-radius: 10px; background: #2d3a55; color: #b8c8f0; }
.jwtf-pill { padding: 2px 10px; border-radius: 12px; }
.jwtf-status { font-size: 11px; color: #8b8f99; }
.jwtf-status.err { color: #f43f5e; }
`);

export function counts(text) {
    const t = String(text ?? "");
    const trimmed = t.trim();
    return {
        chars: t.length,
        words: trimmed ? trimmed.split(/\s+/).length : 0,
        lines: t.length ? t.split("\n").length : 0,
    };
}

function pulse(dot) {
    dot.classList.add("live");
    clearTimeout(dot._t);
    dot._t = setTimeout(() => dot.classList.remove("live"), 1000);
}

async function copyText(text, ta) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        ta.select();
        try { return document.execCommand("copy"); } catch { return false; }
    }
}

// ---------------------------------------------------------------- Text Box

function setupTextBox(node) {
    const w = findWidget(node, "text");
    hideWidget(node, w);
    const dot = h("span.jwtf-dot");
    const ta = h("textarea.jwtf-ta.jwtf-tb-ta", { spellcheck: false, placeholder: "Type text..." });
    const stats = h("span.jwtf-muted.jwtf-grow");
    const copyBtn = h("button.jwtf-btn", { textContent: "Copy" });
    const clearBtn = h("button.jwtf-btn", { textContent: "Clear" });
    const root = h("div.jwtf-card", {}, h("div.jwtf-tb-head", {}, dot, "Text"), ta,
        h("div.jwtf-tb-foot", {}, stats, copyBtn, clearBtn));

    const refresh = () => {
        const c = counts(ta.value);
        stats.textContent = `${c.chars} chars · ${c.words} words · ${c.lines} lines`;
    };
    const write = (v) => {
        if (w) w.value = v;
        refresh();
        pulse(dot);
        node.setDirtyCanvas(true, false);
    };
    ta.addEventListener("input", () => write(ta.value));
    copyBtn.addEventListener("click", async () => {
        const ok = await copyText(ta.value, ta);
        copyBtn.textContent = ok ? "Copied" : "Failed";
        setTimeout(() => (copyBtn.textContent = "Copy"), 1200);
    });
    clearBtn.addEventListener("click", () => {
        ta.value = "";
        write("");
        ta.focus();
    });
    node._jwtfSync = () => {
        if (ta.value !== String(w?.value ?? "")) ta.value = String(w?.value ?? "");
        refresh();
    };
    node.addDOMWidget("jwtf_textbox", "jwtf_textbox", root, { serialize: false, getMinHeight: () => 220 });
    node._jwtfSync();
    node.setSize([Math.max(node.size[0], 320), Math.max(node.size[1], 260)]);
}

// ---------------------------------------------------------------- Text Encode (Zero Negative)

function upstreamText(node) {
    const inp = node.inputs?.find((i) => i.name === "positive");
    if (inp?.link == null) return null;
    const link = getLink(node.graph, inp.link);
    const src = link ? node.graph.getNodeById(link.origin_id) : null;
    if (!src) return { title: "?", text: null };
    const sw = src.widgets?.find((x) => typeof x.value === "string");
    return { title: src.title ?? src.type, text: sw ? sw.value : null };
}

function setupEncode(node) {
    const posW = findWidget(node, "positive");
    const modeW = findWidget(node, "negative_mode");
    const hideNative = () => { hideWidget(node, posW); hideWidget(node, modeW); };
    hideNative();

    const dot = h("span.jwtf-dot");
    const tag = h("span.jwtf-tag", { style: { display: "none" } });
    const ta = h("textarea.jwtf-ta.jwtf-tb-ta", { spellcheck: false, placeholder: "Positive prompt..." });
    const pills = ["Zero Out", "Empty String"].map((m) => h("button.jwtf-btn.jwtf-pill", { textContent: m }));
    const stats = h("span.jwtf-muted.jwtf-grow");
    const status = h("span.jwtf-status");
    const paste = h("button.jwtf-btn", { textContent: "Paste" });
    const root = h("div.jwtf-card", {},
        h("div.jwtf-tb-head", {}, dot, "Positive", tag),
        ta,
        h("div.jwtf-row", {}, h("span.jwtf-muted", {}, "Negative:"), ...pills),
        h("div.jwtf-tb-foot", {}, stats, status, paste));

    let linked = false;
    let lastUpstream = undefined;
    let poll = 0;

    const renderCounts = (text) => {
        const c = counts(text);
        stats.textContent = `${c.chars} chars · ${c.words} words`;
    };
    const renderPills = () => pills.forEach((p) => p.classList.toggle("on", p.textContent === modeW?.value));

    const showLinked = () => {
        const up = upstreamText(node);
        if (!up) return;
        const key = `${up.title}\u0000${up.text}`;
        if (key === lastUpstream) return;
        lastUpstream = key;
        tag.textContent = `← ${up.title}`;
        if (up.text == null) {
            ta.value = "";
            ta.placeholder = "Text arrives from the linked node at run time.";
        } else {
            ta.value = up.text;
        }
        renderCounts(up.text ?? "");
    };

    const evaluate = () => {
        hideNative();
        const nowLinked = node.inputs?.some((i) => i.name === "positive" && i.link != null) ?? false;
        if (nowLinked !== linked) {
            linked = nowLinked;
            ta.readOnly = linked;
            paste.disabled = linked;
            tag.style.display = linked ? "" : "none";
            clearInterval(poll);
            lastUpstream = undefined;
            if (linked) {
                poll = setInterval(showLinked, 250);
            } else {
                ta.placeholder = "Positive prompt...";
            }
        }
        if (linked) showLinked();
        else {
            const v = String(posW?.value ?? "");
            if (ta.value !== v) ta.value = v;
            renderCounts(v);
        }
        renderPills();
    };

    ta.addEventListener("input", () => {
        if (linked) return;
        if (posW) posW.value = ta.value;
        renderCounts(ta.value);
        pulse(dot);
    });
    pills.forEach((p) => p.addEventListener("click", () => {
        if (modeW) {
            modeW.value = p.textContent;
            modeW.callback?.(modeW.value);
        }
        renderPills();
        pulse(dot);
        node.setDirtyCanvas(true, false);
    }));
    paste.addEventListener("click", async () => {
        try {
            const text = await navigator.clipboard.readText();
            ta.value = text;
            if (posW) posW.value = text;
            renderCounts(text);
            pulse(dot);
            ta.focus();
            ta.setSelectionRange(text.length, text.length);
        } catch {
            status.textContent = "blocked";
            status.classList.add("err");
            dot.classList.add("err");
            setTimeout(() => {
                status.textContent = "";
                status.classList.remove("err");
                dot.classList.remove("err");
            }, 1600);
        }
    });

    node._jwtfSync = evaluate;
    node._jwtfStop = () => clearInterval(poll);
    node.addDOMWidget("jwtf_encode", "jwtf_encode", root, { serialize: false, getMinHeight: () => 210 });
    evaluate();
    node.setSize([Math.max(node.size[0], 340), Math.max(node.size[1], 270)]);
}

app.registerExtension({
    name: "JezzWTF.UtilityCore.TextBox",
    beforeRegisterNodeDef(nodeType, nodeData) {
        const setup = { JWTFTextBox: setupTextBox, JWTFTextEncodeZeroNeg: setupEncode }[nodeData.name];
        if (!setup) return;
        chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
        chain(nodeType.prototype, "onConfigure", function () { this._jwtfSync?.(); });
        chain(nodeType.prototype, "onConnectionsChange", function () { setTimeout(() => this._jwtfSync?.(), 0); });
        chain(nodeType.prototype, "onDrawForeground", function () {
            // Re-hide native widgets: convert-to-input can recreate them.
            if (nodeData.name === "JWTFTextEncodeZeroNeg") {
                for (const n of ["positive", "negative_mode"]) {
                    const w = findWidget(this, n);
                    if (w && !w.hidden) hideWidget(this, w);
                }
            }
        });
        chain(nodeType.prototype, "onRemoved", function () { this._jwtfStop?.(); });
    },
});
