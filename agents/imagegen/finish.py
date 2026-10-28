"""Step 4b: from the raw model image to the final featured image.
raw -> upscale (Real-ESRGAN program when configured, else Lanczos) -> cover-crop to out_width x out_height (never stretched) -> light sharpen + tiny film grain
-> WebP or JPEG, lowering the quality a step at a time until the file fits max_kb (never below min_quality).
Every number comes from config.py (IMG_* variables or config.json "image_pipeline")."""
import io
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config

log = logging.getLogger("imagegen")
_run = subprocess.run  # replaced in tests


def _image(raw):
    from PIL import Image
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _png(img):
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _external(cmd_template, img, scale, label):
    """Run a command template with {input} {output} {scale} on a temporary PNG. Returns the new PIL image, or None when the program is missing or fails."""
    from PIL import Image
    try:
        parts = shlex.split(cmd_template)
    except ValueError:
        return None
    if not parts or not shutil.which(parts[0]):
        log.warning("%s: program %r not found; skipping", label, parts[0] if parts else "")
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "in.png", Path(tmp) / "out.png"
        src.write_bytes(_png(img))
        cmd = [x.format(input=str(src), output=str(dst), scale=scale) for x in parts]
        try:
            done = _run(cmd, capture_output=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("%s failed: %s", label, e)
            return None
        if getattr(done, "returncode", 1) != 0 or not dst.exists():
            log.warning("%s failed (exit %s)", label, getattr(done, "returncode", "?"))
            return None
        return Image.open(io.BytesIO(dst.read_bytes())).convert("RGB")


def upscale(img):
    """Enlarge by upscale_factor. upscaler=realesrgan runs upscale_cmd and falls back to Lanczos; none keeps the size. Returns (image, name of what was used)."""
    kind, factor = config.get("upscaler").strip().lower(), max(1, config.get("upscale_factor"))
    if kind == "none" or factor == 1:
        return img, "none"
    if kind == "realesrgan":
        bigger = _external(config.get("upscale_cmd"), img, factor, "realesrgan")
        if bigger is not None:
            return bigger, "realesrgan"
        log.warning("Real-ESRGAN unavailable; using Lanczos instead")
    from PIL import Image
    return img.resize((img.width * factor, img.height * factor), Image.LANCZOS), "lanczos"


def cover_crop(img, width, height):
    """Scale so the image covers width x height, then centre-crop. Never stretches."""
    from PIL import Image
    scale = max(width / img.width, height / img.height)
    img = img.resize((max(width, round(img.width * scale)), max(height, round(img.height * scale))), Image.LANCZOS)
    left, top = (img.width - width) // 2, (img.height - height) // 2
    return img.crop((left, top, left + width, top + height))


def polish(img):
    """Light finishing: a gentle unsharp mask and a very small amount of film grain. No filters beyond that."""
    from PIL import Image, ImageFilter
    strength, grain = config.get("sharpen"), config.get("grain")
    if strength > 0:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=int(80 * strength), threshold=3))
    if grain > 0:
        noise = Image.effect_noise(img.size, 18)  # grey noise around mid-grey
        img = Image.blend(img, Image.merge("RGB", (noise, noise, noise)), min(0.1, grain * 2))  # at most a 10 percent mix, 3 percent at the default
    return img


def encode(img):
    """(bytes, quality used). Starts at out_quality and steps down by 3 until the file is within max_kb or min_quality is reached."""
    fmt = config.out_format()
    quality, floor, budget = config.get("out_quality"), config.get("min_quality"), config.get("max_kb") * 1024
    while True:
        out = io.BytesIO()
        if fmt == "jpeg":
            img.save(out, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=0)
        else:
            img.save(out, "WEBP", quality=quality, method=6)
        if budget <= 0 or out.tell() <= budget or quality <= floor:
            return out.getvalue(), quality
        quality = max(floor, quality - 3)


def restore_faces(img):
    """Optional face restoration (CodeFormer / GFPGAN wrapper through face_restore_cmd), off by default. Failure keeps the original."""
    if config.get("face_restore").strip().lower() in ("", "off", "none", "false") or not config.get("face_restore_cmd").strip():
        return img, False
    out = _external(config.get("face_restore_cmd"), img, 1, "face restoration")
    return (out, True) if out is not None else (img, False)


def finish(raw, restore=False):
    """The whole finishing step. Returns (bytes, info) where info has the sizes, upscaler, quality and the file extension."""
    img = _image(raw)
    info = {"raw_size": list(img.size)}
    img, info["upscaler"] = upscale(img)
    info["upscaled_size"] = list(img.size)
    img = cover_crop(img, config.get("out_width"), config.get("out_height"))
    if restore:
        img, info["face_restored"] = restore_faces(img)
    img = polish(img)
    data, info["quality"] = encode(img)
    info.update(size=list(img.size), format=config.out_format(), ext=config.out_ext(), kb=round(len(data) / 1024, 1))
    return data, info
