"""
Tests de `GoogleDriveClient` y `build_credentials` — SIN red, SIN
credenciales reales. `googleapiclient.http.HttpMockSequence` sustituye el
transporte HTTP (`http=`) del `Resource` de discovery ESTÁTICO
(`static_discovery=True`, ya empaquetado para `drive` v3, así que `build()`
no hace ninguna llamada de red para construir el `Resource`) — es el mock
oficial del SDK, no `httpx.MockTransport` (ese cliente no usa httpx).

`HttpMockSequence.request_sequence` guarda `(uri, method, body, headers)`
de cada llamada — se usa para verificar que TODAS las llamadas van con la
semántica de Unidad compartida (`supportsAllDrives`, y en `list`
`includeItemsFromAllDrives`/`corpora`/`driveId`), no solo que no lancen.
"""

import json
from urllib.parse import parse_qs, urlparse

import pytest
from googleapiclient.discovery import build as build_drive_resource
from googleapiclient.http import HttpMockSequence

from src.features.documents.infrastructure.providers.google_drive_client import (
    GoogleDriveClient,
    build_credentials,
)

_ROOT_FOLDER_ID = "root-folder-123"


def _service_with_mock_sequence(responses: list) -> tuple:
    """`responses`: lista de `(headers, body)` (ver `HttpMockSequence`).
    Devuelve `(service, http_mock)` — el segundo para inspeccionar las
    llamadas hechas (`request_sequence`)."""
    http = HttpMockSequence(responses)
    service = build_drive_resource("drive", "v3", http=http, static_discovery=True)
    return service, http


def _query_param(uri: str, name: str) -> str:
    """`q` (y el resto de parámetros de `files.list`) llegan percent-encoded
    en la URI — se decodifican para comparar contra el literal de la query
    de Drive sin escapes de URL de por medio."""
    return parse_qs(urlparse(uri).query)[name][0]


# --- build_credentials ------------------------------------------------------


def test_build_credentials_desde_json_no_usa_with_subject(monkeypatch):
    captured: dict = {}

    def _fake_from_info(info, scopes=None, **kwargs):
        captured["info"] = info
        captured["scopes"] = scopes
        captured["kwargs"] = kwargs
        return "fake-credentials-from-json"

    monkeypatch.setattr(
        "src.features.documents.infrastructure.providers.google_drive_client"
        ".service_account.Credentials.from_service_account_info",
        _fake_from_info,
    )

    result = build_credentials(
        key_json=json.dumps({"client_email": "drive-sa@amelia.iam.gserviceaccount.com"}),
        key_path="",
    )

    assert result == "fake-credentials-from-json"
    assert captured["info"]["client_email"] == "drive-sa@amelia.iam.gserviceaccount.com"
    assert captured["scopes"] == ["https://www.googleapis.com/auth/drive"]
    # SIN Domain-Wide Delegation: `build_credentials` nunca pasa `subject=`
    # (decisión posterior del usuario, engram #450 — Shared Drive reemplaza DWD).
    assert "subject" not in captured["kwargs"]


def test_build_credentials_desde_path_no_usa_with_subject(monkeypatch):
    captured: dict = {}

    def _fake_from_file(filename, scopes=None, **kwargs):
        captured["filename"] = filename
        captured["scopes"] = scopes
        captured["kwargs"] = kwargs
        return "fake-credentials-from-file"

    monkeypatch.setattr(
        "src.features.documents.infrastructure.providers.google_drive_client"
        ".service_account.Credentials.from_service_account_file",
        _fake_from_file,
    )

    result = build_credentials(key_json="", key_path="/etc/secrets/drive-sa.json")

    assert result == "fake-credentials-from-file"
    assert captured["filename"] == "/etc/secrets/drive-sa.json"
    assert "subject" not in captured["kwargs"]


def test_build_credentials_sin_key_json_ni_key_path_falla_explicito():
    with pytest.raises(ValueError, match="Service Account"):
        build_credentials(key_json="", key_path="")


def test_build_credentials_prioriza_key_json_sobre_key_path(monkeypatch):
    monkeypatch.setattr(
        "src.features.documents.infrastructure.providers.google_drive_client"
        ".service_account.Credentials.from_service_account_info",
        lambda info, scopes=None, **kwargs: "from-json",
    )
    monkeypatch.setattr(
        "src.features.documents.infrastructure.providers.google_drive_client"
        ".service_account.Credentials.from_service_account_file",
        lambda filename, scopes=None, **kwargs: "from-file",
    )

    result = build_credentials(key_json='{"client_email": "x"}', key_path="/some/path.json")

    assert result == "from-json"


# --- find_folder_by_name ----------------------------------------------------


def test_find_folder_by_name_incluye_flags_de_shared_drive():
    service, http = _service_with_mock_sequence(
        [({"status": "200"}, json.dumps({"files": [{"id": "folder-abc", "name": "ana@ameliahub.com"}]}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    folder_id = client.find_folder_by_name("ana@ameliahub.com")

    assert folder_id == "folder-abc"
    uri = http.request_sequence[0][0]
    assert "supportsAllDrives=true" in uri
    assert "includeItemsFromAllDrives=true" in uri
    assert "corpora=drive" in uri
    assert f"driveId={_ROOT_FOLDER_ID}" in uri


def test_find_folder_by_name_devuelve_none_si_no_hay_resultados():
    service, _http = _service_with_mock_sequence(
        [({"status": "200"}, json.dumps({"files": []}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    folder_id = client.find_folder_by_name("nadie@ameliahub.com")

    assert folder_id is None


def test_find_folder_by_name_sin_parent_busca_bajo_la_raiz():
    service, http = _service_with_mock_sequence(
        [({"status": "200"}, json.dumps({"files": []}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    client.find_folder_by_name("ana@ameliahub.com")

    uri = http.request_sequence[0][0]
    assert f"'{_ROOT_FOLDER_ID}' in parents" in _query_param(uri, "q")


def test_find_folder_by_name_con_parent_busca_bajo_esa_subcarpeta_no_la_raiz():
    # Subcarpetas de categoría (Nóminas/Contratos/...): la búsqueda debe ir
    # bajo la carpeta del empleado (`parent_id`), NO bajo la raíz de la
    # Unidad compartida.
    service, http = _service_with_mock_sequence(
        [({"status": "200"}, json.dumps({"files": [{"id": "subcarpeta-nominas", "name": "Nóminas"}]}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    folder_id = client.find_folder_by_name("Nóminas", parent_id="folder-empleado-1")

    assert folder_id == "subcarpeta-nominas"
    uri = http.request_sequence[0][0]
    assert "'folder-empleado-1' in parents" in _query_param(uri, "q")
    # `driveId` (la Unidad compartida) sigue siendo la raíz, nunca el
    # `parent_id` — son conceptos distintos (ver docstring del método).
    assert f"driveId={_ROOT_FOLDER_ID}" in uri


# --- create_folder -----------------------------------------------------------


def test_create_folder_incluye_flag_de_shared_drive():
    service, http = _service_with_mock_sequence(
        [({"status": "200"}, json.dumps({"id": "folder-nueva-1"}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    folder_id = client.create_folder("luis.perez@ameliahub.com")

    assert folder_id == "folder-nueva-1"
    assert "supportsAllDrives=true" in http.request_sequence[0][0]


def test_create_folder_sin_parent_la_crea_bajo_la_raiz():
    service, http = _service_with_mock_sequence(
        [({"status": "200"}, json.dumps({"id": "folder-nueva-1"}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    client.create_folder("luis.perez@ameliahub.com")

    body = json.loads(http.request_sequence[0][2])
    assert body["parents"] == [_ROOT_FOLDER_ID]


def test_create_folder_con_parent_la_crea_bajo_esa_subcarpeta_no_la_raiz():
    service, http = _service_with_mock_sequence(
        [({"status": "200"}, json.dumps({"id": "subcarpeta-nominas-1"}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    folder_id = client.create_folder("Nóminas", parent_id="folder-empleado-1")

    assert folder_id == "subcarpeta-nominas-1"
    body = json.loads(http.request_sequence[0][2])
    assert body["parents"] == ["folder-empleado-1"]
    assert "supportsAllDrives=true" in http.request_sequence[0][0]


# --- upload_file -------------------------------------------------------------


def test_upload_file_multipart_simple_incluye_flag_de_shared_drive():
    service, http = _service_with_mock_sequence(
        [({"status": "200"}, json.dumps({"id": "file-1", "md5Checksum": "abc123"}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    drive_file_id, content_hash = client.upload_file(
        folder_id="folder-abc",
        filename="NOMINA_2026-06_ana.pdf",
        content=b"contenido pequeno",
        mime_type="application/pdf",
    )

    assert drive_file_id == "file-1"
    assert content_hash == "abc123"
    assert len(http.request_sequence) == 1
    assert "supportsAllDrives=true" in http.request_sequence[0][0]


def test_upload_file_usa_resumable_al_superar_el_umbral(monkeypatch):
    # Se baja el umbral a 1 byte en vez de generar >5MB reales de contenido.
    monkeypatch.setattr(
        "src.features.documents.infrastructure.providers.google_drive_client"
        "._RESUMABLE_THRESHOLD_BYTES",
        1,
    )
    service, http = _service_with_mock_sequence(
        [
            ({"status": "200", "location": "http://example.com/upload/session-1"}, ""),
            ({"status": "200"}, json.dumps({"id": "file-resumable-1", "md5Checksum": "def456"})),
        ]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    drive_file_id, content_hash = client.upload_file(
        folder_id="folder-abc",
        filename="CONTRATO_luis.pdf",
        content=b"contenido mas largo que el umbral",
        mime_type="application/pdf",
    )

    assert drive_file_id == "file-resumable-1"
    assert content_hash == "def456"
    # Sesión resumible (POST inicial) + subida del contenido (PUT) = 2 llamadas.
    assert len(http.request_sequence) == 2
    assert "supportsAllDrives=true" in http.request_sequence[0][0]


# --- download_file -----------------------------------------------------------


def test_download_file_incluye_flag_de_shared_drive():
    service, http = _service_with_mock_sequence(
        [({"status": "200"}, b"contenido binario del pdf")]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    content = client.download_file("file-1")

    assert content == b"contenido binario del pdf"
    assert "supportsAllDrives=true" in http.request_sequence[0][0]


def test_download_file_404_propaga_http_error():
    from googleapiclient.errors import HttpError

    service, _http = _service_with_mock_sequence(
        [({"status": "404"}, json.dumps({"error": {"message": "File not found"}}))]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    with pytest.raises(HttpError) as exc_info:
        client.download_file("no-existe")

    assert exc_info.value.resp.status == 404


# --- list_files_in_folder ----------------------------------------------------


def test_list_files_in_folder_incluye_flags_de_shared_drive():
    service, http = _service_with_mock_sequence(
        [
            (
                {"status": "200"},
                json.dumps(
                    {
                        "files": [
                            {
                                "id": "file-1",
                                "name": "NOMINA_2026-06_ana.pdf",
                                "mimeType": "application/pdf",
                                "size": "1024",
                                "md5Checksum": "abc123",
                            }
                        ]
                    }
                ),
            )
        ]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    files = client.list_files_in_folder("folder-abc")

    assert len(files) == 1
    assert files[0]["id"] == "file-1"
    uri = http.request_sequence[0][0]
    assert "supportsAllDrives=true" in uri
    assert "includeItemsFromAllDrives=true" in uri
    assert "corpora=drive" in uri
    assert f"driveId={_ROOT_FOLDER_ID}" in uri


def test_list_files_in_folder_pagina_hasta_agotar_next_page_token():
    service, _http = _service_with_mock_sequence(
        [
            (
                {"status": "200"},
                json.dumps(
                    {
                        "nextPageToken": "page-2",
                        "files": [{"id": "file-1", "name": "a.pdf", "mimeType": "application/pdf"}],
                    }
                ),
            ),
            (
                {"status": "200"},
                json.dumps(
                    {"files": [{"id": "file-2", "name": "b.pdf", "mimeType": "application/pdf"}]}
                ),
            ),
        ]
    )
    client = GoogleDriveClient(None, root_folder_id=_ROOT_FOLDER_ID, service=service)

    files = client.list_files_in_folder("folder-abc")

    assert {f["id"] for f in files} == {"file-1", "file-2"}
