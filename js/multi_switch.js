import { app } from "../../scripts/app.js";

const MAX_SLOTS = 6;
const MIN_SLOTS = 1;

// Slot dot colours — false side blue, true side orange, inactive grey
const COLOR_FALSE  = "#7ab4f5";
const COLOR_TRUE   = "#f5a742";
const COLOR_DIM    = "#4a4a4a";

app.registerExtension({
    name: "JezzWTF.MultiSwitch",

    async nodeCreated(node) {
        if (node.comfyClass !== "MultiSwitch") return;

        function getNumSlots() {
            return node.widgets?.find(w => w.name === "num_slots")?.value ?? 2;
        }
        function setNumSlots(n) {
            const w = node.widgets?.find(w => w.name === "num_slots");
            if (w) w.value = n;
        }
        function getSwitchValue() {
            return node.widgets?.find(w => w.name === "switch")?.value ?? false;
        }

        // Refresh slot dot colours based on current switch state
        function updateColors() {
            const isTrue = getSwitchValue();
            for (let i = 1; i < (node.inputs?.length ?? 0); i++) {
                const inp = node.inputs[i];
                const isFalseSlot = inp.name?.startsWith("false");
                const active = isFalseSlot ? !isTrue : isTrue;
                const col = active ? (isFalseSlot ? COLOR_FALSE : COLOR_TRUE) : COLOR_DIM;
                inp.color_on  = col;
                inp.color_off = col;
            }
            node.setDirtyCanvas(true, false);
        }

        // Add/remove input pairs and output slots together
        function syncSlots(count) {
            // Outputs
            const curOut = node.outputs?.length ?? 0;
            for (let i = curOut - 1; i >= count; i--) {
                for (const id of [...(node.outputs[i]?.links ?? [])]) node.graph.removeLink(id);
                node.removeOutput(i);
            }
            for (let i = curOut; i < count; i++) {
                node.addOutput(`output_${i + 1}`, "*");
            }

            // Inputs (index 0 = switch widget area; slots start at 1)
            const target = 1 + count * 2;
            const curIn  = node.inputs?.length ?? 0;
            for (let i = curIn - 1; i >= target; i--) {
                if (node.inputs[i]?.link != null) node.graph.removeLink(node.inputs[i].link);
                node.removeInput(i);
            }
            for (let i = curIn; i < target; i++) {
                const pair    = Math.ceil(i / 2);
                const isFalse = (i % 2 === 1);
                node.addInput(`${isFalse ? "false" : "true"}_${pair}`, "*");
            }

            // Set clean display labels (strip _N suffix)
            for (let i = 1; i < (node.inputs?.length ?? 0); i++) {
                node.inputs[i].label = node.inputs[i].name?.startsWith("false") ? "false" : "true";
            }

            updateColors();
            node.setSize(node.computeSize());
        }

        // Watch the switch toggle and refresh colours immediately
        const switchWidget = node.widgets?.find(w => w.name === "switch");
        if (switchWidget) {
            const orig = switchWidget.callback;
            switchWidget.callback = function (...args) {
                orig?.call(this, ...args);
                updateColors();
            };
        }

        // Draw subtle dashed dividers between slot pairs
        const origFg = node.onDrawForeground?.bind(node);
        node.onDrawForeground = function (ctx) {
            origFg?.(ctx);
            const count = getNumSlots();
            if (count <= 1) return;

            const slotH  = LiteGraph.NODE_SLOT_HEIGHT ?? 20;
            const titleH = LiteGraph.NODE_TITLE_HEIGHT ?? 30;

            ctx.save();
            ctx.strokeStyle = "rgba(255,255,255,0.10)";
            ctx.lineWidth   = 1;
            ctx.setLineDash([3, 5]);

            for (let i = 1; i < count; i++) {
                const y = titleH + i * 2 * slotH;
                ctx.beginPath();
                ctx.moveTo(6, y);
                ctx.lineTo(this.size[0] - 6, y);
                ctx.stroke();
            }
            ctx.restore();
        };

        // Initialise
        syncSlots(getNumSlots());

        node.addWidget("button", "+ Add Slot", null, () => {
            const next = Math.min(getNumSlots() + 1, MAX_SLOTS);
            setNumSlots(next);
            syncSlots(next);
        });

        node.addWidget("button", "− Remove Slot", null, () => {
            const next = Math.max(getNumSlots() - 1, MIN_SLOTS);
            setNumSlots(next);
            syncSlots(next);
        });
    },
});
