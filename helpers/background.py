import pjsk_background_gen_PIL
from PIL import Image


def render_png(version: str, original_image: Image) -> Image:
    if version == "v1":
        return pjsk_background_gen_PIL.render_v1(original_image)
    return pjsk_background_gen_PIL.render_v3(original_image)
