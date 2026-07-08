"""
Resolución de la IP real del cliente detrás de un proxy inverso. Crítico para
la firma digital trazable (document_signatures.ip_address) — nunca usar
`request.client.host` a pelo en producción, sería la IP del proxy.
"""

from fastapi import Request


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"
