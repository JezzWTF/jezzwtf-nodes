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

## Pull requests

Nobody pushes to `main`, maintainers included. Work on a branch and open a pull request:

- CI (the `Tests` workflow) must pass, and the change needs a review from a code owner (see `.github/CODEOWNERS`).
- Keep a pull request to one change, and say what it changes and how you checked it.
- Changes to `.github/`, `pyproject.toml` or anything that affects what gets published are reviewed more carefully, whoever opens them.
- Do not bump `version` in a feature pull request. A version bump is its own small pull request, opened when a release is planned.

## Releases

Only a maintainer releases. A release is a version tag, not a push to `main`:

1. Merge a pull request that bumps `version` in `pyproject.toml` (and says what changed).
2. Tag that commit on `main` as `v<version>`, for example `v1.2.0`, and push the tag.
3. The `Publish to Comfy registry` workflow runs the whole test suite, checks that the commit is on `main` and that the tag matches `pyproject.toml`, then waits for a maintainer to approve the `release` environment. Only after that approval does it publish.

The registry token lives in the `REGISTRY_ACCESS_TOKEN` secret of the `release` environment, so it is not available to pull requests or other workflows.

### One-time repository setup (maintainer)

These are repository settings, not files, so they have to be switched on by hand:

- **Branch protection on `main`**: require a pull request, require the `Tests` check to pass, require review from Code Owners, block force pushes and deletion, and include administrators.
- **Tag protection**: restrict who can create `v*` tags to maintainers (a tag ruleset).
- **Environment `release`**: Settings > Environments > New environment, add yourself as a required reviewer, and move `REGISTRY_ACCESS_TOKEN` from the repository secrets into this environment.
- **Actions**: in Settings > Actions > General, set workflow permissions to read-only and require approval for workflows from outside collaborators.

`requires-comfyui` in `pyproject.toml` is the oldest ComfyUI the pack has been run on. Only lower it after testing on the older version.
