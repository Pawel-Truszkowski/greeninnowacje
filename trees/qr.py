"""QR codes for tree cards (spec §4): generated on demand, never written to disk."""

import io

import qrcode
from django.conf import settings
from django.urls import reverse

BRAND_GREEN = "#135133"


def tree_card_url(tree_id):
    return f"{settings.APP_BASE_URL}{reverse('trees:card', kwargs={'tree_id': tree_id})}"


def qr_png(url, box_size=8):
    code = qrcode.QRCode(box_size=box_size, border=2)
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(fill_color=BRAND_GREEN, back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
