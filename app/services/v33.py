"""V33 (14-nov-2026): verificación de la guía firmada que adjunta el conductor en la conformidad de entrega."""
import re

from .core import BusinessError


def norm_guia(t):
    """«T001-00012345», «t001 12345» → («T001», 12345). None si no tiene forma de guía."""
    t = (t or "").upper().strip()
    solo = re.fullmatch(r"0*(\d{1,10})", t)
    if solo:
        return "", int(solo.group(1))
    m = re.search(r"([A-Z]{1,2}\d{2,4}|\d{3,4})\s*[-–]?\s*0*(\d{1,10})\b", t)
    if m:
        return m.group(1), int(m.group(2))
    return None


def misma_guia(a, b):
    x, y = norm_guia(a), norm_guia(b)
    if not x or not y:
        return False
    return x[1] == y[1] and (not x[0] or not y[0] or x[0] == y[0])


def verificar_guia_firmada(stop, archivo, numero):
    """El conductor adjunta solo la guía de remisión firmada de la parada: imagen o PDF, con el número de la guía. Si la
    parada tiene número de guía, debe coincidir; si es PDF con texto, el número debe aparecer en el documento."""
    if archivo is None or not getattr(archivo, "filename", ""):
        raise BusinessError("Adjunte la guía de remisión firmada (foto o PDF).")
    nombre = archivo.filename.lower()
    tipo = (getattr(archivo, "mimetype", "") or "").lower()
    es_pdf = nombre.endswith(".pdf") or tipo == "application/pdf"
    if not (es_pdf or tipo.startswith("image/") or nombre.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic"))):
        raise BusinessError("La guía firmada debe ser una foto o un PDF de la guía de remisión.")
    numero = (numero or "").strip()
    if not norm_guia(numero):
        raise BusinessError("Escriba el número de la guía que adjunta (p. ej. T001-12345).")
    esperado = (stop.guia_numero or "").strip()
    if esperado and not misma_guia(numero, esperado):
        raise BusinessError(f"La guía que adjunta ({numero}) no es la de esta entrega ({esperado}). Adjunte la guía "
                            "firmada que corresponde.")
    if es_pdf:
        try:
            from io import BytesIO
            from pypdf import PdfReader
            pos = archivo.stream.tell()
            texto = " ".join((p.extract_text() or "") for p in PdfReader(BytesIO(archivo.read())).pages[:3])
            archivo.stream.seek(pos)
        except Exception:  # noqa: BLE001  (PDF escaneado o dañado: se acepta con el número digitado)
            texto = ""
            try:
                archivo.stream.seek(0)
            except Exception:  # noqa: BLE001
                pass
        if texto.strip():
            g = norm_guia(numero)
            nums = [norm_guia(x) for x in re.findall(r"[A-Z]{0,2}\d{2,4}\s*[-–]\s*\d{1,10}", texto.upper())]
            if not any(n and n[1] == g[1] for n in nums):
                raise BusinessError(f"El PDF adjunto no es la guía {numero}: no aparece ese número en el documento.")
    if not esperado:
        stop.guia_numero = numero[:40]
    return True
