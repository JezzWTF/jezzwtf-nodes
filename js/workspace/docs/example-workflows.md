# Example workflows

Open the **Workflows** window and pick the **JezzWTF examples** category, or drag a file from the repository's `example_workflows` folder into ComfyUI. ComfyUI also lists them in its Templates browser under this pack.

| Workflow | What it does | Needs |
|---|---|---|
| Character Creator | Qwen3.5 writes a Character Card V2 from a concept, bakes it with your portrait, then chats with it | Qwen3.5 |
| Character Chat | The minimal chat setup | Qwen3.5 and a character card |
| Video to GIF Optimised | Load a video and optimise it to a size budget | Nothing beyond core |
| GIF Optimise and Compare | Load a GIF, re-encode it, compare with the original in Video Compare | Nothing beyond core |
| Dataset Captioning | Caption a whole folder of images and save a `.txt` next to each | Qwen3.5 |
| RefMod Bake and Apply (H3) | Bake a portrait into a RefMod and use it in H3 reference-to-video | MiniMax H3 reference model, text encoder and VAEs |

Each workflow has a "How it works" note. Pick your own file in the loader node first: the shipped placeholder names (`your.gif`, `example.png`) will not exist on your machine.
