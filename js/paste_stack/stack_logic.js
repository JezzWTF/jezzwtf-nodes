// Paste Stack pure logic: no DOM, no ComfyUI imports, so it can be unit tested under plain Node.

export const LIMITS = Object.freeze({
  textChars: 1000000,
  textFileBytes: 1000000,
  blobBytes: 25 * 1024 * 1024,
  defaultEntries: 50,
  minEntries: 5,
  maxEntries: 500,
});

const IMAGE_EXT = ["png", "jpg", "jpeg", "webp", "gif", "bmp", "avif"];
const TEXT_EXT = ["txt", "md", "markdown", "json", "csv", "tsv", "yaml", "yml", "log", "ini", "toml", "xml", "html", "htm", "css", "js", "py"];

export function extensionOf(name) {
  const i = String(name || "").lastIndexOf(".");
  return i < 0 ? "" : name.slice(i + 1).toLowerCase();
}

export function clamp(value, lo, hi) {
  return Math.min(Math.max(value, lo), hi);
}

export function normalizeLimit(value) {
  const n = Number(value) || LIMITS.defaultEntries;
  return clamp(n, LIMITS.minEntries, LIMITS.maxEntries);
}

export function makeId(now = Date.now(), rand = Math.random) {
  let tail = "";
  for (let i = 0; i < 4; i++) tail += Math.floor(rand() * 36).toString(36);
  return now.toString(36) + tail;
}

// ---------------------------------------------------------------- classification

export function imageMimeFromName(name) {
  const ext = extensionOf(name);
  return IMAGE_EXT.includes(ext) ? "image/" + (ext === "jpg" ? "jpeg" : ext) : "";
}

/** @returns {"image"|"text"|"file"} */
export function classifyFile(name, mime) {
  const type = mime || imageMimeFromName(name);
  if (type.startsWith("image/")) return "image";
  if (type.startsWith("text/") || type === "application/json" || TEXT_EXT.includes(extensionOf(name))) return "text";
  return "file";
}

/** True when text is a single absolute image file path (a copied file, not a prompt). */
export function looksLikeImagePath(text) {
  const t = String(text || "").trim();
  if (!t || /[\r\n]/.test(t)) return false;
  if (!/^(?:[A-Za-z]:\\|\/)/.test(t)) return false;
  return /\.(png|jpe?g|webp|gif|bmp|avif)$/i.test(t);
}

/** Returns a refusal message, or "" when the item may be stored. */
export function refusalFor(kind, size, name = "") {
  if (kind === "text-file" && size > LIMITS.textFileBytes) return `${name} is too large to save as text.`;
  if (kind === "text" && size > LIMITS.textChars) return "That text is too long to save (over 1,000,000 characters).";
  if (kind === "image" && size > LIMITS.blobBytes) return "That image is over 25 MB, so it wasn't saved.";
  if (kind === "file" && size > LIMITS.blobBytes) return `${name} is over 25 MB, so it wasn't saved.`;
  return "";
}

// ---------------------------------------------------------------- fingerprints

export function hexFromBuffer(buf) {
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

/** Size-and-type fingerprint used when SubtleCrypto is unavailable. */
export function fallbackKey(size, mime) {
  return `${size}:${mime || ""}`;
}

/** SHA-256 hex (first 32 chars) of a Blob, with the fallback when hashing is unavailable. */
export async function fingerprint(blob, subtle = globalThis.crypto && globalThis.crypto.subtle) {
  try {
    if (!subtle) throw new Error("no subtle");
    return hexFromBuffer(await subtle.digest("SHA-256", await blob.arrayBuffer()));
  } catch {
    return fallbackKey(blob.size, blob.type);
  }
}

export function findDuplicate(items, kind, key) {
  return items.find((it) => it.kind === kind && it.key === key) || null;
}

// ---------------------------------------------------------------- ordering

/**
 * Sort loaded records by `ord`; legacy records without a numeric `ord` go above all ordered ones,
 * newest first, and get ord values below the smallest existing one. Returns {items, changed}.
 */
export function normalizeOrder(records) {
  const ordered = records.filter((r) => typeof r.ord === "number" && Number.isFinite(r.ord)).sort((a, b) => a.ord - b.ord);
  const legacy = records.filter((r) => !(typeof r.ord === "number" && Number.isFinite(r.ord))).sort((a, b) => (b.ts || 0) - (a.ts || 0));
  const top = ordered.length ? ordered[0].ord : 0;
  const changed = [];
  legacy.forEach((r, i) => {
    r.ord = top - legacy.length + i;
    changed.push(r);
  });
  return { items: [...legacy, ...ordered], changed };
}

export function nextTopOrd(items) {
  return items.length ? items[0].ord - 1 : 0;
}

/**
 * Plan a move of the card at `from` to slot `to` (index among the list after lifting it).
 * `ords` is the current ascending ord array. Returns null for a no-op, {renumber:true} when no
 * float lies strictly between the neighbours, or {ord} for the moved record only.
 */
export function planMove(ords, from, to) {
  if (from < 0 || from >= ords.length || to === from) return null;
  const others = ords.filter((_, i) => i !== from);
  const idx = clamp(to, 0, others.length);
  if (idx === from) return null;
  let ord;
  if (!others.length) ord = 0;
  else if (idx === 0) ord = others[0] - 1;
  else if (idx === others.length) ord = others[others.length - 1] + 1;
  else {
    const lo = others[idx - 1];
    const hi = others[idx];
    ord = (lo + hi) / 2;
    if (!(ord > lo && ord < hi)) return { renumber: true, to: idx };
  }
  return { ord, to: idx };
}

export function moveInArray(list, from, to) {
  const copy = list.slice();
  const [item] = copy.splice(from, 1);
  copy.splice(clamp(to, 0, copy.length), 0, item);
  return copy;
}

// ---------------------------------------------------------------- eviction

/** Records to delete so at most `limit` remain: smallest `ts` first. */
export function pickEvictions(items, limit) {
  const over = items.length - limit;
  if (over <= 0) return [];
  return items.slice().sort((a, b) => a.ts - b.ts).slice(0, over);
}

// ---------------------------------------------------------------- formatting

export function relativeAge(ts, now = Date.now()) {
  const s = Math.max(0, (now - ts) / 1000);
  if (s < 45) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${Math.max(1, m)}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ---------------------------------------------------------------- upload naming

const MIME_EXT = { jpeg: "jpg", "svg+xml": "svg" };

export function safeUploadName(name, id, mime) {
  let base = String(name || "").trim() || `paste_${id}`;
  base = base.replace(/[\\/:*?"<>|]+/g, "_").trim() || `paste_${id}`;
  if (!/\.[A-Za-z0-9]{2,5}$/.test(base)) {
    let sub = String(mime || "image/png").split("/")[1] || "png";
    sub = sub.split("+")[0];
    base += "." + (MIME_EXT[sub] || sub || "png");
  }
  return base;
}

export function widgetValueFrom(response) {
  return response.subfolder ? `${response.subfolder}/${response.name}` : response.name;
}

/** Does this node accept a dropped image: not collapsed, not LoadImageOutput, has a combo widget named image. */
export function nodeAcceptsImage(node) {
  if (!node || (node.flags && node.flags.collapsed)) return false;
  if (node.comfyClass === "LoadImageOutput" || node.type === "LoadImageOutput") return false;
  const w = (node.widgets || []).find((x) => x.name === "image");
  return !!w && (w.type === "combo" || !!(w.options && Array.isArray(w.options.values)));
}

export function base64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
