"""DTOs de request/response (Pydantic) del feature `documents`. La subida
(`POST /documents`) es multipart (archivo + campos de formulario) — no lleva
DTO de request propio, sus campos se declaran como `Form(...)`/`File(...)`
directamente en `routes.py` (mismo criterio que el resto del ecosistema
FastAPI para endpoints con archivo)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DocumentDTO(BaseModel):
    id: str
    user_id: str
    category: str
    title: str
    period: Optional[str] = None
    mime_type: str
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    created_at: datetime


class DocumentListDTO(BaseModel):
    documents: list[DocumentDTO]
