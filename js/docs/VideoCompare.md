# Video Compare

Synchronized A/B comparison of two videos in the UI. Play both side-by-side, wipe between them with a slider, or view the difference blend — useful for checking body/scene swap results against the original.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `video_a` | Reference video, usually the original source (shown left/top). | VIDEO | No |  |
| `video_b` | Result video to compare against A (shown right/bottom). | VIDEO | No |  |
| `image_a` | Fallback for A when the pipeline only outputs frames (e.g. VHS or Wan decode). Ignored while video_a is connected. | IMAGE | No |  |
| `image_b` | Fallback for B when the pipeline only outputs frames (e.g. VHS or Wan decode). Ignored while video_b is connected. | IMAGE | No |  |
| `frame_rate` | Frame rate used only when building a video from IMAGE fallback inputs. (default: 16.0) | FLOAT | No | 1 to 120 (step 0.5) |
| `b_offset` | Seconds to shift B against A: B plays at A's time + offset (positive skips into B, negative delays it). (default: 0.0) | FLOAT | No | -1000 to 1000 (step 0.001) |
| `audio_a` | Audio mixed into the preview when A is built from IMAGE frames. Ignored while video_a is connected. | AUDIO | No |  |
| `audio_b` | Audio mixed into the preview when B is built from IMAGE frames. Ignored while video_b is connected. | AUDIO | No |  |
| `filename_prefix` | Filename prefix and optional subfolder for the two preview MP4s written to ComfyUI's temp directory. (default: videoCompare) | STRING | No |  |

Notes:

- More detail, including how this node fits with the others, is in the **Where files are saved** page of the JezzWTF Documentation window (Alt+Shift+D).
