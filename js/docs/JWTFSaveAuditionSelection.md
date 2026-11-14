# Save Audition Selection

Save chosen references as a compatible new bundle, without rerunning the upstream audition. Source order is numbered from 1. Saving is off by default; the original bundle is always preserved.

## Inputs

| Parameter | Description | Data Type | Required | Range |
|-----------|-------------|-----------|----------|-------|
| `audition` | Audition. | JWTF_REF_AUDITION | Yes |  |
| `keep_refs` | Comma-separated 1-based source indices, e.g. 1,3; or all. Order is preserved as entered. (default: all) | STRING | Yes |  |
| `name` | Name. (default: audition_selection) | STRING | Yes |  |
| `save` | Save. (default: false) | BOOLEAN | Yes |  |
| `overwrite` | Overwrite. (default: false) | BOOLEAN | Yes |  |

## Outputs

| Output Name | Description | Data Type |
|-------------|-------------|-----------|
| `path` | File path, overriding the picker. | STRING |
| `info` | Info. | STRING |

Notes:

- More detail, including how this node fits with the others, is in the **Tail and Image RefMod** page of the JezzWTF Documentation window (Alt+Shift+D).
