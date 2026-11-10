// Pure rules for the Model Preview Mirror panel (no DOM, no ComfyUI imports) so they can be tested under plain node.

/** Does a preview from `eventNodeId` belong in a mirror that follows `source` (a node id, or empty for "any")? */
export function follows(source, eventNodeId) {
  if (eventNodeId === null || eventNodeId === undefined || eventNodeId === "") return false;
  if (source === null || source === undefined || source === "") return true;
  const a = String(source), b = String(eventNodeId);
  // ids inside subgraphs look like "12:34"; a sampler may report the whole path or only its last part
  const last = (s) => s.split(":").pop();
  return a === b || ((!a.includes(":") || !b.includes(":")) && last(a) === last(b));
}

/** The line of numbers under the picture: "step 4/20 · sigma 0.812 · change 0.031". */
export function statusLine(p) {
  const bits = [];
  if (Number.isFinite(p?.step) && Number.isFinite(p?.total) && p.total > 0) bits.push(`step ${p.step}/${p.total}`);
  else if (Number.isFinite(p?.step)) bits.push(`step ${p.step}`);
  if (Number.isFinite(p?.sigma)) bits.push(`sigma ${p.sigma.toFixed(3)}`);
  if (Number.isFinite(p?.delta)) bits.push(`change ${p.delta.toFixed(3)}`);
  return bits.join(" · ");
}

/** Where a frame's media comes from, or null when it carries none. */
export function mediaSource(p) {
  if (!p || typeof p.image !== "string" || !p.image) return null;
  const mime = typeof p.mime === "string" && /^(image|video)\/[a-z0-9.+-]+$/i.test(p.mime) ? p.mime : "image/jpeg";
  return { url: `data:${mime};base64,${p.image}`, video: mime.startsWith("video/") };
}
