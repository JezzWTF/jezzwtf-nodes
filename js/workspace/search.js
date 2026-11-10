// Pure search and indexing helpers (no DOM, no ComfyUI imports) so they can be tested under plain node.

const WORD = /[\p{L}\p{N}_.-]+/gu;

export const terms = (query) => (String(query ?? "").toLowerCase().match(WORD) ?? []);

/** Every term must appear somewhere in the haystack (case-insensitive). */
export function matchesAll(haystack, query) {
  const need = terms(query);
  if (!need.length) return true;
  const hay = String(haystack ?? "").toLowerCase();
  return need.every((t) => hay.includes(t));
}

const STOP = new Set(["a", "an", "the", "is", "are", "to", "of", "in", "on", "it", "i", "my", "me", "do", "does", "did", "how",
  "where", "what", "why", "can", "go", "get", "for", "and", "or", "with", "this", "that", "not", "no"]);

const countOf = (hay, t, cap = 5) => { let n = 0, at = 0; while (n < cap && (at = hay.indexOf(t, at)) >= 0) { n++; at += t.length; } return n; };

/**
 * Rank a documentation page for a question. Filler words are ignored, a page needs at least half of the remaining
 * words, and title and keyword hits count more than body hits. 0 means no match.
 */
export function score(doc, query) {
  const all = terms(query);
  if (!all.length) return 1;
  const need = all.filter((t) => !STOP.has(t));
  const words = need.length ? need : all;
  const title = String(doc.title ?? "").toLowerCase();
  const body = String(doc.text ?? "").toLowerCase();
  const keys = String(doc.keywords ?? "").toLowerCase();
  let total = 0, hit = 0;
  for (const t of words) {
    const inTitle = title.includes(t), inKeys = keys.includes(t), n = countOf(body, t);
    if (!inTitle && !inKeys && !n) continue;
    hit++;
    total += (inTitle ? 6 : 0) + (inKeys ? 3 : 0) + n;
  }
  return hit >= Math.ceil(words.length / 2) ? total * hit : 0;
}

/** A short snippet of `text` around the first query term. */
export function snippet(text, query, width = 90) {
  const flat = String(text ?? "").replace(/\s+/g, " ").trim();
  const need = terms(query);
  const at = need.length ? flat.toLowerCase().indexOf(need[0]) : -1;
  if (at < 0) return flat.slice(0, width * 2);
  const start = Math.max(0, at - Math.floor(width / 3));
  return (start ? "…" : "") + flat.slice(start, start + width * 2) + (start + width * 2 < flat.length ? "…" : "");
}

const MODEL_EXT = /\.(safetensors|ckpt|pt|pth|gguf|sft|bin|onnx)$/i;
const NOTE_TYPES = new Set(["Note", "MarkdownNote"]);

/** API-format files ({ "12": { class_type, inputs } }) have no layout; index what they do contain. */
function indexApiFormat(workflow) {
  const entries = Object.values(workflow).filter((n) => n && typeof n === "object" && typeof n.class_type === "string");
  const models = new Set();
  const prompts = [];
  for (const n of entries) {
    for (const v of Object.values(n.inputs ?? {})) {
      if (typeof v !== "string" || !v) continue;
      if (MODEL_EXT.test(v)) models.add(v.split(/[\\/]/).pop());
      else if (v.length > 24 && /\s/.test(v)) prompts.push(v);
    }
  }
  return { nodeCount: entries.length, types: [...new Set(entries.map((n) => n.class_type))], models: [...models],
    text: prompts.join("\n").slice(0, 20000), apiFormat: true };
}

/** Collect what is worth searching inside a saved workflow: node types, titles, models, notes and prompts. */
export function indexWorkflow(workflow) {
  if (workflow && typeof workflow === "object" && !Array.isArray(workflow.nodes)
    && Object.values(workflow).some((n) => n && typeof n === "object" && typeof n.class_type === "string")) return indexApiFormat(workflow);
  const nodes = Array.isArray(workflow?.nodes) ? workflow.nodes : [];
  const types = new Set();
  const models = new Set();
  const notes = [];
  const prompts = [];
  for (const node of nodes) {
    if (typeof node?.type === "string") types.add(node.type);
    const values = Array.isArray(node?.widgets_values) ? node.widgets_values : [];
    for (const v of values) {
      if (typeof v !== "string" || !v) continue;
      if (MODEL_EXT.test(v)) models.add(v.split(/[\\/]/).pop());
      else if (NOTE_TYPES.has(node.type)) notes.push(v);
      else if (v.length > 24 && /\s/.test(v)) prompts.push(v);
    }
  }
  const groups = (Array.isArray(workflow?.groups) ? workflow.groups : []).map((g) => g?.title).filter((t) => typeof t === "string");
  const titles = nodes.map((n) => n?.title).filter((t) => typeof t === "string");
  return {
    nodeCount: nodes.length,
    types: [...types],
    models: [...models],
    text: [...notes, ...prompts, ...groups, ...titles].join("\n").slice(0, 20000),
  };
}

const VIDEO = /(SaveVideo|CreateVideo|VHS_VideoCombine|SaveWEBM|SaveAnimated|VideoToGif|LoadVideo)/;
const UPSCALE = /(Upscale|SeedVR|ESRGAN|UltimateSD)/i;
const INPAINT = /(Inpaint|Outpaint|SetLatentNoiseMask|VAEEncodeForInpaint)/i;
const LORA = /Lora/i;
const IMAGE_OUT = /(SaveImage|PreviewImage)/;
const THREE_D = /(3D|GLB|Mesh|Trellis|Tripo|Hunyuan3D|Gaussian|Splat|PointCloud|TextureProject)/i;
const AUDIO_OUT = /(SaveAudio|PreviewAudio|SaveWEBM|AudioVAEDecode|VAEDecodeAudio|TTS|Music)/i;

const FAMILIES = [
  ["Flux", /flux/i], ["Qwen", /qwen/i], ["SDXL", /(sdxl|xl_)/i], ["MiniMax H3", /(minimax|h3)/i],
  ["Wan", /wan/i], ["LTX", /ltx/i], ["Hunyuan", /hunyuan/i], ["Z-Image", /z_image/i],
];

/** Sidebar categories derived from the index: what a workflow makes and which model family it uses. */
export function categorize(index) {
  const types = index?.types ?? [];
  const joined = types.join(" ");
  const makes = [];
  const video = types.some((t) => VIDEO.test(t));
  const threeD = types.some((t) => THREE_D.test(t));
  if (video) makes.push("Video");
  if (threeD) makes.push("3D");
  if (!video && !threeD && types.some((t) => AUDIO_OUT.test(t)) && !types.some((t) => IMAGE_OUT.test(t))) makes.push("Audio");
  if (UPSCALE.test(joined)) makes.push("Upscale");
  if (INPAINT.test(joined)) makes.push("Inpaint / Outpaint");
  // Images only when nothing more specific was made: video and 3D workflows preview images on the way.
  if (!video && !threeD && types.some((t) => IMAGE_OUT.test(t))) makes.push("Image");
  if (LORA.test(joined)) makes.push("Uses a LoRA");
  if (types.some((t) => /^JWTF/.test(t))) makes.push("Uses JezzWTF nodes");
  const modelText = (index?.models ?? []).join(" ");
  const models = FAMILIES.filter(([, re]) => re.test(modelText)).map(([name]) => name);
  return { makes, models };
}

/** Human "5 days ago" style age from a unix-seconds or millisecond timestamp. */
export function ago(timestamp, now = Date.now()) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "";
  const ms = timestamp < 1e12 ? timestamp * 1000 : timestamp;
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 90) return "just now";
  const m = Math.round(s / 60);
  if (m < 90) return `${m}m ago`;
  const hr = Math.round(m / 60);
  if (hr < 36) return `${hr}h ago`;
  const d = Math.round(hr / 24);
  if (d < 45) return `${d} days ago`;
  return new Date(ms).toISOString().slice(0, 10);
}
