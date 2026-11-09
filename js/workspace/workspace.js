// Registers the Workflows and Documentation panels: floating, non-blocking, remembered between sessions. They open
// from buttons in ComfyUI's top bar, keyboard shortcuts, commands and the canvas right-click menu. A floating
// launcher dock is available as an opt-in setting for frontends without top-bar extension buttons.
import { app } from "../../../scripts/app.js";
import { h } from "../utility_core/_shared.js";
import { createDocumentation } from "./docs.js";
import { createDock } from "./panel.js";
import { createWorkflowBrowser } from "./workflows.js";

const SET_DOCK = "JezzWTF.Workspace.Dock";
let workflows;
let docs;
let dock;

const refreshDock = () => dock?.refresh();
const openWorkflows = () => { workflows.toggle(); refreshDock(); };
const openDocs = (topic) => { docs.toggle(typeof topic === "string" ? topic : undefined); refreshDock(); };

const tools = [
  { id: "JezzWTF.Workflows.Toggle", label: "JezzWTF Workflows", run: openWorkflows, key: "w" },
  { id: "JezzWTF.Documentation.Toggle", label: "JezzWTF Documentation", run: () => openDocs(), key: "d" },
];

function boot() {
  workflows ??= createWorkflowBrowser();
  docs ??= createDocumentation();
  for (const api of [workflows, docs]) {
    const { panel } = api;
    // keep the dock's pressed state in step with the panel however it was opened or closed
    new MutationObserver(refreshDock).observe(panel.root, { attributes: true, attributeFilter: ["hidden"] });
  }
  dock ??= createDock([
    { label: "Workflows", panel: workflows.panel, toggle: () => workflows.toggle(), hint: "Browse workflows and examples (Alt+Shift+W)" },
    { label: "Docs", panel: docs.panel, toggle: () => docs.toggle(), hint: "Help for every JezzWTF node (Alt+Shift+D)" },
  ]);
  refreshDock();
  // reopen what was open last time
  if (workflows.panel.wasOpen) workflows.open();
  if (docs.panel.wasOpen) docs.open();
}

// Other scripts (and docs links) can open a topic: window.JezzWTF.openDocs("run-timer").
window.JezzWTF = Object.assign(window.JezzWTF ?? {}, { openDocs: (t) => openDocs(t), openWorkflows: () => openWorkflows() });

app.registerExtension({
  name: "JezzWTF.Workspace",
  settings: [{
    id: SET_DOCK,
    name: "Show a floating Workflows and Docs launcher (the top bar buttons are always available)",
    type: "boolean",
    defaultValue: false,
    category: ["JezzWTF", "Windows", "Floating launcher"],
    onChange: (v) => dock?.setVisible(!!v),
  }],
  // Buttons in the top bar; the icons are lucide classes already compiled into the frontend.
  actionBarButtons: [
    { icon: "icon-[lucide--layout-grid]", label: "Workflows", tooltip: "JezzWTF Workflows (Alt+Shift+W)", onClick: () => openWorkflows() },
    { icon: "icon-[lucide--book-open]", label: "Docs", tooltip: "JezzWTF Documentation (Alt+Shift+D)", onClick: () => openDocs() },
  ],
  setup() {
    document.head.append(h("link", { rel: "stylesheet", href: new URL("./workspace.css", import.meta.url).href }));
    boot();
    let show = false;
    try { show = !!app.ui.settings.getSettingValue(SET_DOCK, false); } catch { /* old frontend: default */ }
    dock?.setVisible(show);
  },
  commands: tools.map(({ id, label, run }) => ({ id, label, function: run })),
  keybindings: tools.map(({ id, key }) => ({ combo: { key, alt: true, shift: true }, commandId: id })),
  getCanvasMenuItems: () => tools.map(({ label, run }) => ({ content: label, callback: () => run() })),
});
