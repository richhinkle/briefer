"""QR code — generate a scannable QR code from text, a URL, or WiFi credentials.

Prints a QR code image as a `Picture` item. In WiFi mode the payload uses the
standard ``WIFI:T:…;S:…;P:…;;`` encoding that Android and iOS auto-detect.

Requires the ``qrcode`` package (pure-Python, uses Pillow for rendering).
"""

from __future__ import annotations

from ..brief import Picture, Section, Text


def _wifi_payload(ssid: str, password: str = "", security: str = "WPA",
                  hidden: bool = False) -> str:
    """Build a WiFi QR payload (ZXing / Google Lens standard)."""
    def _esc(s: str) -> str:
        for ch in ("\\", ";", ",", '"', ":"):
            s = s.replace(ch, f"\\{ch}")
        return s

    h = "true" if hidden else "false"
    return f"WIFI:T:{security};S:{_esc(ssid)};P:{_esc(password)};H:{h};;"


def _make_qr(data: str, box_size: int = 4, border: int = 2):
    """Generate a QR code as a greyscale PIL Image."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("L")


def build(section_cfg, ctx) -> Section | None:
    title = section_cfg.title or "QR CODE"
    mode = section_cfg.get("mode", "text")
    label = section_cfg.get("label", "")

    if mode == "wifi":
        ssid = section_cfg.get("ssid", "")
        password = section_cfg.get("password", "")
        security = section_cfg.get("security", "WPA")
        hidden = section_cfg.get("hidden", False)
        if not ssid:
            return Section(title, [Text("(no SSID configured)")])
        payload = _wifi_payload(ssid, password, security, hidden)
        if not label:
            label = f"WiFi: {ssid}"
    else:
        payload = section_cfg.get("data", "")
        if not payload:
            return Section(title, [Text("(no data configured)")])

    img = _make_qr(payload)

    items: list = []
    if label:
        items.append(Text(label))
    items.append(Picture(img))
    return Section(title, items)
