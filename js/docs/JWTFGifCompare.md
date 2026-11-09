# GIF Analyse / Compare

Compare two GIFs or image batches: sizes, frame counts, SSIM and PSNR, with side-by-side, split or difference output.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `layout` | Layout. (default: `side_by_side`) | COMBO | Yes | `"side_by_side"`<br>`"split"`<br>`"difference"` |
| `gif_a` | Reference GIF path (input, output or temp folder). Relative names resolve under input. | STRING | No |  |
| `gif_b` | GIF to judge against A, e.g. an optimised result. | STRING | No |  |
| `images_a` | Images a. | IMAGE | No |  |
| `images_b` | Images b. | IMAGE | No |  |
| `fps_a` | Rate of images_a. (default: 20.0) | FLOAT | No | 0.1 to 1000 (step 0.1) |
| `fps_b` | Rate of images_b. (default: 20.0) | FLOAT | No | 0.1 to 1000 (step 0.1) |
| `sample_frames` | Frames of A measured for SSIM/PSNR (evenly spread). (default: 24) | INT | No | 1 to 400 |
| `output_frames` | Frames in the comparison image batch. (default: 60) | INT | No | 1 to 400 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `compare` | Compare. | IMAGE |
| `report` | Report. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **GIF Tools** page of the JezzWTF Documentation window (Alt+Shift+D).
