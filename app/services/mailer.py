"""Envío de correos de la bandeja de salida.

Requiere variables de entorno SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS.
Sin SMTP_HOST los correos quedan marcados SIN_SMTP: la dependencia se documenta y NO se simula el envío.
"""
import os
import smtplib
from email.message import EmailMessage

from sqlalchemy import select

from ..db import db
from ..models import EmailOutbox, now


def smtp_configured():
    return bool(os.environ.get("SMTP_HOST"))


def flush_outbox(limit=200):
    s = db()
    pending = list(s.execute(select(EmailOutbox).where(EmailOutbox.estado.in_(["PENDIENTE", "SIN_SMTP"]))
                             .limit(limit)).scalars())
    if not pending:
        return {"enviados": 0, "errores": 0, "sin_smtp": 0}
    if not smtp_configured():
        for m in pending:
            m.estado = "SIN_SMTP"
            m.error = "SMTP no configurado (variable SMTP_HOST vacía). Correo no enviado."
        return {"enviados": 0, "errores": 0, "sin_smtp": len(pending)}
    sent = err = 0
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    try:
        server = smtplib.SMTP(host, port, timeout=20)
        if os.environ.get("SMTP_TLS", "1") == "1":
            server.starttls()
        if os.environ.get("SMTP_USER"):
            server.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
    except Exception as e:  # noqa: BLE001
        for m in pending:
            m.estado = "ERROR"
            m.error = f"Conexión SMTP fallida: {e}"
        return {"enviados": 0, "errores": len(pending), "sin_smtp": 0}
    for m in pending:
        try:
            msg = EmailMessage()
            msg["From"] = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USER", "modulo-operaciones@localhost"))
            msg["To"] = m.destinatario
            msg["Subject"] = m.asunto
            msg.set_content(m.cuerpo)
            server.send_message(msg)
            m.estado = "ENVIADO"
            m.enviado_ts = now()
            m.error = ""
            sent += 1
        except Exception as e:  # noqa: BLE001
            m.estado = "ERROR"
            m.error = str(e)
            err += 1
    server.quit()
    return {"enviados": sent, "errores": err, "sin_smtp": 0}
