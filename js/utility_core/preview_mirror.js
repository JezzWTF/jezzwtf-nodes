// Model Preview Mirror: shows a sampler's live preview (the `kj_preview_override` websocket event) in a panel on
// this node. The node's `jezzwtf_source_id` result says which sampler to follow; empty means follow any preview.
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, fitHeight, h, injectCss } from "./_shared.js";
import { follows, mediaSource, statusLine } from "./mirror_logic.js";

const NODE = "JWTFModelPreviewMirror";
const EVENT = "kj_preview_override";
const UI_KEY = "jezzwtf_source_id";

injectCss("jwtf-preview-mirror", `
.jwtf-pm { box-sizing: border-box; display: flex; flex-direction: column; gap: 4px; width: 100%; height: 100%; padding: 4px;
  font: 12px system-ui, sans-serif; color: #dfe2ea; background: #16181d; border: 1px solid #2c2f37; border-radius: 8px; }
.jwtf-pm-media { flex: 1 1 auto; min-height: 120px; display: flex; align-items: center; justify-content: center;
  background: #0d0e11; border-radius: 6px; overflow: hidden; }
.jwtf-pm-media img, .jwtf-pm-media video { max-width: 100%; max-height: 100%; object-fit: contain; }
.jwtf-pm-empty { color: #5b5f6a; padding: 8px; text-align: center; }
.jwtf-pm-line { font-size: 11px; color: #8b8f99; font-variant-numeric: tabular-nums; min-height: 1.3em; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
`);

const mirrors = new Set();
const latest = new Map(); // sampler node id -> its most recent frame, so a mirror added mid-run has something to show
let wired = false;

function show(m, p) {
  const src = mediaSource(p);
  if (!src) return;
  const el = src.video
    ? h("video", { src: src.url, autoplay: true, loop: true, muted: true, playsInline: true })
    : h("img", { src: src.url, alt: "sampler preview" });
  if (src.video) {
    el.defaultMuted = true;
    el.play?.().catch(() => { /* autoplay can be refused; the first frame still shows */ });
  }
  m.media.replaceChildren(el);
  m.line.textContent = statusLine(p);
  m.shown = p.node_id;
}

function onFrame(p) {
  if (p?.node_id != null && p.image) latest.set(String(p.node_id), p);
  for (const m of mirrors) if (follows(m.source, p?.node_id)) show(m, p);
}

function wire() {
  if (wired) return;
  wired = true;
  api.addEventListener(EVENT, (e) => onFrame(e.detail ?? {}));
  // a new run starts from a blank panel
  api.addEventListener("execution_start", () => {
    latest.clear();
    for (const m of mirrors) { m.media.replaceChildren(m.empty); m.line.textContent = ""; }
  });
}

function setup(node) {
  wire();
  const empty = h("div.jwtf-pm-empty", {}, "Waiting for a sampler preview…");
  const media = h("div.jwtf-pm-media", {}, empty);
  const line = h("div.jwtf-pm-line");
  const root = h("div.jwtf-pm", {}, media, line);
  node.addDOMWidget("jwtf_preview_mirror", "jwtf_preview_mirror", root, { serialize: false, getMinHeight: () => 200 });
  const m = { node, media, line, empty, source: "", shown: null };
  node._jwtfMirror = m;
  mirrors.add(m);
  fitHeight(node, 340);
}

app.registerExtension({
  name: "JezzWTF.PreviewMirror",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE) return;
    chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
    chain(nodeType.prototype, "onExecuted", function (message) {
      const m = this._jwtfMirror;
      if (!m) return;
      m.source = message?.[UI_KEY]?.[0] ?? "";
      const known = m.source ? latest.get(String(m.source)) : [...latest.values()].at(-1);
      if (known) show(m, known);
    });
    chain(nodeType.prototype, "onRemoved", function () { if (this._jwtfMirror) mirrors.delete(this._jwtfMirror); });
  },
});
