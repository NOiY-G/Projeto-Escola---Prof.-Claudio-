import base64
import io

import qrcode


def qr_code_data_uri(texto):
    """QR Code em PNG, pronto para usar em <img src> (certificados e Pix)."""
    imagem = qrcode.make(texto, box_size=10, border=1)
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
