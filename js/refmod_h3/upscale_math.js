// Pure same-scale upscale target search. Mirrors nodes/refmod_h3/upscale_picker.py line by line
// (the tests run both on random inputs and compare). No imports: loadable in node and the browser.

export const MODES = ["Scale factor", "Target megapixels"];
export const SCALE_LABELS = ["1.5x", "2x", "2.5x", "3x", "4x", "Custom"];
const MIN_SCALE = 1.0;
const MAX_SCALE = 4.0;
const EPS = 1e-9;

export function labelScale(label) {
    const m = /^\s*(\d+(\.\d+)?)\s*[x×]/.exec(String(label));
    return m ? parseFloat(m[1]) : 2.0;
}

export function grid(multiple) {
    return Math.max(16, Math.ceil(multiple / 16) * 16);
}

const snap = (v, m) => Math.max(m, Math.floor(v / m + 0.5) * m);

export function requestedScale(w, h, mode, scale, customScale, megapixels) {
    let s;
    if (mode === "Target megapixels") {
        const mp = Math.min(16.0, Math.max(0.05, Number(megapixels)));
        s = Math.sqrt(mp * 1024 * 1024 / (w * h));
    } else {
        s = scale === "Custom" ? Number(customScale) : labelScale(scale);
    }
    let note = "";
    if (s < MIN_SCALE) {
        if (mode === "Target megapixels") note = "no upscale (target <= source)";
        s = MIN_SCALE;
    } else if (s > MAX_SCALE) {
        note = "capped at 4x";
        s = MAX_SCALE;
    }
    return [s, note];
}

export function candidates(w, h, s, m) {
    const out = [[snap(w * s, m), snap(h * s, m)]];
    const lo = Math.max(1, Math.floor(0.8 * w * s / m));
    const hi = Math.ceil(1.2 * w * s / m) + 1;
    for (let k = lo; k <= hi; k++) {
        const cw = k * m;
        const rows = Math.max(1, Math.floor(cw * h / w / m));
        out.push([cw, rows * m]);
        out.push([cw, (rows + 1) * m]);
    }
    return out;
}

export function choose(w, h, s, m) {
    let best = null;
    for (const [cw, ch] of candidates(w, h, s, m)) {
        const sw = cw / w, sh = ch / h;
        if (sw < 1 - EPS || sh < 1 - EPS) continue;
        const eff = (sw + sh) / 2;
        if (eff > MAX_SCALE) continue;
        const cost = 20 * Math.abs(sw - sh) / eff + Math.abs(eff / s - 1);
        if (best === null || cost < best[0] || (cost === best[0] && cw < best[1])) best = [cost, cw, ch];
    }
    if (best === null) return [Math.ceil(w * s / m) * m, Math.ceil(h * s / m) * m];
    return [best[1], best[2]];
}

export function pickTarget(width, height, mode = "Scale factor", scale = "2x", customScale = 2.0,
                           targetMegapixels = 0.5, multiple = 16) {
    const w = Math.max(1, Math.trunc(width)), h = Math.max(1, Math.trunc(height));
    const m = grid(Math.trunc(multiple));
    const [s, note] = requestedScale(w, h, mode, scale, customScale, targetMegapixels);
    const [tw, th] = choose(w, h, s, m);
    const sw = tw / w, sh = th / h;
    const eff = (sw + sh) / 2;
    const mismatch = Math.abs(sw - sh) / eff;
    const match = mismatch < 1e-6 ? "exact" : `uneven ${(mismatch * 100).toFixed(1)}%`;
    let info = `${w}x${h} -> ${tw}x${th} | ${sw.toFixed(3)}x by ${sh.toFixed(3)}x (${match}) | upscaler scale ${eff.toFixed(3)}x`
        + ` | ${(w * h / 1048576).toFixed(2)} -> ${(tw * th / 1048576).toFixed(2)} MP`;
    if (note) info += ` | ${note}`;
    return { width: tw, height: th, scale: eff, scaleW: sw, scaleH: sh, requested: s, note, mismatch, info };
}
