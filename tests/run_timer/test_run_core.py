"""Runs the dependency-free frontend logic module (run_core.js) under Node and checks the results."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "js" / "run_timer" / "run_core.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_js(body: str) -> object:
    script = f"import * as L from {json.dumps(CORE.as_uri())};\nconst out = (() => {{ {body} }})();\nconsole.log(JSON.stringify(out));"
    done = subprocess.run([NODE or "node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_format_duration() -> None:
    out = run_js(
        """
        return [0, 850, 999, 1000, 12345, 59950, 60000, 125000, 3599999, 3723000, null, -5, NaN, 'x'].map(L.formatDuration);
        """
    )
    assert out == ["0 ms", "850 ms", "999 ms", "1.0s", "12.3s", "59.9s", "1m 00s", "2m 05s", "59m 59s", "1h 02m 03s", "--", "--", "--", "--"]


def test_format_clock_and_chip() -> None:
    out = run_js(
        """
        return { clock: [0, 99, 100, 12345, 59999, 60000, 3723456, null, -1].map(L.formatClock),
                 chip: [0, 12999, 125000, 3723000, null].map(L.formatChip) };
        """
    )
    assert out == {
        "clock": ["00:00.0", "00:00.0", "00:00.1", "00:12.3", "00:59.9", "01:00.0", "1:02:03.4", "00:00.0", "00:00.0"],
        "chip": ["0s", "12s", "2:05", "1:02:03", "0s"],
    }


def test_node_indicators_switch_at_elapsed_second_boundaries() -> None:
    node_module = CORE.with_name("run_timer.js").as_uri()
    out = run_js(
        f"""
        const {{ readFileSync }} = process.getBuiltinModule('node:fs');
        const {{ runInNewContext }} = process.getBuiltinModule('node:vm');
        const source = readFileSync(new URL({json.dumps(node_module)}), 'utf8').replace(/^import .*;$/gm, '');
        let elapsed = null, refresh, extension, root;
        const controller = {{
            primary: () => elapsed === null ? null : {{ elapsed }},
            subscribe: callback => {{ refresh = callback; }},
        }};
        runInNewContext(source, {{
            app: {{ registerExtension: value => {{ extension = value; }} }},
            window: {{ __jwtfRunTimerShared: {{ controller, panel: {{}} }} }},
            document: (() => {{
                const make = () => ({{
                    dataset: {{}}, append() {{}}, setAttribute() {{}}, addEventListener() {{}}, insertBefore() {{}},
                    style: {{ setProperty() {{}} }}, querySelector() {{ return null; }},
                    classList: {{ add() {{}}, toggle(_name, off) {{ this.off = off; }} }},
                }});
                return {{ createElement: make, createElementNS: make }};
            }})(),
            ensureStylesheet() {{}}, nodeSummary: () => ({{ count: 0 }}), AbortController,
            sanitize: () => ({{ face: 'digital', statusTint: true }}), cssVars: () => ({{}}), aspectOf: () => 2,
            ringState: () => ({{ lap: 0, frac: 0 }}), lapMsFor: () => 60000, ANIMS: {{}}, LAPS: {{}}, accent: () => '#fff', FACES: {{}}, SKINS: {{}}, handAngles: () => ({{ second: 0, minute: 0 }}), FONTS: {{}}, THEMES: {{}}, BACKGROUNDS: {{}},
        }});
        class Timer {{
            size = [340, 150];
            computeSize() {{ return this.size; }}
            setSize() {{}}
            addDOMWidget(_name, _type, element) {{ root = element; }}
        }}
        extension.beforeRegisterNodeDef(Timer, {{ name: 'JWTFRunTimer' }});
        new Timer().onNodeCreated();
        return [0, 999, 1000, 1999, 2000, 3599999, 3600000, null].map(value => {{
            elapsed = value;
            refresh('tick');
            return root.classList.off;
        }});
        """
    )
    assert out == [False, False, True, True, False, True, False, False]


def test_time_ago() -> None:
    out = run_js("return [0, 4000, 12000, 59000, 61000, 3600000, 7300000, 90000000, -9000].map((d) => L.timeAgo(1000000 - d, 1000000));")
    assert out == ["just now", "just now", "12s ago", "59s ago", "1m ago", "1h ago", "2h ago", "1d ago", "just now"]


def test_stats_average_median_best_worst() -> None:
    out = run_js(
        """
        const r = (ms, status = 'ok') => ({ duration_ms: ms, status });
        return {
          odd: L.computeStats([r(30), r(10), r(20)]),
          even: L.computeStats([r(10), r(20), r(30), r(100)]),
          none: L.computeStats([]),
          skipsUnknown: L.computeStats([r(10), r(null, 'unknown'), r(50, 'unknown'), r(30, 'error')]),
        };
        """
    )
    assert isinstance(out, dict)
    assert out["odd"] == {"count": 3, "timed": 3, "avg": 20, "median": 20, "best": 10, "worst": 30, "total": 60}
    assert out["even"] == {"count": 4, "timed": 4, "avg": 40, "median": 25, "best": 10, "worst": 100, "total": 160}
    assert out["none"] == {"count": 0, "timed": 0, "avg": None, "median": None, "best": None, "worst": None, "total": 0}
    assert out["skipsUnknown"] == {"count": 4, "timed": 2, "avg": 20, "median": 20, "best": 10, "worst": 30, "total": 40}


def test_filters_and_node_summary() -> None:
    out = run_js(
        """
        const runs = [
          { id: 'a', label: 'hero', status: 'ok', duration_ms: 100, started_at: 1 },
          { id: 'b', label: 'hero', status: 'error', duration_ms: 5, started_at: 3 },
          { id: 'c', label: '', status: 'ok', duration_ms: 300, started_at: 2 },
          { id: 'd', label: 'hero', status: 'ok', duration_ms: 200, started_at: 0 },
        ];
        return {
          byLabel: L.filterRuns(runs, { label: 'hero' }).map((r) => r.id),
          unlabeled: L.filterRuns(runs, { label: '' }).map((r) => r.id),
          byStatus: L.filterRuns(runs, { status: 'ok' }).map((r) => r.id),
          both: L.filterRuns(runs, { label: 'hero', status: 'ok' }).map((r) => r.id),
          all: L.filterRuns(runs, { label: null, status: null }).length,
          labels: L.uniqueLabels(runs),
          named: L.nodeSummary(runs, 'hero'),
          anyLabel: L.nodeSummary(runs, ''),
          empty: L.nodeSummary([], 'x'),
        };
        """
    )
    assert isinstance(out, dict)
    assert out["byLabel"] == ["a", "b", "d"] and out["unlabeled"] == ["c"] and out["byStatus"] == ["a", "c", "d"]
    assert out["both"] == ["a", "d"] and out["all"] == 4 and out["labels"] == ["", "hero"]
    assert out["named"] == {"last": {"ms": 5, "status": "error"}, "avg": 150, "best": 100, "count": 2}
    assert out["anyLabel"] == {"last": {"ms": 5, "status": "error"}, "avg": 200, "best": 100, "count": 3}
    assert out["empty"] == {"last": None, "avg": None, "best": None, "count": 0}


def test_csv_export_escapes_and_defuses_formulas() -> None:
    out = run_js(
        """
        const csv = L.toCsv([{ id: 'x1', prompt_id: 'p', started_at: 1700000000000, duration_ms: 1500, status: 'ok',
          label: '=HYPERLINK("evil")', workflow: 'a,b "c"', node_count: 7, slowest: [{ title: 'KSampler', ms: 900 }], approx: true },
          { id: 'x2', prompt_id: 'q', started_at: 1700000000000, duration_ms: null, status: 'unknown', label: '', workflow: '', node_count: 0, slowest: [], approx: false }]);
        return csv;
        """
    )
    assert isinstance(out, str)
    lines = out.split("\r\n")
    assert lines[0].startswith("id,prompt_id,started_at,started_at_ms,duration_ms,duration,status,label")
    assert lines[1] == 'x1,p,2023-11-14T22:13:20.000Z,1700000000000,1500,1.5s,ok,"\'=HYPERLINK(""evil"")","a,b ""c""",7,KSampler=900ms,yes'
    assert lines[2] == "x2,q,2023-11-14T22:13:20.000Z,1700000000000,,,unknown,,,0,,no"
    assert lines[-1] == ""


def test_export_name() -> None:
    assert run_js("return L.exportName('csv', new Date(2026, 10, 9, 8, 5));") == "run_history-20261109-0805.csv"


def test_node_timeline_sums_repeats_and_ranks() -> None:
    out = run_js(
        """
        const t = new L.NodeTimeline();
        t.enter('1', 'Load', 0); t.enter('2', 'KSampler', 100); t.enter('1', 'Load', 1100);
        t.enter('3', 'Save', 1200); t.enter(null, '', 1250);
        for (let i = 0; i < 8; i++) { t.enter('n' + i, 'N' + i, 2000 + i); }
        t.enter(null, '', 2008);
        return { top: t.slowest(), two: t.slowest(2) };
        """
    )
    assert isinstance(out, dict)
    assert out["two"] == [{"title": "KSampler", "ms": 1000}, {"title": "Load", "ms": 200}]
    assert len(out["top"]) == 5 and out["top"][0]["title"] == "KSampler"


def test_scan_prompt_finds_active_timer_and_label() -> None:
    out = run_js(
        """
        const prompt = {
          '10': { class_type: 'KSampler', inputs: {}, _meta: { title: 'My Sampler' } },
          '9': { class_type: 'JWTFRunTimer', inputs: { label: '  hero  ' } },
          '12': { class_type: 'JWTFRunTimer', inputs: { label: 'later' } },
        };
        return { on: L.scanPrompt(prompt), off: L.scanPrompt({ '1': { class_type: 'KSampler', inputs: {} } }),
                 linked: L.scanPrompt({ '1': { class_type: 'JWTFRunTimer', inputs: { label: ['5', 0] } } }),
                 junk: [L.scanPrompt(null), L.scanPrompt('x')] };
        """
    )
    assert isinstance(out, dict)
    assert out["on"]["hasTimer"] is True and out["on"]["label"] == "hero" and out["on"]["nodeCount"] == 3
    assert out["on"]["titles"]["10"] == "My Sampler" and out["on"]["titles"]["9"] == "JWTFRunTimer"
    assert out["off"]["hasTimer"] is False and out["linked"] == {"hasTimer": True, "label": "", "nodeCount": 1, "titles": {"1": "JWTFRunTimer"}}
    assert all(j["hasTimer"] is False for j in out["junk"])


def test_outcome_from_history_uses_server_timestamps() -> None:
    out = run_js(
        """
        const h = (messages, extra = {}) => ({ status: { status_str: 'success', completed: true, messages, ...extra } });
        return {
          ok: L.outcomeFromHistory(h([['execution_start', { timestamp: 1000 }], ['execution_cached', { timestamp: 1010 }], ['execution_success', { timestamp: 6500 }]])),
          err: L.outcomeFromHistory(h([['execution_start', { timestamp: 1000 }], ['execution_error', { timestamp: 2000 }]])),
          intr: L.outcomeFromHistory(h([['execution_start', { timestamp: 10 }], ['execution_interrupted', { timestamp: 20 }]])),
          noTs: L.outcomeFromHistory(h([], { status_str: 'error', completed: false })),
          nothing: [L.outcomeFromHistory(null), L.outcomeFromHistory({}), L.outcomeFromHistory(h([['execution_start', { timestamp: 1 }]], { status_str: 'running' }))],
        };
        """
    )
    assert isinstance(out, dict)
    assert out["ok"] == {"status": "ok", "startedAt": 1000, "endedAt": 6500, "durationMs": 5500}
    assert out["err"]["status"] == "error" and out["err"]["durationMs"] == 1000
    assert out["intr"]["status"] == "interrupted" and out["intr"]["durationMs"] == 10
    assert out["noTs"] == {"status": "error", "startedAt": None, "endedAt": None, "durationMs": None}
    assert out["nothing"] == [None, None, None]


def test_tracker_handles_queued_prompts_by_prompt_id() -> None:
    out = run_js(
        """
        const t = new L.RunTracker();
        const a = t.start('A', { startedAt: 1000, label: 'one' });
        t.executing('1', 'Load', 1000); t.executing('2', 'Sampler', 1500);
        // A ends; B starts right after (queued behind it)
        const doneA = t.finish('A', 4000);
        const b = t.start('B', { startedAt: 4001, label: 'two' });
        t.executing('2', 'Sampler', 4100);
        const recA = L.buildRecord(doneA, 'ok', 4000, 'wf');
        const missing = t.finish('Z', 5000);
        const afterA = { current: t.currentId, primary: t.primary().promptId, active: t.active().length };
        const doneB = t.finish('B', 9000);
        return { recA, missing, afterA, doneB: L.buildRecord(doneB, 'interrupted', 9000, ''), empty: t.currentId, none: t.primary() };
        """
    )
    assert isinstance(out, dict)
    rec = out["recA"]
    assert rec["prompt_id"] == "A" and rec["started_at"] == 1000 and rec["duration_ms"] == 3000 and rec["status"] == "ok" and rec["workflow"] == "wf"
    assert rec["label"] == "one" and rec["slowest"] == [{"title": "Sampler", "ms": 2500}, {"title": "Load", "ms": 500}]
    assert out["missing"] is None and out["afterA"] == {"current": "B", "primary": "B", "active": 1}
    assert out["doneB"]["duration_ms"] == 4999 and out["doneB"]["status"] == "interrupted" and out["doneB"]["slowest"] == [{"title": "Sampler", "ms": 4900}]
    assert out["empty"] is None and out["none"] is None


def test_unknown_record_has_no_duration_and_every_run_is_tracked() -> None:
    out = run_js(
        """
        const t = new L.RunTracker();
        const run = t.start('A', { startedAt: 500.7, hasTimer: false });
        const act = t.active().length;
        const rec = L.buildRecord(run, 'unknown', null, '');
        return { act, rec };
        """
    )
    assert isinstance(out, dict)
    assert out["act"] == 1 and out["rec"]["duration_ms"] is None and out["rec"]["status"] == "unknown" and out["rec"]["slowest"] == [] and out["rec"]["started_at"] == 500


def test_tracker_is_bounded() -> None:
    out = run_js("const t = new L.RunTracker(); for (let i = 0; i < 100; i++) t.start('p' + i, { startedAt: i }); return t.runs.size;")
    assert out == 32


def test_journal_parse_is_defensive() -> None:
    out = run_js(
        """
        const ok = L.parseJournal(JSON.stringify({ a: { started_at: 5, label: 'x', workflow: 'w', node_count: 3, approx: true }, b: { started_at: 'no' }, c: null }));
        return { ok, bad: [L.parseJournal('{oops'), L.parseJournal('[]'), L.parseJournal(null), L.parseJournal('7')],
                 big: Object.keys(L.parseJournal(JSON.stringify(Object.fromEntries(Array.from({ length: 80 }, (_, i) => ['k' + i, { started_at: i }]))))).length };
        """
    )
    assert isinstance(out, dict)
    assert out["ok"] == {"a": {"started_at": 5, "label": "x", "workflow": "w", "node_count": 3, "approx": True}}
    assert out["bad"] == [{}, {}, {}, {}] and out["big"] == 32


def test_parse_queue() -> None:
    out = run_js(
        """
        const q = L.parseQueue({ queue_running: [[0, 'r1', { '1': { class_type: 'X' } }, {}, []]], queue_pending: [[1, 'p1', {}, {}, []], 'junk'] });
        return { running: [...q.running.keys()], pending: [...q.pending.keys()], prompt: q.running.get('r1'), bad: L.parseQueue(null) };
        """
    )
    assert out == {"running": ["r1"], "pending": ["p1"], "prompt": {"1": {"class_type": "X"}}, "bad": None}
