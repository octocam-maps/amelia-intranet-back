"""
Resolución de la IP real del cliente detrás de un proxy inverso. Crítico para
la firma digital trazable (document_signatures.ip_address) y para la clave
del rate-limiter del login (src/shared/middleware/rate_limiter.py).

SEC-1 (auditoría QA Fase 3): confiar en X-Forwarded-For/X-Real-IP sin validar
de dónde vienen permite que cualquier cliente falsee su IP con esas
cabeceras — saltándose el rate-limit del login y falseando
auth_sessions.ip_address/document_signatures.ip_address (rompe la
trazabilidad legal). Por defecto usamos `request.client.host` (la IP con la
que TCP conectó de verdad, imposible de falsear) y SOLO leemos las cabeceras
si esa conexión directa viene de un proxy en el que confiamos explícitamente
(`TRUSTED_PROXY_IPS`). Decisión del usuario: despliegue directo por ahora, así
que la allowlist queda vacía y las cabeceras se ignoran del todo.
"""

from fastapi import Request

from src.shared.config import get_settings


def get_client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"

    settings = get_settings()
    if direct_ip not in settings.trusted_proxy_ips:
        return direct_ip

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return direct_ip
