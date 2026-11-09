# Contributing

## Writing nodes

Every node uses ComfyUI's V3 API (`comfy_api.latest`): a class derived from `io.ComfyNode` with a `define_schema()` classmethod and an `execute()` classmethod that returns `io.NodeOutput`. Each node family's `__init__.py` exports `NODES`, and the pack's top-level `__init__.py` registers them through `comfy_entrypoint`. Do not add `NODE_CLASS_MAPPINGS`.

- Keep a node's id and the order of its inputs stable: saved workflows store widget values by position.
- A list of choices that depends on disk (models, files) belongs in `define_schema()` as a call such as `options=list_models()`, so it is read each time ComfyUI asks for the node definitions.
- Read hidden inputs from `cls.hidden` (declare them with `hidden=[io.Hidden.unique_id]`); use `fingerprint_inputs` for caching and `validate_inputs` for checks.
- ComfyUI shows `js/docs/<NodeId>.md` as each node's help page. Those pages are generated: with this pack loaded in a running ComfyUI, run `python tools/generate_node_docs.py http://127.0.0.1:8188` after changing a node's inputs or description. A test fails when a node has no page.
- Tests call `Node.execute(...)` directly. `tests/v3_helpers.py` has `legacy()` (old return shape), `hidden()` / `run_node()` (set hidden inputs) and `legacy_spec()` (old input-spec shape).

## Tests

Tests live in `tests/`, one folder per node family:

```bash
python -m pytest tests/<family> -q
```

Run each folder on its own. Some tests skip themselves when ComfyUI core or ffmpeg isn't available. No test may write into a real ComfyUI `models` or `output` folder; use the fixtures in each folder's `conftest.py`.

## Checks before a pull request

- `python -m pytest tests/<family> -q` for every family you touched.
- `node --check --input-type=module < <file>.js` for every JS file you changed.
- New behaviour comes with a test, and a bug fix comes with a regression test.

## Publishing

Releases go to the [Comfy Registry](https://registry.comfy.org). Bump `version` in `pyproject.toml` and push to `main`. The `Publish to Comfy registry` workflow does the rest and needs a `REGISTRY_ACCESS_TOKEN` repository secret.

`requires-comfyui` in `pyproject.toml` is the oldest ComfyUI the pack has been run on. Only lower it after testing on the older version.
