# Contributing

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
