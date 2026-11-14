"""Browser smoke checks for the actual editor modules, hosted against a simulated ComfyUI API.

Requires Pillow, Playwright and its Chromium browser. Run from any directory:
    python tools/check_image_tools_browser.py [screenshot_directory]
"""

from __future__ import annotations
import json, math, sys, tempfile, threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from email.parser import BytesParser
from email.policy import default
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FILES = Path(tempfile.mkdtemp(prefix="jwtf-image-ui-"))
OUT = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path(tempfile.mkdtemp(prefix="jwtf-browser-results-"))
)
OUT.mkdir(parents=True, exist_ok=True)
for name, changed in [("a.png", False), ("b.png", True)]:
    image = Image.new("RGB", (720, 480), "#29414d")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 300, 720, 480), fill="#526456")
    draw.ellipse((420, 65, 565, 210), fill="#b9c6b6" if not changed else "#d6b18b")
    draw.polygon([(0, 360), (270, 135), (510, 360)], fill="#798e86")
    draw.polygon([(300, 385), (525, 195), (720, 385)], fill="#405650")
    image.save(FILES / name)
a, b = Image.open(FILES / "a.png"), Image.open(FILES / "b.png")
from PIL import ImageChops

ImageChops.difference(a, b).save(FILES / "diff.png")
Image.new("RGB", (720, 480), "black").save(FILES / "mask.png")
HTML = """<!doctype html><meta charset="utf-8"><title>Image tools browser checks</title>
<style>body{margin:28px;background:#15171b;color:#dce0e5;font:14px system-ui}main{display:grid;grid-template-columns:640px 640px;gap:24px}h2{font-size:16px;font-weight:500}button,select,input{background:#30363e;color:#dce0e5;border:1px solid #58616b;border-radius:4px;padding:4px}button{cursor:pointer}section{min-width:0}audio{width:100%}</style>
<h1 style="font-size:22px;font-weight:500">JezzWTF · image and audio tools</h1><main><section id="comparison"><h2>Image Compare</h2></section><section id="mask"><h2>Mask Editor</h2></section><section id="wave"><h2>Audio waveform trim</h2></section></main>
<script type="module">
import {app} from '/scripts/app.js';
import '/extensions/jezzwtf/utility_core/image_compare.js';
import '/extensions/jezzwtf/utility_core/mask_editor.js';
import {createWaveform} from '/extensions/jezzwtf/audio_tools/waveform.js';
window.app=app;
for(const extension of app.extensions) extension.setup?.();
function makeNode(type,host,widgets=[]){
 class Node {constructor(){this.widgets=widgets;this.size=[640,520];this.pos=[0,0];this.properties={};this.graph={change(){}};this.onNodeCreated?.()}
 addDOMWidget(name,type,element){document.querySelector(host).append(element)} computeSize(){return this.size}setSize(size){this.size=size}setDirtyCanvas(){} }
 for(const extension of app.extensions)extension.beforeRegisterNodeDef?.(Node,{name:type});return new Node();
}
const descriptor=filename=>({filename,type:'temp',subfolder:''});
window.compare=makeNode('JWTFImageCompare','#comparison');
compare.onExecuted({jwtf_compare:[{frames:[{a:descriptor('a.png'),b:descriptor('b.png'),difference:descriptor('diff.png')}],metrics:[{mae:0.0123,psnr_db:28.6}],total:1}]});
window.mask=makeNode('JWTFMaskEditor','#mask',[{name:'painted_mask',value:'',computeSize(){return [0,0]}}]);
mask.onExecuted({jwtf_mask_editor:[{background:descriptor('a.png'),mask:descriptor('mask.png')}]});
const player=document.createElement('audio');player.controls=true;
window.audioNode={widgets:[{name:'start',value:0},{name:'length',value:0}],graph:{change(){}},setDirtyCanvas(){}};
const waveform=createWaveform(audioNode,player);document.querySelector('#wave').append(waveform.body,player);waveform.load('tone.wav');
window.ready=true;
</script>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, data, kind="text/javascript"):
        if isinstance(data, str):
            data = data.encode()
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.send(HTML, "text/html")
        if parsed.path == "/scripts/app.js":
            return self.send(
                "export const app={extensions:[],registerExtension(e){this.extensions.push(e)},async graphToPrompt(){return {ok:true}}};"
            )
        if parsed.path == "/scripts/api.js":
            return self.send(
                "export const api={apiURL:url=>url,fetchApi:(url,options)=>fetch(url,options)};"
            )
        if parsed.path.startswith("/extensions/jezzwtf/"):
            path = (
                ROOT / "js" / parsed.path.removeprefix("/extensions/jezzwtf/")
            ).resolve()
            if not path.is_relative_to((ROOT / "js").resolve()):
                return self.send_error(403)
            return self.send(path.read_bytes())
        if parsed.path == "/view":
            filename = parse_qs(parsed.query)["filename"][0]
            if Path(filename).name != filename:
                return self.send_error(403)
            return self.send((FILES / filename).read_bytes(), "image/png")
        if parsed.path == "/jezzwtf/audio/waveform":
            return self.send(
                json.dumps(
                    {
                        "duration": 10,
                        "peaks": [
                            0.15 + abs(math.sin(i * 0.13)) * 0.75 for i in range(200)
                        ],
                    }
                ),
                "application/json",
            )
        self.send_error(404)

    def do_POST(self):
        data = self.rfile.read(int(self.headers["Content-Length"]))
        message = BytesParser(policy=default).parsebytes(
            (
                "Content-Type: "
                + self.headers["Content-Type"]
                + "\r\nMIME-Version: 1.0\r\n\r\n"
            ).encode()
            + data
        )
        for part in message.iter_parts():
            if part.get_filename():
                name = Path(part.get_filename()).name
                (FILES / name).write_bytes(part.get_payload(decode=True))
                return self.send(
                    json.dumps(
                        {"name": name, "subfolder": "jezzwtf_masks", "type": "input"}
                    ),
                    "application/json",
                )
        self.send_error(400)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1360, "height": 950}, device_scale_factor=1
        )
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{server.server_port}/")
        page.wait_for_function("window.ready===true")
        page.get_by_text("MAE 0.01230", exact=False).wait_for()
        page.get_by_text("Paint white to select ·", exact=False).wait_for()
        page.get_by_text("10.00s selected", exact=False).wait_for()
        for mode in ["Difference", "Blend", "Toggle", "Wipe"]:
            page.get_by_label("Comparison mode").select_option(mode)
        assert (
            page.get_by_label("Comparison mode")
            .locator('option[value="Mask"]')
            .is_disabled()
        )
        box = page.locator("#mask canvas").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.35, box["y"] + box["height"] * 0.5)
        page.mouse.down()
        page.mouse.move(
            box["x"] + box["width"] * 0.65, box["y"] + box["height"] * 0.5, steps=12
        )
        page.mouse.up()
        page.evaluate("app.graphToPrompt()")
        saved = page.evaluate('mask.widgets.find(w=>w.name==="painted_mask").value')
        assert saved.startswith("jezzwtf_masks/")
        with Image.open(FILES / Path(saved).name) as painted:
            assert (
                painted.getpixel((360, 240))[0] > 240
                and painted.getpixel((20, 20))[0] == 0
            )
        page.get_by_role("button", name="Undo", exact=True).click()
        page.evaluate("app.graphToPrompt()")
        with Image.open(FILES / Path(saved).name) as painted:
            assert painted.getpixel((360, 240))[0] == 0
        page.get_by_role("button", name="Fill", exact=True).click()
        page.evaluate("app.graphToPrompt()")
        with Image.open(FILES / Path(saved).name) as painted:
            assert painted.getpixel((360, 240))[0] == 255
        page.get_by_role("button", name="Clear", exact=True).click()
        page.evaluate("app.graphToPrompt()")
        box = page.locator("#mask canvas").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.35, box["y"] + box["height"] * 0.5)
        page.mouse.down()
        page.mouse.move(
            box["x"] + box["width"] * 0.65, box["y"] + box["height"] * 0.5, steps=12
        )
        page.mouse.up()
        page.evaluate("app.graphToPrompt()")
        wavebox = page.locator("#wave canvas").bounding_box()
        page.mouse.move(wavebox["x"] + 2, wavebox["y"] + 30)
        page.mouse.down()
        page.mouse.move(
            wavebox["x"] + wavebox["width"] * 0.2, wavebox["y"] + 30, steps=8
        )
        page.mouse.up()
        assert 1.8 < page.evaluate("audioNode.widgets[0].value") < 2.2
        page.screenshot(path=str(OUT / "image-tools-browser.png"), full_page=True)
        page.route(
            "**/upload/image",
            lambda route: route.fulfill(status=500, body="simulated upload failure"),
        )
        page.get_by_role("button", name="Fill", exact=True).click()
        rejected = page.evaluate("app.graphToPrompt().then(()=>false,()=>true)")
        assert rejected, "Failed mask uploads must prevent queuing stale masks"
        page.get_by_role("button", name="Use input mask", exact=True).click()
        page.get_by_text("Incoming mask selected", exact=False).wait_for()
        assert (
            page.evaluate('mask.widgets.find(w=>w.name==="painted_mask").value') == ""
        )
        assert page.evaluate("app.graphToPrompt().then(()=>true)")
        assert not errors, errors
        print(
            json.dumps(
                {
                    "browser_errors": errors,
                    "mask_saved": True,
                    "undo_and_fill": True,
                    "waveform_drag": True,
                    "failed_save_blocks_queue": True,
                    "reset_to_input": True,
                    "screenshot": str(OUT / "image-tools-browser.png"),
                }
            )
        )
        browser.close()
finally:
    server.shutdown()
