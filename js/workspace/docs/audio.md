# Audio Loader and Album Cover

## Audio Loader

Loads an audio file from the `input` folder (subfolders included) as AUDIO.

- `audio` picks a file. **Upload audio…** under it copies a file into `input` and selects it; a small player previews the selection.
- `start` and `length` trim in seconds (`length` 0 keeps the rest). `mono` mixes all channels down to one.
- `path` overrides the picker with a file path from the `input`, `output` or `temp` folder, for example the `file_path` of another node.

Outputs: `audio`, `duration` (seconds, after trimming), `sample_rate` and `file_path`. mp3, wav, flac, ogg, opus, m4a, aac, wma and aiff are read.

## Album Cover

Embeds an image as the cover art of an audio file, and can set its title, artist and album.

- `audio_path` is the file to tag, from Audio Loader's `file_path` or typed in. Cover art can be embedded in **mp3, flac and m4a** files.
- `image` supplies the picture; `image_index` picks a frame from a batch. `cover_size` scales it down to that longest edge (it never scales up; 0 keeps the size). It is stored as JPEG.
- `save_mode` either **saves a copy** under `output/<filename_prefix>/` (never overwriting, it counts up `_001`, `_002`…) or **replaces the original**. Replacing is refused for files in the `temp` folder.
- `title`, `artist` and `album` are only written when they are not empty; other existing tags are kept.

The audio itself is copied packet for packet, so there is no re-encoding and no quality loss.

## Good to know

- Wav and ogg files cannot carry cover art in a way players agree on; the node says so instead of writing something half-working.
- The Audio Loader's file list is read when ComfyUI loads node definitions. Press **R** on the canvas to refresh it after adding files by hand.
