MAX_SLOTS = 6


class AnyType(str):
    """Compares equal to every type so ComfyUI accepts any connection."""

    def __ne__(self, other: object) -> bool:
        return False


ANY = AnyType("*")


class ContainsAnyDict(dict):
    """An empty dict that reports containing any key.
    Empty → ComfyUI renders no input slots from the Python definition.
    __contains__ always True → any JS-added input name passes validation.
    dict subclass → JSON serialisable (serialises as {})."""

    def __contains__(self, key: object) -> bool:
        return True

    def __getitem__(self, key: str) -> tuple:
        return (ANY, {})


class MultiSwitch:
    TITLE = "Multi Switch"
    CATEGORY = "JezzWTF/utils"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "switch": ("BOOLEAN", {
                    "default": False,
                    "label_on": "true",
                    "label_off": "false",
                    "tooltip": "Option A → false_N inputs pass through.  Option B → true_N inputs pass through.",
                }),
            },
            "optional": ContainsAnyDict(),
            "hidden": {
                "num_slots": ("INT", {"default": 2}),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, input_types):
        return True

    RETURN_TYPES = (ANY,) * MAX_SLOTS
    RETURN_NAMES = tuple(f"output_{i}" for i in range(1, MAX_SLOTS + 1))
    FUNCTION = "execute"

    def execute(self, switch: bool, num_slots: int = 2, **kwargs) -> tuple:
        side = "true" if switch else "false"
        return tuple(kwargs.get(f"{side}_{i}", None) for i in range(1, MAX_SLOTS + 1))
