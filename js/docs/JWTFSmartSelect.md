# Smart Select (WeVisOne)

Find a subject described in words with native WeVisOne-VL. Output alpha masks and pixel boxes for Mask Editor or regional refinement. Detection mode outputs rectangular masks; segmentation outputs the model's mattes.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `clip` | WeVisOne-VL checkpoint loaded by CLIPLoader; native core detects this architecture automatically. | CLIP | Yes |  |
| `images` | The input images (an image batch). | IMAGE | Yes |  |
| `query` | Query. (default: face) | STRING | Yes |  |
| `task` | Task. (default: `segmentation`) | COMBO | Yes | `"segmentation"`<br>`"detection"` |
| `selection` | Selection. (default: `largest`) | COMBO | Yes | `"largest"`<br>`"all"`<br>`"index"` |
| `selection_index` | Zero-based detection index, used only by index selection. (default: 0) | INT | Yes | 0 to 999 |
| `max_length` | Max length. (default: 1024) | INT | Yes | 64 to 32768 |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `mask` | The mask. | MASK |
| `bboxes` | Bboxes. | BOUNDING_BOX |
| `report` | Report. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Image Compare, Image Saver and Mask Editor** page of the JezzWTF Documentation window (Alt+Shift+D).
