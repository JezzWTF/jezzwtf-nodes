// GIF Tools: live result preview (animated <img> from /view), a stats line, and mode-aware widget states.
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { formatBytes, statsLine, viewUrl, widgetRules } from "./gif_core.js";

const EXT_NAME = "JezzWTF.GifTools";
const PREVIEW_NODES = new Set(["JWTFVideoToGif", "JWTFGifOptimise", "JWTFFramesToAnimated"]);
const COMPARE_NODE = "JWTFGifCompare";
const MIN_W = 320;
const PREVIEW_H = 190;
const STYLE_ID = "jwtf-gif-tools-style";

function ensureStyle() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
.jwtf-gif { display: flex; flex-direction: column; gap: 4px; width: 100%; height: 100%; box-sizing: border-box; }
.jwtf-gif-frame { flex: 1 1 auto; min-height: 0; display: flex; align-items: center; justify-content: center;
  background: var(--comfy-input-bg, #222); border-radius: 4px; overflow: hidden; }
.jwtf-gif-frame img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; }
.jwtf-gif-empty { color: var(--descrip-text, #999); font-size: 11px; }
.jwtf-gif-stats { flex: 0 0 auto; font: 11px/1.35 var(--font-family, monospace); color: var(--descrip-text, #aaa);
  white-space: normal; overflow-wrap: anywhere; user-select: text; }
.jwtf-gif-stats[data-over="true"] { color: var(--error-text, #e66); }
.jwtf-gif-text { font: 11px/1.4 var(--font-family, monospace); color: var(--input-text, #ddd); white-space: pre-wrap;
  overflow: auto; height: 100%; box-sizing: border-box; padding: 4px 6px; background: var(--comfy-input-bg, #222);
  border-radius: 4px; user-select: text; }`;
  document.head.appendChild(style);
}

function setWidgetDisabled(widget, disabled) {
  widget.disabled = disabled;
  // Older frontends read options.read_only instead of `disabled`.
  widget.options = { ...(widget.options || {}), read_only: disabled };
}

function applyModeRules(node) {
  const mode = node.widgets?.find((w) => w.name === "mode")?.value;
  const rules = widgetRules(mode);
  for (const w of node.widgets ?? []) {
    if (Object.prototype.hasOwnProperty.call(rules, w.name)) setWidgetDisabled(w, rules[w.name]);
  }
  node.setDirtyCanvas?.(true, true);
}

function budgetHint(node) {
  const mode = node.widgets?.find((w) => w.name === "mode")?.value;
  if (mode !== "target_size") return "";
  const mb = Number(node.widgets?.find((w) => w.name === "target_size_mb")?.value);
  return Number.isFinite(mb) ? `target ${formatBytes(mb * 1024 * 1024)}` : "";
}

function buildPreview(node) {
  ensureStyle();
  const img = document.createElement("img");
  img.alt = "GIF preview";
  img.decoding = "async";
  const empty = document.createElement("span");
  empty.className = "jwtf-gif-empty";
  const frame = document.createElement("div");
  frame.className = "jwtf-gif-frame";
  frame.append(empty);
  const stats = document.createElement("div");
  stats.className = "jwtf-gif-stats";
  const root = document.createElement("div");
  root.className = "jwtf-gif";
  root.append(frame, stats);

  const widget = node.addDOMWidget("gif_preview", "jwtf_gif_preview", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => PREVIEW_H,
  });
  widget.serialize = false;

  const api_ = {
    refreshHint() {
      if (img.isConnected) return;
      empty.textContent = budgetHint(node) || "Run to preview";
      stats.textContent = "";
    },
    show(entry, mode) {
      if (!entry) return;
      const url = viewUrl((p) => api.apiURL(p), entry);
      img.onerror = () => {
        frame.replaceChildren(empty);
        empty.textContent = "Preview unavailable";
      };
      img.src = url;
      frame.replaceChildren(img);
      const line = statsLine(entry.stats, mode || entry.mode);
      stats.textContent = line;
      stats.title = entry.filename ? `${entry.subfolder ? `${entry.subfolder}/` : ""}${entry.filename}` : "";
      stats.dataset.over = entry.stats?.fits === false ? "true" : "false";
    },
  };
  api_.refreshHint();
  return api_;
}

function buildTextPanel(node) {
  ensureStyle();
  const box = document.createElement("div");
  box.className = "jwtf-gif-text";
  box.textContent = "Run to compare";
  const widget = node.addDOMWidget("gif_report", "jwtf_gif_report", box, { serialize: false, getMinHeight: () => 110 });
  widget.serialize = false;
  return { set: (text) => { box.textContent = text; } };
}

app.registerExtension({
  name: EXT_NAME,
  async beforeRegisterNodeDef(nodeType, nodeData) {
    const name = nodeData?.name;
    const isPreview = PREVIEW_NODES.has(name);
    if (!isPreview && name !== COMPARE_NODE) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const r = onCreated?.apply(this, args);
      if (isPreview) {
        this.__jwtfGif = buildPreview(this);
        if (name !== "JWTFFramesToAnimated") {
          const modeWidget = this.widgets?.find((w) => w.name === "mode");
          if (modeWidget) {
            const prev = modeWidget.callback;
            modeWidget.callback = (...cbArgs) => {
              prev?.apply(modeWidget, cbArgs);
              applyModeRules(this);
              this.__jwtfGif?.refreshHint();
            };
          }
          const budget = this.widgets?.find((w) => w.name === "target_size_mb");
          if (budget) {
            const prev = budget.callback;
            budget.callback = (...cbArgs) => {
              prev?.apply(budget, cbArgs);
              this.__jwtfGif?.refreshHint();
            };
          }
          applyModeRules(this);
        }
      } else {
        this.__jwtfText = buildTextPanel(this);
      }
      this.size[0] = Math.max(this.size[0], MIN_W);
      return r;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.call(this, message);
      const entry = message?.jwtf_gif?.[0];
      if (entry && this.__jwtfGif) {
        this.__jwtfGif.show(entry, entry.mode);
        this.properties = this.properties || {};
        this.properties.jwtf_last_gif = entry;
      }
      const text = message?.jwtf_gif_text?.[0];
      if (typeof text === "string" && this.__jwtfText) this.__jwtfText.set(text);
    };

    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (...args) {
      const r = onConfigure?.apply(this, args);
      if (isPreview) {
        // Saved workflows come back with their last result so the card is not blank after a reload.
        if (name !== "JWTFFramesToAnimated") applyModeRules(this);
        const last = this.properties?.jwtf_last_gif;
        if (last && this.__jwtfGif) this.__jwtfGif.show(last, last.mode);
      }
      return r;
    };
  },
});
