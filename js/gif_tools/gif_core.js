// GIF Tools: pure helpers (formatting, widget rules, view URLs). No ComfyUI imports, so they can be syntax-checked
// and unit-tested in isolation.

export const TARGET_MODE = "target_size";
// Widgets the target_size search chooses for itself, and widgets only that mode reads.
export const SEARCHED_WIDGETS = ["colors", "dither"];
export const BUDGET_WIDGETS = ["target_size_mb", "max_trials", "time_budget_s"];

export function formatBytes(n) {
  if (!Number.isFinite(n) || n < 0) return "?";
  if (n < 1024) return `${Math.round(n)} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

const num = (v) => typeof v === "number" && Number.isFinite(v);

/** One compact line from the stats object the Python side attaches to each result. */
export function statsLine(stats, mode) {
  if (!stats) return "";
  const parts = [];
  if (num(stats.bytes)) parts.push(formatBytes(stats.bytes));
  if (num(stats.width) && num(stats.height)) parts.push(`${stats.width}x${stats.height}`);
  if (num(stats.frames)) parts.push(`${stats.frames} fr`);
  if (num(stats.fps)) parts.push(`${stats.fps} fps`);
  if (num(stats.colors)) parts.push(`${stats.colors} col`);
  if (stats.dither && stats.dither !== "none") parts.push(String(stats.dither));
  if (stats.format) parts.push(stats.lossless ? `${stats.format} lossless` : `${stats.format}${num(stats.quality) ? ` q${stats.quality}` : ""}`);
  if (num(stats.ssim)) parts.push(`SSIM ${stats.ssim.toFixed(3)}`);
  if (num(stats.saved_pct)) parts.push(`${stats.saved_pct >= 0 ? "-" : "+"}${Math.abs(stats.saved_pct).toFixed(0)}% vs naive`);
  if (num(stats.budget_bytes)) {
    const pct = num(stats.bytes) ? Math.round((stats.bytes / stats.budget_bytes) * 100) : null;
    parts.push(`budget ${formatBytes(stats.budget_bytes)}${pct === null ? "" : ` (${pct}%)`}${stats.fits === false ? " OVER" : ""}`);
  }
  return parts.join("  ·  ");
}

/** Which widgets should be inert for the selected mode: {widgetName: disabled}. */
export function widgetRules(mode) {
  const target = mode === TARGET_MODE;
  const rules = {};
  for (const name of SEARCHED_WIDGETS) rules[name] = target;
  for (const name of BUDGET_WIDGETS) rules[name] = !target;
  return rules;
}

export function viewUrl(apiURL, entry) {
  if (!entry || typeof entry.filename !== "string") return "";
  const q = new URLSearchParams({
    filename: entry.filename,
    subfolder: entry.subfolder || "",
    type: entry.type || "output",
    rand: String(Math.random()),
  });
  return apiURL(`/view?${q.toString()}`);
}
