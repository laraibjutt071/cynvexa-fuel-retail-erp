import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio

# Minimal-but-genuine magic-byte prefixes - enough for the real format
# sniffing in app/core/storage.py to accept them, without needing a full
# valid image/PDF body.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF_BYTES = b"%PDF-1.4\n" + b"\x00" * 32


def _receipt_payload(tank, supplier, **overrides):
    payload = {
        "tank_id": str(tank.id),
        "supplier_id": str(supplier.id),
        "tanker_registration": "TRK-ATT",
        "invoice_quantity": "10000",
        "pre_receipt_tank_reading": "2000",
    }
    payload.update(overrides)
    return payload


async def _create_receipt(client: AsyncClient, token: str, org, station, tank, supplier) -> str:
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    resp = await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _attachments_url(org, station, receipt_id) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/tanker-receipts/{receipt_id}/attachments"


async def test_valid_png_upload_succeeds_and_is_listed(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = await _create_receipt(client, token, org, station, tank, supplier)

    upload = await client.post(
        _attachments_url(org, station, receipt_id),
        files={"file": ("evidence.png", PNG_BYTES, "image/png")},
        headers=auth_headers(token),
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["content_type"] == "image/png"
    assert upload.json()["size_bytes"] == len(PNG_BYTES)

    listing = await client.get(_attachments_url(org, station, receipt_id), headers=auth_headers(token))
    assert listing.status_code == 200
    assert len(listing.json()) == 1


async def test_valid_pdf_upload_succeeds(client: AsyncClient, owner_user, org, station, tank, supplier):
    token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = await _create_receipt(client, token, org, station, tank, supplier)

    upload = await client.post(
        _attachments_url(org, station, receipt_id),
        files={"file": ("invoice.pdf", PDF_BYTES, "application/pdf")},
        headers=auth_headers(token),
    )
    assert upload.status_code == 201, upload.text


async def test_disallowed_content_type_is_rejected(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = await _create_receipt(client, token, org, station, tank, supplier)

    upload = await client.post(
        _attachments_url(org, station, receipt_id),
        files={"file": ("script.js", b"alert(1)", "application/javascript")},
        headers=auth_headers(token),
    )
    assert upload.status_code == 422
    assert "Unsupported file type" in upload.json()["detail"]


async def test_content_disguised_as_an_allowed_type_is_rejected(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    """
    A client can claim any Content-Type header regardless of what bytes it
    actually sends - this is exactly the kind of upload a stored-XSS or
    disguised-executable attack relies on. The real file contents must
    match the declared type's magic bytes, not just the header.
    """
    token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = await _create_receipt(client, token, org, station, tank, supplier)

    upload = await client.post(
        _attachments_url(org, station, receipt_id),
        files={"file": ("fake.png", b"<script>alert(1)</script>", "image/png")},
        headers=auth_headers(token),
    )
    assert upload.status_code == 422
    assert "do not match the declared type" in upload.json()["detail"]


async def test_empty_file_is_rejected(client: AsyncClient, owner_user, org, station, tank, supplier):
    token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = await _create_receipt(client, token, org, station, tank, supplier)

    upload = await client.post(
        _attachments_url(org, station, receipt_id),
        files={"file": ("empty.png", b"", "image/png")},
        headers=auth_headers(token),
    )
    assert upload.status_code == 422


async def test_oversized_file_is_rejected(
    client: AsyncClient, owner_user, org, station, tank, supplier, monkeypatch
):
    token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = await _create_receipt(client, token, org, station, tank, supplier)

    from app.core import storage

    monkeypatch.setattr(storage.settings, "max_upload_size_bytes", 10)

    upload = await client.post(
        _attachments_url(org, station, receipt_id),
        files={"file": ("evidence.png", PNG_BYTES, "image/png")},
        headers=auth_headers(token),
    )
    assert upload.status_code == 422
    assert "exceeds the maximum allowed size" in upload.json()["detail"]


async def test_path_traversal_filename_is_sanitized(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = await _create_receipt(client, token, org, station, tank, supplier)

    upload = await client.post(
        _attachments_url(org, station, receipt_id),
        files={"file": ("../../../../etc/passwd.png", PNG_BYTES, "image/png")},
        headers=auth_headers(token),
    )
    assert upload.status_code == 201, upload.text
    # The ORIGINAL filename is preserved as a display value (what the user
    # uploaded), but it must never be used as-is to build a filesystem
    # path - see app/core/storage.py::_sanitize_filename.
    assert upload.json()["original_filename"] == "../../../../etc/passwd.png"


async def test_cashier_cannot_upload_receipt_evidence(
    client: AsyncClient, owner_user, cashier_user, org, station, tank, supplier
):
    owner_token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = await _create_receipt(client, owner_token, org, station, tank, supplier)

    cashier_token = await login(client, "cashier@acmefuel-dev.com")
    upload = await client.post(
        _attachments_url(org, station, receipt_id),
        files={"file": ("evidence.png", PNG_BYTES, "image/png")},
        headers=auth_headers(cashier_token),
    )
    assert upload.status_code == 403
