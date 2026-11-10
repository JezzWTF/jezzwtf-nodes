// Paste Stack backdrop: a slowly drifting, domain-warped noise in near-black with teal and violet tints, a soft glow
// that follows the pointer, a ripple from the last click or drop, and a brightness that rises as the stack fills.
// Purely decorative: any failure leaves the CSS gradient that is always underneath. WebGL2 only.

const VERT = `#version 300 es
void main() {
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const FRAG = `#version 300 es
precision mediump float;
uniform vec2 u_res;
uniform float u_time;
uniform vec2 u_pointer;
uniform float u_glow;
uniform vec3 u_ripple;
uniform float u_fill;
out vec4 outColor;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 4; i++) { v += a * noise(p); p = p * 2.03 + 7.3; a *= 0.5; }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_res;
  float aspect = u_res.x / u_res.y;
  vec2 p = vec2(uv.x * aspect, uv.y) * 2.2;
  float t = u_time * 0.05;
  vec2 q = vec2(fbm(p + t), fbm(p + vec2(5.2, 1.3) - t));
  float n = fbm(p + 2.4 * q + t * 0.6);

  vec3 teal = vec3(0.10, 0.62, 0.55);
  vec3 violet = vec3(0.44, 0.26, 0.86);
  vec3 col = mix(teal, violet, smoothstep(0.25, 0.8, q.x * 0.6 + n * 0.5));
  float body = smoothstep(0.30, 0.85, n);
  vec3 c = vec3(0.012, 0.016, 0.022) + col * body * (0.10 + 0.10 * u_fill);

  vec2 d = (uv - u_pointer) * vec2(aspect, 1.0);
  c += teal * exp(-dot(d, d) * 4.0) * u_glow * 0.055;

  if (u_ripple.z >= 0.0 && u_ripple.z < 1.6) {
    vec2 r = (uv - u_ripple.xy) * vec2(aspect, 1.0);
    float fade = 1.0 - u_ripple.z / 1.6;
    float ring = exp(-pow((length(r) - u_ripple.z * 0.4) * 6.0, 2.0)) * fade * fade;
    c += teal * ring * 0.09;
  }

  vec2 v = uv - 0.5;
  c *= 1.0 - dot(v, v) * 0.9;
  outColor = vec4(c, 1.0);
}`;

const RENDER_SCALE = 0.5;
const FRAME_MS = 1000 / 30;

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || "shader failed");
  return shader;
}

/**
 * Starts the backdrop on `canvas`. Returns null when WebGL2 or the shader is unavailable.
 * `host` supplies the size; `getFill()` returns 0..1 for how full the stack is.
 */
export function createBackdrop(canvas, host, getFill) {
  let gl;
  try {
    gl = canvas.getContext("webgl2", { alpha: false, antialias: false, powerPreference: "low-power" });
    if (!gl) return null;
  } catch {
    return null;
  }
  let program;
  try {
    program = gl.createProgram();
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || "link failed");
  } catch (err) {
    console.warn("Paste Stack backdrop disabled:", err);
    return null;
  }
  gl.useProgram(program);
  const loc = (n) => gl.getUniformLocation(program, n);
  const u = { res: loc("u_res"), time: loc("u_time"), pointer: loc("u_pointer"), glow: loc("u_glow"), ripple: loc("u_ripple"), fill: loc("u_fill") };
  const vao = gl.createVertexArray();
  gl.bindVertexArray(vao);

  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  let active = false;
  let wanted = false;
  let lost = false;
  let raf = 0;
  let last = 0;
  let glow = 0;
  let glowTarget = 0;
  const pointer = [0.5, 0.5];
  let rippleAt = -1e9;
  let rippleXY = [0.5, 0.5];
  const start = performance.now();
  let frozen = 0;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(2, Math.round((host.clientWidth || 300) * dpr * RENDER_SCALE));
    const h = Math.max(2, Math.round((host.clientHeight || 300) * dpr * RENDER_SCALE));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
  }

  function draw(now) {
    if (lost) return;
    resize();
    const seconds = reduced?.matches ? frozen : (now - start) / 1000;
    glow += (glowTarget - glow) * 0.12;
    const age = (now - rippleAt) / 1000;
    gl.uniform2f(u.res, canvas.width, canvas.height);
    gl.uniform1f(u.time, seconds);
    gl.uniform2f(u.pointer, pointer[0], pointer[1]);
    gl.uniform1f(u.glow, glow);
    gl.uniform3f(u.ripple, rippleXY[0], rippleXY[1], reduced?.matches ? -1 : age);
    gl.uniform1f(u.fill, Math.max(0, Math.min(1, getFill())));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  function loop(now) {
    raf = 0;
    if (!active || lost) return;
    if (now - last >= FRAME_MS) { last = now; draw(now); }
    raf = requestAnimationFrame(loop);
  }

  const api = {
    /** Run only while the panel is on screen; with reduced motion it draws a single still frame instead. */
    setActive(on) {
      wanted = !!on;
      active = wanted && !lost && !document.hidden;
      canvas.dataset.on = active ? "1" : "0";
      if (!active) { if (raf) cancelAnimationFrame(raf); raf = 0; return; }
      if (reduced?.matches) { draw(performance.now()); return; }
      if (!raf) raf = requestAnimationFrame(loop);
    },
    /** Pointer position over the host, in CSS pixels relative to its top-left; null when it leaves. */
    point(x, y) {
      if (x === null) { glowTarget = 0; return; }
      const w = host.clientWidth || 1, h = host.clientHeight || 1;
      pointer[0] = Math.max(0, Math.min(1, x / w));
      pointer[1] = Math.max(0, Math.min(1, 1 - y / h));
      glowTarget = 1;
      if (active && reduced?.matches) draw(performance.now());
    },
    /** A click, paste or drop: a ring spreads from there. */
    ripple(x, y) {
      const w = host.clientWidth || 1, h = host.clientHeight || 1;
      rippleXY = [Math.max(0, Math.min(1, x / w)), Math.max(0, Math.min(1, 1 - y / h))];
      rippleAt = performance.now();
      if (active && reduced?.matches) draw(rippleAt);
    },
    redraw() { if (active && reduced?.matches) draw(performance.now()); },
    get ok() { return !lost; },
    dispose() {
      active = false;
      if (raf) cancelAnimationFrame(raf);
      canvas.removeEventListener("webglcontextlost", onLost);
      document.removeEventListener("visibilitychange", onVisible);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    },
  };
  const onLost = (e) => { e.preventDefault(); lost = true; active = false; canvas.dataset.on = "0"; };
  const onVisible = () => { if (document.hidden) { if (raf) cancelAnimationFrame(raf); raf = 0; } else if (wanted) api.setActive(true); };
  canvas.addEventListener("webglcontextlost", onLost);
  document.addEventListener("visibilitychange", onVisible);
  return api;
}
