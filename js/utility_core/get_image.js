import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";
import { chain, h, injectCss, viewUrl } from "./_shared.js";

// Get Image: two square thumbnails (image + mask) filled from the custom ui key.

const UI_KEY = "jezzwtf_get_image";

injectCss("jwtf-getimage", `
.jwtf-gi { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; height: 100%; box-sizing: border-box; padding: 4px; }
.jwtf-gi-box { position: relative; border: 1px dashed #3a3d46; border-radius: 8px; background: #111 center/contain no-repeat;
  min-height: 0; }
.jwtf-gi-box.filled { border-style: solid; border-color: #2c2e35; }
.jwtf-gi-box span { position: absolute; left: 6px; top: 4px; font: 600 10px system-ui; color: #aab; text-shadow: 0 1px 2px #000; }
`);

app.registerExtension({
    name: "JezzWTF.UtilityCore.GetImage",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "JWTFGetImage") return;
        chain(nodeType.prototype, "onNodeCreated", function () {
            const boxes = { image: h("div.jwtf-gi-box", {}, h("span", {}, "Image")), mask: h("div.jwtf-gi-box", {}, h("span", {}, "Mask")) };
            this._jwtfBoxes = boxes;
            this.addDOMWidget("jwtf_getimage", "jwtf_getimage", h("div.jwtf-gi", {}, boxes.image, boxes.mask),
                { serialize: false, getMinHeight: () => 170 });
            this.setSize([Math.max(this.size[0], 320), this.computeSize()[1]]);
        });
        chain(nodeType.prototype, "onExecuted", function (msg) {
            for (const entry of msg?.[UI_KEY] ?? []) {
                const box = this._jwtfBoxes?.[entry.kind];
                if (!box) continue;
                box.style.backgroundImage = `url("${viewUrl(api, entry)}")`;
                box.classList.add("filled");
            }
        });
    },
});
