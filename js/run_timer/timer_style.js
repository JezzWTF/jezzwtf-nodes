// Run Timer appearance: the choices, their validation and the maths for the ring face. Pure (no DOM, no ComfyUI)
// so it can be tested under plain node. The chosen style lives in the node's properties and saves with the workflow.

export const FACES = { digital: "Digital", ring: "Circular", analog: "Analog" };
export const SKINS = { glass: "Glass", neon: "Neon", flat: "Flat" };
export const THEMES = {
  ember: { label: "Ember", color: "#e8703a" },
  mint: { label: "Mint", color: "#3ddc97" },
  ice: { label: "Ice", color: "#56c8ff" },
  violet: { label: "Violet", color: "#a78bfa" },
  rose: { label: "Rose", color: "#ff6b9d" },
  gold: { label: "Gold", color: "#f5c542" },
  white: { label: "White", color: "#e8e8ec" },
};
export const FONTS = {
  mono: { label: "Mono", css: 'ui-monospace, "Cascadia Mono", "SF Mono", Consolas, monospace', weight: 800, scale: 1 },
  sans: { label: "Sans", css: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', weight: 700, scale: 1 },
  rounded: { label: "Rounded", css: '"Arial Rounded MT Bold", "Nunito", "Varela Round", ui-rounded, system-ui, sans-serif', weight: 800, scale: 0.95 },
  serif: { label: "Serif", css: 'Georgia, "Times New Roman", serif', weight: 700, scale: 0.88 },
  thin: { label: "Thin", css: '"Segoe UI Light", "Helvetica Neue", system-ui, sans-serif', weight: 200, scale: 0.8 },
  condensed: { label: "Condensed", css: '"Arial Narrow", "Roboto Condensed", Impact, system-ui, sans-serif', weight: 700, scale: 1.15 },
};
export const BACKGROUNDS = {
  dark: { label: "Dark", css: "#0c0c0e" },
  black: { label: "Black", css: "#000000" },
  clear: { label: "Clear", css: "transparent" },
  light: { label: "Light", css: "#e9e9ee" },
};

export const ANIMS = { arc: "Laps", ticks: "Ticks", comet: "Comet" };
export const LAPS = { "10": "10 s", "30": "30 s", "60": "1 min", avg: "Average run" };

export const DEFAULT_STYLE = { skin: "glass", face: "digital", theme: "ember", color: "", font: "mono", background: "dark", statusTint: true, anim: "arc", lap: "60" };

const HEX = /^#[0-9a-f]{6}$/i;

/** A style with every field valid, filling gaps from the defaults. Unknown or malformed values fall back. */
export function sanitize(raw) {
  const s = raw && typeof raw === "object" ? raw : {};
  const pick = (value, allowed, fallback) => (typeof value === "string" && Object.hasOwn(allowed, value) ? value : fallback);
  return {
    skin: pick(s.skin, SKINS, DEFAULT_STYLE.skin),
    face: pick(s.face, FACES, DEFAULT_STYLE.face),
    theme: pick(s.theme, THEMES, DEFAULT_STYLE.theme),
    color: typeof s.color === "string" && HEX.test(s.color) ? s.color.toLowerCase() : "",
    font: pick(s.font, FONTS, DEFAULT_STYLE.font),
    background: pick(s.background, BACKGROUNDS, DEFAULT_STYLE.background),
    statusTint: typeof s.statusTint === "boolean" ? s.statusTint : DEFAULT_STYLE.statusTint,
    anim: pick(s.anim, ANIMS, DEFAULT_STYLE.anim),
    lap: pick(s.lap, LAPS, DEFAULT_STYLE.lap),
  };
}

/** The accent colour: a custom pick wins over the preset. */
export const accent = (style) => (style.color || THEMES[style.theme].color);

/** CSS custom properties for a style, ready to assign to the node's root element. */
export function cssVars(style) {
  const font = FONTS[style.font];
  return {
    "--rt-color": accent(style),
    "--rt-color-2": secondColor(accent(style)),
    "--rt-font": font.css,
    "--rt-weight": String(font.weight),
    "--rt-scale": String(font.scale),
    "--rt-bg": BACKGROUNDS[style.background].css,
  };
}

/** Width : height of the node for a face. */
export const aspectOf = (face, digitalRatio) => (face === "digital" ? digitalRatio : 1);

/** The colour a second lap is drawn in: the accent with its hue turned 140 degrees, same lightness and saturation. */
export function secondColor(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  let h = 0;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (d !== 0) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
  }
  h = (h * 60 + 140 + 360) % 360;
  const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = l - c / 2;
  const [r1, g1, b1] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  const to = (v) => Math.round((v + m) * 255).toString(16).padStart(2, "0");
  return `#${to(r1)}${to(g1)}${to(b1)}`;
}

/** Length of one lap in ms: a fixed number of seconds, or the average run when known (a minute until there is history). */
export function lapMsFor(lap, avgMs) {
  if (lap === "avg") return avgMs > 0 ? avgMs : 60000;
  return (Number(lap) || 60) * 1000;
}

/**
 * Where the ring is: `lap` is how many full laps are done and `frac` how far round the current one is (0..1).
 * Each new lap starts over in the other colour while the finished lap stays drawn behind it. At rest the ring is full.
 */
export function ringState({ running, elapsedMs, lapMs }) {
  if (!running) return { lap: 0, frac: 1, rest: true };
  const laps = Math.max(0, elapsedMs) / Math.max(1, lapMs);
  return { lap: Math.floor(laps), frac: laps - Math.floor(laps), rest: false };
}

/**
 * Hand angles in degrees for an analog stopwatch face: the big hand goes round once a minute, the small dial's hand
 * once every 30 minutes. A new second hand position every call, so it sweeps smoothly rather than ticking.
 */
export function handAngles(elapsedMs) {
  const ms = Math.max(0, Number(elapsedMs) || 0);
  return { second: (ms % 60000) / 60000 * 360, minute: (ms % 1800000) / 1800000 * 360 };
}
