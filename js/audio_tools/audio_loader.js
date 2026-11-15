// Audio Loader: an upload button and a small player under the file picker.
// (The frontend's own audio-upload widget only supports the core Load Audio node, so this node brings its own.)
import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, findWidget, fitHeight, h, onWidget } from "../utility_core/_shared.js";
import { createWaveform } from "./waveform.js";

const NODE = "JWTFAudioLoader";
const NONE = "(no audio in input)";

async function upload(file) {
  const body = new FormData();
  body.append("image", file);
  body.append("type", "input");
  body.append("overwrite", "true");
  const res = await api.fetchApi("/upload/image", { method: "POST", body });
  if (!res.ok) throw new Error(`upload failed (${res.status})`);
  const data = await res.json();
  return data.subfolder ? `${data.subfolder}/${data.name}` : data.name;
}

function setup(node) {
  const picker = findWidget(node, "audio");
  if (!picker) return;
  const player = h("audio", { controls: true, preload: "metadata", style: { width: "100%" } });
  const status = h("span.jwtf-muted", {});
  const input = h("input", { type: "file", accept: "audio/*,.flac,.m4a,.opus,.aac", hidden: true });
  const button = h("button.jwtf-btn", { type: "button" }, "Upload audio…");
  const waveform = createWaveform(node, player);
  const body = h("div.jwtf-card", {}, h("div.jwtf-row", {}, button, status), waveform.body, player);
  body.append(input);

  const show = () => {
    const name = String(findWidget(node, "path")?.value || picker.value || "").trim();
    if (!name || name === NONE) { player.removeAttribute("src"); waveform.load(""); return; }
    player.src = api.apiURL(`/jezzwtf/audio/source?${new URLSearchParams({file: name})}`);
    waveform.load(name);
  };
  button.addEventListener("click", () => input.click());
  input.addEventListener("change", async () => {
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    status.textContent = "Uploading…";
    try {
      const name = await upload(file);
      const values = picker.options.values;
      if (Array.isArray(values)) {
        const at = values.indexOf(NONE);
        if (at >= 0) values.splice(at, 1);
        if (!values.includes(name)) values.push(name);
      }
      picker.value = name;
      picker.callback?.(name);
      status.textContent = "";
      show();
      node.setDirtyCanvas(true, true);
    } catch (err) {
      status.textContent = String(err.message ?? err);
    }
  });
  const previous = picker.callback;
  picker.callback = function (...args) { previous?.apply(this, args); show(); };

  const path = findWidget(node, "path");
  if (path) onWidget(path, show);
  node.addDOMWidget("jwtf_audio_preview", "jwtf_audio_preview", body, { serialize: false, getMinHeight: () => 210 });
  node._jwtfAudio = { show };
  fitHeight(node, 300);
  show();
}

app.registerExtension({
  name: "JezzWTF.AudioTools",
  beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE) return;
    chain(nodeType.prototype, "onNodeCreated", function () { setup(this); });
    chain(nodeType.prototype, "onConfigure", function () { this._jwtfAudio?.show(); });
  },
});
