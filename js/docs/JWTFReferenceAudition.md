# Reference Audition

Render all references, then omit each reference in turn using the same seed, prompt and target latent. Supports image/LTX bundles and H3 bundles. A render cap and between-render time budget bound the sweep. Visual change measures influence, never quality. Use Save Audition Selection to keep your chosen references without rerunning trials.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `model` | The model to use. | MODEL | Yes |  |
| `vae` | The VAE to use. | VAE | Yes |  |
| `latent_image` | Fixed target for every trial. Use a clean, batch-one latent matching the model, without pre-applied references or LTX guide frames. | LATENT | Yes |  |
| `refmod` | Refmod. (default: `None`) | COMBO | Yes | choose from the list |
| `seed` | Random seed; the same seed gives the same result. (default: 42) | INT | Yes |  |
| `steps` | Steps. (default: 12) | INT | Yes | 1 to 1000 |
| `cfg` | Cfg. (default: 4) | FLOAT | Yes | 0 to 100 (step 0.1) |
| `sampler_name` | Sampler name. (default: `euler`) | COMBO | Yes | choose from the list |
| `scheduler` | Scheduler. (default: `simple`) | COMBO | Yes | `"simple"`<br>`"sgm_uniform"`<br>`"karras"`<br>`"exponential"`<br>`"ddim_uniform"`<br>`"beta"`<br>`"normal"`<br>`"linear_quadratic"`<br>`"kl_optimal"` |
| `denoise` | Denoise. (default: 1) | FLOAT | Yes | 0.01 to 1 (step 0.01) |
| `max_renders` | Includes the full-reference baseline. Reference omissions run in source order; untested numbers appear in the report. (default: 5) | INT | Yes | 1 to 81 |
| `time_budget_seconds` | Soft wall-time budget: finish the current render, then stop. 0 disables the time limit; max_renders still applies. (default: 120) | FLOAT | Yes | 0 to 86400 |
| `clip` | The CLIP / text encoder to use. | CLIP | No |  |
| `prompt` | The text prompt. | STRING | No |  |
| `negative_prompt` | What the result should avoid. | STRING | No |  |
| `positive` | Clean prompt conditioning for Flux, LTX or H3. Do not apply references upstream. | CONDITIONING | No |  |
| `negative` | Negative. | CONDITIONING | No |  |
| `edit_format` | Edit format. (default: `ai-toolkit (kv_cache off)`) | COMBO | No | `"ai-toolkit"`<br>`"ai-toolkit (kv_cache off)"`<br>`"Moss-Image-Edit"`<br>`"Krea2 style reference"` |
| `ref_strength` | Image reference schedule; LTX guide strength; H3 retention. Held fixed across trials. (default: 1) | FLOAT | No | 0 to 1 (step 0.01) |
| `ref_on_negative` | Ref on negative. (default: true) | BOOLEAN | No |  |
| `latent_idx` | LTX guide start, in latent frames. (default: 0) | INT | No | 0 to 10000 |
| `sigmas` | Exact schedule from your working generation workflow, e.g. Flux2Scheduler. Overrides steps, scheduler and denoise widgets for every trial. | SIGMAS | No |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `contact_sheet` | Contact sheet. | IMAGE |
| `audition` | Audition. | JWTF_REF_AUDITION |
| `report` | Report. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
