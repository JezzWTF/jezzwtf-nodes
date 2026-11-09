import torch
from comfy_api.latest import io


class ImageAspectSize(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="ImageAspectSize",
            display_name='Image Aspect Size',
            category='JezzWTF/image',
            inputs=[
                io.Image.Input("image"),
                io.Int.Input("target_size", default=1024, min=64, max=8192, step=8, tooltip='Longest side in pixels. The other dimension is calculated to preserve aspect ratio, snapped to multiples of 8.'),
                io.Boolean.Input("flip", default=False, label_on='Flipped (portrait↔landscape)', label_off='Normal', tooltip='Swap width and height before scaling — useful for rotating orientation without changing the image.'),
            ],
            outputs=[
                io.Image.Output("IMAGE"),
                io.Int.Output("WIDTH"),
                io.Int.Output("HEIGHT"),
            ],
        )

    @classmethod
    def execute(cls, image: torch.Tensor, target_size: int, flip: bool) -> io.NodeOutput:
        _, H, W, _ = image.shape

        if flip:
            W, H = H, W

        scale = target_size / max(W, H)
        width = round(W * scale / 8) * 8
        height = round(H * scale / 8) * 8

        return io.NodeOutput(image, width, height)


NODES = [ImageAspectSize]
