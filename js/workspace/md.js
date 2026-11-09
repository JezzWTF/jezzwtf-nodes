// A small, safe Markdown subset for the docs window. It never touches innerHTML: the parser returns plain
// block objects, and `renderBlocks` builds DOM nodes with textContent only.

const INLINE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\[[^\]]+\]\([^)\s]+\))/g;

/** Split a line of text into inline tokens: text, code, bold, italic, link. */
export function parseInline(text) {
  const out = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    if (m.index > last) out.push({ t: "text", v: text.slice(last, m.index) });
    const raw = m[0];
    if (m[1]) out.push({ t: "code", v: raw.slice(1, -1) });
    else if (m[2]) out.push({ t: "bold", v: raw.slice(2, -2) });
    else if (m[3]) out.push({ t: "italic", v: raw.slice(1, -1) });
    else {
      const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(raw);
      out.push({ t: "link", v: link[1], href: link[2] });
    }
    last = m.index + raw.length;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}

const splitRow = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
const isTableRule = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);

/** Parse Markdown into blocks: heading, para, list, quote, code, table. */
export function parseMarkdown(source) {
  const lines = String(source ?? "").replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = /^```(\w*)\s*$/.exec(line);
    if (fence) {
      const body = [];
      i++;
      while (i < lines.length && !/^```\s*$/.test(lines[i])) body.push(lines[i++]);
      i++;
      blocks.push({ type: "code", lang: fence[1], text: body.join("\n") });
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) { blocks.push({ type: "heading", level: heading[1].length, text: heading[2].trim() }); i++; continue; }
    if (line.includes("|") && i + 1 < lines.length && isTableRule(lines[i + 1])) {
      const head = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(splitRow(lines[i++]));
      blocks.push({ type: "table", head, rows });
      continue;
    }
    if (/^>\s?/.test(line)) {
      const body = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, ""));
      blocks.push({ type: "quote", text: body.join(" ") });
      continue;
    }
    const bullet = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(line);
    if (bullet) {
      const ordered = /\d/.test(bullet[2]);
      const items = [];
      while (i < lines.length) {
        const m = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(lines[i]);
        if (!m || /\d/.test(m[2]) !== ordered) break;
        items.push(m[3]);
        i++;
      }
      blocks.push({ type: "list", ordered, items });
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|>\s?|\s*([-*]|\d+\.)\s)/.test(lines[i])
      && !(lines[i].includes("|") && i + 1 < lines.length && isTableRule(lines[i + 1]))) para.push(lines[i++].trim());
    blocks.push({ type: "para", text: para.join(" ") });
  }
  return blocks;
}

/** Plain text of the blocks (for search and "Copy as text"). */
export function blocksToText(blocks) {
  const strip = (t) => parseInline(t).map((x) => x.v).join("");
  return blocks.map((b) => {
    switch (b.type) {
      case "heading": return strip(b.text).toUpperCase();
      case "list": return b.items.map((it, n) => `${b.ordered ? `${n + 1}.` : "-"} ${strip(it)}`).join("\n");
      case "code": return b.text;
      case "table": return [b.head, ...b.rows].map((r) => r.map(strip).join(" | ")).join("\n");
      default: return strip(b.text);
    }
  }).join("\n\n");
}

/** A link is only followed when it is http(s) or an internal `topic:<id>` reference. */
export function classifyLink(href) {
  if (/^https?:\/\//i.test(href)) return "external";
  if (/^topic:[\w-]+$/.test(href)) return "topic";
  return "blocked";
}

/** Build DOM for blocks. `h` is the DOM helper; `onTopic(id)` handles internal links. */
export function renderBlocks(blocks, h, onTopic) {
  const inline = (text) => parseInline(text).map((tok) => {
    if (tok.t === "code") return h("code", { textContent: tok.v });
    if (tok.t === "bold") return h("strong", { textContent: tok.v });
    if (tok.t === "italic") return h("em", { textContent: tok.v });
    if (tok.t === "link") {
      const kind = classifyLink(tok.href);
      if (kind === "external") return h("a", { href: tok.href, target: "_blank", rel: "noopener noreferrer", textContent: tok.v });
      if (kind === "topic") {
        return h("a", { href: "#", textContent: tok.v, onclick: (e) => { e.preventDefault(); onTopic?.(tok.href.slice(6)); } });
      }
      return document.createTextNode(tok.v);
    }
    return document.createTextNode(tok.v);
  });
  return blocks.map((b) => {
    switch (b.type) {
      case "heading": return h(`h${Math.min(4, b.level + 1)}`, {}, ...inline(b.text));
      case "list": return h(b.ordered ? "ol" : "ul", {}, ...b.items.map((it) => h("li", {}, ...inline(it))));
      case "quote": return h("blockquote", {}, ...inline(b.text));
      case "code": return h("pre", {}, h("code", { textContent: b.text }));
      case "table": return h("table", {}, h("thead", {}, h("tr", {}, ...b.head.map((c) => h("th", {}, ...inline(c))))),
        h("tbody", {}, ...b.rows.map((r) => h("tr", {}, ...r.map((c) => h("td", {}, ...inline(c)))))));
      default: return h("p", {}, ...inline(b.text));
    }
  });
}
