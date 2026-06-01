import torch


class ImageAspectSize:
    TITLE = "Image Aspect Size"
    CATEGORY = "JezzWTF/image"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "target_size": ("INT", {
                    "default": 1024,
                    "min": 64,
                    "max": 8192,
                    "step": 8,
                    "tooltip": "Longest side in pixels. The other dimension is calculated to preserve aspect ratio, snapped to multiples of 8.",
                }),
                "flip": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Flipped (portrait↔landscape)",
                    "label_off": "Normal",
                    "tooltip": "Swap width and height before scaling — useful for rotating orientation without changing the image.",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("IMAGE", "WIDTH", "HEIGHT")
    FUNCTION = "calculate"

    def calculate(self, image: torch.Tensor, target_size: int, flip: bool) -> tuple[torch.Tensor, int, int]:
        _, H, W, _ = image.shape

        if flip:
            W, H = H, W

        scale = target_size / max(W, H)
        width = round(W * scale / 8) * 8
        height = round(H * scale / 8) * 8

        return (image, width, height)
