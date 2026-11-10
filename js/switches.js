// Switch, Route and Multi Switch: colour the slots of the side that is active, and (Multi Switch) add and remove pairs.
// The Python side declares every slot, so the server validates and runs only the chosen side; this file just shows
// as many pairs as the node is using.
import { app } from "../../scripts/app.js";

const MAX_PAIRS = 6;
const DEFAULT_PAIRS = 2;
const COLOR = { false: "#7ab4f5", true: "#f5a742", off: "#4a4a4a" };

const sideOf = (input) => (/^(?:if_)?(true|false)/.exec(input?.name ?? "") ?? [])[1];
const switchWidget = (node) => node.widgets?.find((w) => w.name === "switch");
const switchValue = (node) => !!switchWidget(node)?.value;

/** The slot dot of the active side takes its colour; the other side goes grey. */
function paint(node) {
  const active = switchValue(node) ? "true" : "false";
  for (const slot of [...(node.inputs ?? []), ...(node.outputs ?? [])]) {
    const side = sideOf(slot);
    if (!side) continue;
    const color = side === active ? COLOR[side] : COLOR.off;
    slot.color_on = color;
    slot.color_off = color;
  }
  node.setDirtyCanvas?.(true, false);
}

function watchSwitch(node) {
  const w = switchWidget(node);
  if (!w || w._jwtfWatched) return;
  w._jwtfWatched = true;
  const original = w.callback;
  w.callback = function (...args) {
    const r = original?.apply(this, args);
    paint(node);
    return r;
  };
}

// ----------------------------------------------------------------------------------------------- Multi Switch

const pairNumbers = (node) => (node.inputs ?? []).map((i) => /^true_(\d+)$/.exec(i.name ?? "")?.[1]).filter(Boolean).map(Number);
const pairCount = (node) => Math.max(0, ...pairNumbers(node));

function removeInput(node, name) {
  const at = node.inputs?.findIndex((s) => s.name === name) ?? -1;
  if (at < 0) return;
  if (node.inputs[at].link != null) node.graph?.removeLink(node.inputs[at].link);
  node.removeInput(at);
}

/** Output N belongs to pair N, by position (the server names them by display name, which is not stable). */
function removeOutput(node, pair) {
  if (pair - 1 >= (node.outputs?.length ?? 0)) return;
  node.disconnectOutput?.(pair - 1);
  node.removeOutput(pair - 1);
}

function setPairs(node, count) {
  const wanted = Math.max(1, Math.min(MAX_PAIRS, count));
  for (let n = pairCount(node); n > wanted; n--) {
    removeInput(node, `true_${n}`);
    removeInput(node, `false_${n}`);
    removeOutput(node, n);
  }
  for (let n = pairCount(node) + 1; n <= wanted; n++) {
    node.addInput(`false_${n}`, "*", { label: "false" });
    node.addInput(`true_${n}`, "*", { label: "true" });
    node.addOutput(`output_${n}`, "*", { label: `output ${n}` });
  }
  paint(node);
  node.setSize(node.computeSize());
  node.setDirtyCanvas?.(true, true);
}

/** A faint dashed line between the pairs, so each pair reads as one unit. */
function drawDividers(node, ctx) {
  const pairs = pairCount(node);
  if (pairs <= 1) return;
  const slotH = LiteGraph.NODE_SLOT_HEIGHT ?? 20;
  const first = (node.inputs?.findIndex((i) => /^false_/.test(i.name ?? "")) ?? 1) + 0;
  const top = (LiteGraph.NODE_TITLE_HEIGHT ?? 30) + (first >= 0 ? first : 1) * slotH;
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.setLineDash([3, 5]);
  for (let i = 1; i < pairs; i++) {
    const y = top + i * 2 * slotH - 2;
    ctx.beginPath();
    ctx.moveTo(6, y);
    ctx.lineTo(node.size[0] - 6, y);
    ctx.stroke();
  }
  ctx.restore();
}

app.registerExtension({
  name: "JezzWTF.Switches",

  async nodeCreated(node) {
    if (node.comfyClass === "JWTFSwitch" || node.comfyClass === "JWTFRoute") {
      watchSwitch(node);
      paint(node);
      return;
    }
    if (node.comfyClass !== "MultiSwitch") return;

    watchSwitch(node);
    setPairs(node, DEFAULT_PAIRS); // the server declares all six pairs; a new node starts with two
    node.addWidget("button", "+ Add pair", null, () => setPairs(node, pairCount(node) + 1));
    node.addWidget("button", "− Remove pair", null, () => setPairs(node, pairCount(node) - 1));

    const drawn = node.onDrawForeground;
    node.onDrawForeground = function (ctx, ...rest) {
      drawn?.call(this, ctx, ...rest);
      drawDividers(this, ctx);
    };
    const configured = node.onConfigure;
    node.onConfigure = function (...args) {
      const r = configured?.apply(this, args);
      watchSwitch(this);
      paint(this);
      return r;
    };
  },

  loadedGraphNode(node) {
    if (["JWTFSwitch", "JWTFRoute", "MultiSwitch"].includes(node.comfyClass)) {
      watchSwitch(node);
      paint(node);
    }
  },
});
