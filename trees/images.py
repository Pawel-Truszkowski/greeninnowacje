"""Turning a phone photo into a file we are willing to store (Etap 2: zdjęcia drzew).

Nothing is stored as it arrived: every upload is decoded and **re-encoded**. Checking the
extension or the magic bytes only proves a file starts like an image; re-encoding means the
stored file was built by our own code out of pixels. That drops the whole EXIF block — the
photographer's GPS position included, which in a private garden is a worse leak than the
tree's coordinates because nobody sees it — and neutralises files that are a valid image and
a script at once.
"""

import io
from dataclasses import dataclass

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
# Not a duplicate of the byte limit: a 8.8 kB PNG can declare 3000×3000 (measured), so a
# 200 kB one can declare 50 000×50 000 and make Pillow reach for gigabytes while decoding.
MAX_PIXELS = 40_000_000
MAX_EDGE_PX = 1600
JPEG_QUALITY = 82

UNREADABLE = (
    UnidentifiedImageError,
    Image.DecompressionBombError,
    OSError,
    ValueError,
    SyntaxError,
)


class InvalidImage(Exception):
    """Not something we can store. The message reaches the user, so it is in Polish."""


@dataclass(frozen=True)
class ProcessedImage:
    file: ContentFile
    width: int
    height: int


def _open_checked(data):
    """Prove `data` is an image within limits, then return it open for the real work.

    `verify()` checks the content rather than the name, and leaves the object unusable —
    hence the second `open()`. `size` comes from the header, so the pixel limit costs nothing.
    """
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            probe.verify()
    except UNREADABLE:
        raise InvalidImage("Nie udało się odczytać zdjęcia.") from None

    if width * height > MAX_PIXELS:
        raise InvalidImage("Zdjęcie jest zbyt duże. Spróbuj z mniejszym plikiem.")

    return Image.open(io.BytesIO(data))


def _flattened(image):
    """Drop the alpha a JPEG cannot carry onto white; `convert("RGB")` alone gives black."""
    # A palette PNG can be transparent without an A band, hence the second check.
    if "A" not in image.getbands() and "transparency" not in image.info:
        return image.convert("RGB")

    white = Image.new("RGBA", image.size, "white")
    white.alpha_composite(image.convert("RGBA"))
    return white.convert("RGB")


def process_upload(uploaded_file, *, fit=None):
    """Validate, straighten, shrink and re-encode an upload into a `ProcessedImage`.

    With `fit=(width, height)` the result has exactly that size: the centre is cropped to the
    aspect ratio and scaled, up if need be — a grid of cards needs every photo the same shape.

    The file gets a plain name; the tree id and UUID belong in the model's `upload_to`.
    """
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise InvalidImage(f"Plik jest za duży, maksymalnie {limit_mb} MB.")

    uploaded_file.seek(0)
    data = uploaded_file.read()

    with _open_checked(data) as image:
        photo = ImageOps.exif_transpose(image)
        if fit:
            photo = ImageOps.fit(photo, fit, Image.Resampling.LANCZOS)
        else:
            photo.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.Resampling.LANCZOS)
        photo = _flattened(photo)

    # Encoding sits outside the try above: a failure here is our bug, not a bad upload.
    buffer = io.BytesIO()
    photo.save(buffer, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return ProcessedImage(
        file=ContentFile(buffer.getvalue(), name="zdjecie.jpg"),
        width=photo.width,
        height=photo.height,
    )
