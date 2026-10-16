"""중간 인증서를 보내지 않는 학교 서버용 인증서 보완.

일부 학교 서버는 서버 인증서만 보내고 중간 인증서를 빠뜨려서, 브라우저(중간 인증서를 스스로 받아 옴)에서는 열리지만
파이썬 requests 에서는 인증서 오류가 난다. 서버 인증서에 적힌 발급기관 주소(AIA, CA Issuers)에서 중간 인증서를 받아
신뢰 루트(certifi)와 함께 묶은 파일로 '다시 검증'한다. 검증을 끄지 않는다.
"""
from __future__ import annotations

import socket
import ssl
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import requests

_cache: dict[str, str | None] = {}
_lock = threading.Lock()


def _leaf_der(host: str, port: int) -> bytes:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # 서버 인증서를 '읽기만' 한다 (검증은 아래에서 묶음 파일로 다시 한다)
    with socket.create_connection((host, port), timeout=10) as s, ctx.wrap_socket(s, server_hostname=host) as t:
        return t.getpeercert(binary_form=True)


def _issuer_pems(der: bytes, depth: int = 3) -> list[str]:
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID
    out = []
    cert = x509.load_der_x509_certificate(der)
    for _ in range(depth):
        try:
            aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
        except x509.ExtensionNotFound:
            break
        urls = [d.access_location.value for d in aia if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS]
        if not urls or not urls[0].startswith("http"):
            break
        raw = requests.get(urls[0], timeout=15).content
        try:
            cert = x509.load_der_x509_certificate(raw)
        except ValueError:
            cert = x509.load_pem_x509_certificate(raw)
        out.append(cert.public_bytes(Encoding.PEM).decode())
        if cert.issuer == cert.subject:
            break
    return out


def bundle_for(url: str) -> str | None:
    """그 서버용 인증서 묶음 파일 경로 (못 만들면 None)."""
    p = urlparse(url)
    host, port = p.hostname or "", p.port or 443
    key = f"{host}:{port}"
    with _lock:
        if key in _cache:
            return _cache[key]
    path = None
    try:
        pems = _issuer_pems(_leaf_der(host, port))
        if pems:
            import certifi
            f = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
            f.write(Path(certifi.where()).read_text() + "\n" + "\n".join(pems))
            f.close()
            path = f.name
    except Exception:  # noqa: BLE001
        path = None
    with _lock:
        _cache[key] = path
    return path


def get(url: str, **kw) -> requests.Response:
    """requests.get 과 같지만, 중간 인증서가 빠진 서버면 보완한 묶음으로 한 번 더 '검증해서' 연다."""
    try:
        return requests.get(url, **kw)
    except requests.exceptions.SSLError:
        b = bundle_for(url)
        if not b:
            raise
        return requests.get(url, verify=b, **kw)
