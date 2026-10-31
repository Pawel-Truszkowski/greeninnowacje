"""Photo processing (Etap 2). Written before the implementation. No database, no HTTP.

`test_exif_is_gone` matters most: a phone writes the photographer's GPS position into the
file, and in a private garden that position is a doorstep nobody thinks to remove. The
helpers build a JPEG carrying real GPS tags, so the test proves the stripping.
"""

import io

import pytest
from PIL import ExifTags, Image, ImageOps

from trees.images import (
    JPEG_QUALITY,
    MAX_EDGE_PX,
    MAX_UPLOAD_BYTES,
    InvalidImage,
    process_upload,
)

ORIENTATION = 274
MAKE = 271


class FakeUpload(io.BytesIO):
    """What a view hands to `process_upload`: bytes plus `.size` and `.name`."""

    def __init__(self, data, name="zdjecie.jpg"):
        super().__init__(data)
        self.size = len(data)
        self.name = name


def jpeg(size=(800, 600), colour="green", exif=None, mode="RGB"):
    image = Image.new(mode, size, colour)
    buffer = io.BytesIO()
    if exif is None:
        image.save(buffer, "JPEG", quality=JPEG_QUALITY)
    else:
        image.save(buffer, "JPEG", quality=JPEG_QUALITY, exif=exif(image).tobytes())
    return buffer.getvalue()


def with_gps_and_rotation(image):
    """EXIF as a phone writes it: maker, orientation and a GPS position."""
    exif = image.getexif()
    exif[MAKE] = "TestPhone"
    exif[ORIENTATION] = 6  # "rotate 90°" — the usual portrait photo
    exif.get_ifd(ExifTags.IFD.GPSInfo).update(
        {1: "N", 2: (52.0, 52.0, 12.0), 3: "E", 4: (19.0, 39.0, 4.0)}
    )
    return exif


def png(size=(800, 600), mode="RGB", colour="blue"):
    buffer = io.BytesIO()
    Image.new(mode, size, colour).save(buffer, "PNG")
    return buffer.getvalue()


def opened(processed):
    return Image.open(io.BytesIO(processed.file.read()))


class TestStripsMetadata:
    def test_exif_is_gone(self):
        """The whole EXIF block goes, GPS included — see the module docstring."""
        before = Image.open(io.BytesIO(jpeg(exif=with_gps_and_rotation)))
        assert before.getexif(), "Materiał testowy musi naprawdę mieć EXIF"
        assert before.getexif().get_ifd(ExifTags.IFD.GPSInfo), "…i naprawdę mieć GPS"

        after = opened(process_upload(FakeUpload(jpeg(exif=with_gps_and_rotation))))

        assert after._getexif() is None
        assert dict(after.getexif()) == {}

    def test_output_is_always_jpeg(self):
        assert opened(process_upload(FakeUpload(png(), name="rysunek.png"))).format == "JPEG"

    def test_original_filename_is_not_trusted(self):
        """The name comes from us; the tree id and UUID are added by the model's upload_to."""
        processed = process_upload(FakeUpload(jpeg(), name="../../etc/passwd.jpg"))

        assert "passwd" not in processed.file.name
        assert ".." not in processed.file.name


class TestGeometry:
    def test_rotation_from_exif_is_applied(self):
        """A portrait photo tagged "rotate 90°" must be stored upright, not sideways."""
        data = jpeg(size=(600, 400), exif=with_gps_and_rotation)

        processed = process_upload(FakeUpload(data))

        assert (processed.width, processed.height) == (400, 600)

    def test_large_photo_is_downscaled_keeping_proportions(self):
        processed = process_upload(FakeUpload(jpeg(size=(4000, 3000))))

        assert max(processed.width, processed.height) == MAX_EDGE_PX
        assert processed.width / processed.height == pytest.approx(4 / 3, abs=0.01)

    def test_small_photo_is_left_alone(self):
        """Upscaling would only invent pixels and make the file bigger."""
        processed = process_upload(FakeUpload(jpeg(size=(320, 240))))

        assert (processed.width, processed.height) == (320, 240)

    @pytest.mark.parametrize("size", [(4000, 3000), (600, 1600), (200, 150)])
    def test_fit_gives_exactly_the_requested_size(self, size):
        """Species cards in the knowledge base: every photo the same 4:5 shape."""
        processed = process_upload(FakeUpload(jpeg(size=size)), fit=(400, 500))

        assert (processed.width, processed.height) == (400, 500)
        assert opened(processed).size == (400, 500)

    def test_reported_size_matches_the_stored_file(self):
        """The numbers go into <img width height>, so a mismatch would shift the layout."""
        processed = process_upload(FakeUpload(jpeg(size=(1000, 500))))

        assert opened(processed).size == (processed.width, processed.height)


class TestRejects:
    @pytest.mark.parametrize(
        ("label", "data"),
        [
            ("plik tekstowy", b"to nie jest obraz, tylko notatka"),
            ("pusty plik", b""),
            ("obcięty JPEG", jpeg()[:40]),
            ("plik HTML", b"<!doctype html><script>alert(1)</script>"),
        ],
    )
    def test_anything_that_is_not_an_image(self, label, data):
        with pytest.raises(InvalidImage):
            process_upload(FakeUpload(data, name=f"{label}.jpg"))

    def test_message_is_in_polish_and_readable(self):
        """It lands in `messages` on the tree card (UI doc §107: "błąd zapisu zdjęcia")."""
        with pytest.raises(InvalidImage) as error:
            process_upload(FakeUpload(b"nie obraz"))

        message = str(error.value)
        assert message and message[0].isupper()
        assert "Traceback" not in message and "PIL" not in message

    def test_file_over_the_size_limit(self):
        upload = FakeUpload(jpeg())
        upload.size = MAX_UPLOAD_BYTES + 1

        with pytest.raises(InvalidImage):
            process_upload(upload)

    def test_pixel_bomb_is_rejected_although_the_file_is_tiny(self, monkeypatch):
        """Measured: a 3000×3000 PNG weighs under 10 kB. The byte limit cannot catch this."""
        monkeypatch.setattr("trees.images.MAX_PIXELS", 1_000_000)
        data = png(size=(3000, 3000), mode="L")
        assert len(data) < MAX_UPLOAD_BYTES, "Materiał musi przechodzić limit bajtów"

        with pytest.raises(InvalidImage):
            process_upload(FakeUpload(data, name="bomba.png"))


class TestColours:
    def test_transparency_becomes_white_not_black(self):
        """`convert("RGB")` alone turns see-through pixels black — the photo looks broken."""
        buffer = io.BytesIO()
        Image.new("RGBA", (100, 100), (255, 0, 0, 0)).save(buffer, "PNG")

        corner = opened(process_upload(FakeUpload(buffer.getvalue(), name="a.png"))).getpixel(
            (0, 0)
        )

        assert corner == (255, 255, 255)

    def test_greyscale_photo_survives(self):
        processed = process_upload(FakeUpload(jpeg(mode="L", colour=128), name="szare.jpg"))

        assert opened(processed).mode == "RGB"


def test_result_is_smaller_than_a_raw_phone_photo():
    """The point of the whole module: a card opened on mobile data stays light."""
    big = jpeg(size=(4032, 3024), colour="darkgreen")

    processed = process_upload(FakeUpload(big))

    assert processed.file.size < len(big)


def test_helpers_produce_what_the_tests_claim():
    """Guards the test material itself: without real EXIF, test_exif_is_gone proves nothing."""
    image = Image.open(io.BytesIO(jpeg(size=(600, 400), exif=with_gps_and_rotation)))

    assert image.getexif()[ORIENTATION] == 6
    assert ImageOps.exif_transpose(image).size == (400, 600)
