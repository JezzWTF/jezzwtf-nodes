from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path

import pytest
from aiohttp.test_utils import make_mocked_request

from paste_stack import NODES, clipboard, routes

MB = 1024 * 1024


# ------------------------------------------------------------------ package


def test_package_adds_no_nodes() -> None:
    assert NODES == []


# ------------------------------------------------------------------ caller checks


@pytest.mark.parametrize("remote", ["127.0.0.1", "127.5.6.7", "::1", "::ffff:127.0.0.1", "localhost"])
def test_loopback_callers_accepted(remote: str) -> None:
    assert clipboard.is_local_caller(remote)


@pytest.mark.parametrize("remote", [None, "", "192.168.1.20", "10.0.0.2", "8.8.8.8", "::ffff:192.168.1.5", "evil.example", "2001:db8::1"])
def test_non_loopback_callers_rejected(remote: str | None) -> None:
    assert not clipboard.is_local_caller(remote)


@pytest.mark.parametrize(
    ("host", "origin", "ok"),
    [
        ("127.0.0.1:8188", None, True),
        ("localhost:8188", "http://localhost:8188", True),
        ("[::1]:8188", "http://[::1]:8188", True),
        ("evil.example:8188", None, False),
        ("127.0.0.1:8188", "https://evil.example", False),
        (None, None, False),
        ("192.168.1.2:8188", None, False),
    ],
)
def test_host_and_origin_validation(host: str | None, origin: str | None, ok: bool) -> None:
    assert clipboard.is_local_request_origin(host, origin) is ok


# ------------------------------------------------------------------ powershell parsing and subprocess


def test_parse_powershell_paths_trims_and_drops_blanks() -> None:
    raw = "\ufeffC:\\a\\one.png\r\n\r\n  C:\\b\\two.txt  \r\n".encode("utf-8")
    assert clipboard.parse_powershell_paths(raw) == ["C:\\a\\one.png", "C:\\b\\two.txt"]


def test_parse_powershell_paths_replaces_bad_bytes() -> None:
    assert clipboard.parse_powershell_paths(b"C:\\x\xff.png\n") == ["C:\\x\ufffd.png"]


def test_powershell_uses_fixed_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        seen["args"] = args
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="C:\\pics\\a.png\r\n".encode("utf-8"), stderr=b"")

    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)
    assert clipboard._powershell_paths() == ["C:\\pics\\a.png"]
    args = seen["args"]
    assert args == list(clipboard.POWERSHELL_ARGS)
    assert "-STA" in args and "-NoProfile" in args and "-NonInteractive" in args
    kwargs = seen["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["timeout"] == 6
    assert kwargs["creationflags"] == 0x08000000
    assert "shell" not in kwargs


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired("powershell", 6), OSError("missing")])
def test_powershell_failure_is_empty(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    def boom(*_a: object, **_k: object) -> subprocess.CompletedProcess[bytes]:
        raise exc

    monkeypatch.setattr(clipboard.subprocess, "run", boom)
    assert clipboard._powershell_paths() == []


def test_read_content_prefers_pillow_then_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clipboard, "_pillow_clipboard", lambda: ([], None))
    monkeypatch.setattr(clipboard, "_powershell_paths", lambda: ["C:\\z.png"])
    monkeypatch.setattr(clipboard.sys, "platform", "win32")
    assert clipboard.read_clipboard_content() == (["C:\\z.png"], None)
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    assert clipboard.read_clipboard_content() == ([], None)
    monkeypatch.setattr(clipboard, "_pillow_clipboard", lambda: (["/a.png"], None))
    assert clipboard.read_clipboard_content() == (["/a.png"], None)


# ------------------------------------------------------------------ allowlist and limits


def test_allowlist_matches_spec() -> None:
    assert clipboard.ALLOWED_EXTENSIONS == frozenset(
        "png jpg jpeg webp gif bmp avif tif tiff txt md json csv tsv yaml yml log ini toml xml".split()
    )
    assert "py" not in clipboard.ALLOWED_EXTENSIONS and "html" not in clipboard.ALLOWED_EXTENSIONS


def test_select_filters_extension_and_missing() -> None:
    sizes = {"a.PNG": 10, "b.exe": 10, "c.txt": 5}
    got = clipboard.select_file_paths(["a.PNG", "b.exe", "c.txt", "gone.txt"], sizes)
    assert got == [("a.PNG", 10), ("c.txt", 5)]


def test_select_caps_file_count() -> None:
    paths = [f"f{i}.txt" for i in range(15)]
    got = clipboard.select_file_paths(paths, {p: 1 for p in paths})
    assert [p for p, _ in got] == paths[:10]


def test_select_per_file_and_total_limits_skip_but_continue() -> None:
    sizes = {
        "big.png": 25 * MB + 1,  # over per-file limit
        "a.png": 25 * MB,
        "b.png": 25 * MB,
        "c.png": 11 * MB,  # would exceed 60 MB total (25+25+11)
        "d.png": 10 * MB,  # still fits afterwards
    }
    got = clipboard.select_file_paths(list(sizes), sizes)
    assert [p for p, _ in got] == ["a.png", "b.png", "d.png"]


def test_select_real_filesystem_skips_folders_and_nul(tmp_path: Path) -> None:
    good = tmp_path / "ok.txt"
    good.write_text("hi")
    folder = tmp_path / "dir.txt"
    folder.mkdir()
    got = clipboard.select_file_paths([str(good), str(folder), str(tmp_path / "nope.txt"), "bad\x00.txt"])
    assert [p for p, _ in got] == [str(good)]


def test_read_files_names_mimes_and_base64(tmp_path: Path) -> None:
    (tmp_path / "pic.webp").write_bytes(b"RIFF")
    (tmp_path / "n.md").write_text("# t")
    (tmp_path / "d.json").write_text("{}")
    (tmp_path / "t.TXT").write_text("plain")
    (tmp_path / "s.exe").write_bytes(b"x")
    paths = [str(tmp_path / n) for n in ("pic.webp", "n.md", "d.json", "t.TXT", "s.exe")]
    files = clipboard.read_files(paths)
    assert [f["name"] for f in files] == ["pic.webp", "n.md", "d.json", "t.TXT"]
    assert [f["mime"] for f in files] == ["image/webp", "text/markdown", "application/json", "text/plain"]
    assert base64.b64decode(files[0]["data"]) == b"RIFF"


def test_mime_unknown_extension_falls_back_to_octet_stream() -> None:
    assert clipboard.mime_for("thing.log") in {"text/plain", "application/octet-stream"}
    assert clipboard.mime_for("x.avif") == "image/avif"


def test_name_never_contains_directories(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x")
    [entry] = clipboard.read_files([str(tmp_path / "a.txt")])
    assert entry["name"] == "a.txt"


# ------------------------------------------------------------------ raw image fallback


def test_raw_image_becomes_png_when_no_files(monkeypatch: pytest.MonkeyPatch) -> None:
    from PIL import Image

    image = Image.new("RGB", (3, 2), (255, 0, 0))
    monkeypatch.setattr(clipboard, "read_clipboard_content", lambda: ([], image))
    [entry] = clipboard.collect_clipboard_files()
    assert entry["name"] == "clipboard.png" and entry["mime"] == "image/png"
    assert base64.b64decode(entry["data"]).startswith(b"\x89PNG")


def test_files_win_over_image(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from PIL import Image

    (tmp_path / "a.txt").write_text("x")
    monkeypatch.setattr(clipboard, "read_clipboard_content", lambda: ([str(tmp_path / "a.txt")], Image.new("RGB", (1, 1))))
    assert [f["name"] for f in clipboard.collect_clipboard_files()] == ["a.txt"]


def test_collect_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> tuple[list[str], None]:
        raise RuntimeError("x")

    monkeypatch.setattr(clipboard, "read_clipboard_content", boom)
    assert clipboard.collect_clipboard_files() == []


# ------------------------------------------------------------------ route


class _Transport:
    def __init__(self, remote: str | None) -> None:
        self._remote = remote

    def get_extra_info(self, name: str, default: object = None) -> object:
        if name == "peername" and self._remote is not None:
            return (self._remote, 1234)
        return default


def _call(headers: dict[str, str], remote: str | None = "127.0.0.1") -> tuple[int, dict[str, object]]:
    async def run() -> tuple[int, dict[str, object]]:
        transport = _Transport(remote)
        request = make_mocked_request("POST", routes.ROUTE_PATH, headers=headers, transport=transport)
        response = await routes.handle_clipboard(request)
        return response.status, json.loads(response.text or "{}")

    return asyncio.run(run())


def test_route_missing_header_is_forbidden() -> None:
    status, body = _call({"Host": "127.0.0.1:8188"})
    assert (status, body) == (403, {"files": [], "error": "forbidden"})


def test_route_wrong_header_value_is_forbidden() -> None:
    status, _ = _call({"Host": "127.0.0.1:8188", "X-JezzWTF-Paste": "true"})
    assert status == 403


def test_route_remote_peer_is_not_local() -> None:
    status, body = _call({"Host": "127.0.0.1:8188", "X-JezzWTF-Paste": "1"}, remote="192.168.1.9")
    assert (status, body) == (403, {"files": [], "error": "not-local"})


def test_route_bad_host_is_not_local() -> None:
    status, body = _call({"Host": "evil.example", "X-JezzWTF-Paste": "1"})
    assert (status, body["error"]) == (403, "not-local")


def test_route_header_check_precedes_locality() -> None:
    status, body = _call({"Host": "evil.example"}, remote="8.8.8.8")
    assert body["error"] == "forbidden" and status == 403


def test_route_success_runs_off_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    main = threading.get_ident()
    seen: list[int] = []

    def fake() -> list[clipboard.ClipboardFile]:
        seen.append(threading.get_ident())
        return [{"name": "a.txt", "mime": "text/plain", "data": "eA=="}]

    monkeypatch.setattr(clipboard, "collect_clipboard_files", fake)
    status, body = _call({"Host": "localhost:8188", "X-JezzWTF-Paste": "1", "Origin": "http://localhost:8188"})
    assert status == 200 and body == {"files": [{"name": "a.txt", "mime": "text/plain", "data": "eA=="}]}
    assert seen and seen[0] != main


def test_route_timeout_gives_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    monkeypatch.setattr(routes, "COLLECT_TIMEOUT_S", 0.05)
    monkeypatch.setattr(clipboard, "collect_clipboard_files", lambda: (time.sleep(0.3), [])[1])
    status, body = _call({"Host": "127.0.0.1:8188", "X-JezzWTF-Paste": "1"})
    assert (status, body) == (200, {"files": []})


def test_register_adds_post_route() -> None:
    from aiohttp import web

    table = web.RouteTableDef()
    routes.register(table)
    assert [(r.method, r.path) for r in table] == [("POST", "/jezzwtf/paste_stack/clipboard")]


def test_helper_never_writes_clipboard_to_disk() -> None:
    src = (Path(clipboard.__file__)).read_text(encoding="utf-8")
    assert "open(path, \"wb\"" not in src and "NamedTemporaryFile" not in src and "tempfile" not in src
    assert os.path.basename(clipboard.__file__) == "clipboard.py"
