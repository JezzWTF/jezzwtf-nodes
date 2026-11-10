// Pure RefMod curve math: easings and per-frame direction curves. Mirrors
// nodes/refmod_h3/curves.py (tests compare both). No imports: loadable in node and the browser.

export const DIRECTIONS = ["constant", "concept_at_start", "concept_at_end", "concept_at_middle", "concept_at_ends"];
const ALIASES = { decrease: "concept_at_start", increase: "concept_at_end" };

const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

export const EASINGS = {
    linear: (x) => x,
    ease: (x) => x * x * (3 - 2 * x),
    sigmoid: (x) => 1 / (1 + Math.exp(-12 * (x - 0.5))),
    tanh: (x) => 0.5 * (Math.tanh(8 * (x - 0.5)) + 1),
    quadratic: (x) => x * x,
    cubic: (x) => x * x * x,
    exponential: (x) => 2 ** x - 1,
    stair: (x) => Math.min(1, Math.floor(4 * x) / 3),
    elastic: (x) => {
        if (x <= 0) return 0;
        if (x >= 1) return 1;
        return 2 ** (-10 * x) * Math.sin((10 * x - 0.75) * (2 * Math.PI / 3)) + 1;
    },
    bump: (x) => 1 - Math.abs(2 * x - 1),
    dip: (x) => Math.abs(2 * x - 1),
};
export const SHAPES = Object.keys(EASINGS);

/** Per-frame curve for `t` frames, or null when the curve is flat (or t <= 1). */
export function directionCurve(direction, shape, value, t) {
    if (t <= 1) return null;
    const ease = EASINGS[shape];
    if (!ease) return null;
    const d = ALIASES[direction] ?? direction;
    const v = Number(value);
    const ys = Array.from({ length: t }, (_, i) => ease(i / (t - 1)));
    switch (d) {
        case "constant":
            if (shape === "linear") return v >= 1 ? null : new Array(t).fill(v);
            return ys.map((y) => clamp01(v * y));
        case "concept_at_end": return ys.map((y) => clamp01(v * y));
        case "concept_at_start": return ys.map((y) => clamp01(v * (1 - y)));
        case "concept_at_middle": return ys.map((y) => clamp01(v * (1 - Math.abs(2 * y - 1))));
        case "concept_at_ends": return ys.map((y) => clamp01(v * Math.abs(2 * y - 1)));
        default: return null;
    }
}
