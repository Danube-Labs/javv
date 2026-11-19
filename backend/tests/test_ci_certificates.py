"""The test certificates of development/scripts/make-test-certs.sh pass the strict check of Python.

Since Python 3.13, ssl.create_default_context() sets VERIFY_X509_STRICT, and both opensearch-py and
httpx make their TLS contexts with it (issue 1263). The cases set the flag themselves, so they hold
the same rule on any Python version.
"""

import socket
import ssl
import subprocess
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "development/scripts/make-test-certs.sh"
SERVICE = "javv-opensearch"


def handshake(ca: Path, crt: Path, key: Path) -> None:
    """A TLS handshake on a socket pair: the server shows crt, the client checks it strictly."""
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.load_cert_chain(crt, key)
    client = ssl.create_default_context(cafile=str(ca))
    client.verify_flags |= ssl.VERIFY_X509_STRICT
    a, b = socket.socketpair()
    a.settimeout(10)
    b.settimeout(10)

    def serve() -> None:
        try:
            server.wrap_socket(a, server_side=True).close()
        except (ssl.SSLError, OSError):
            a.close()

    thread = threading.Thread(target=serve)
    thread.start()
    try:
        client.wrap_socket(b, server_hostname=SERVICE).close()
    finally:
        b.close()
        thread.join()


def openssl(args: list[str]) -> None:
    subprocess.run(["openssl", *args], check=True, capture_output=True)


@pytest.fixture(scope="module")
def certs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("certs")
    subprocess.run(["bash", str(SCRIPT), str(out), SERVICE, "javv-ci"], check=True)
    return out


def test_the_node_certificate_passes_the_strict_check(certs: Path) -> None:
    handshake(certs / "ca.crt", certs / "tls.crt", certs / "tls.key")


def test_a_ca_without_key_usage_fails_the_same_check(certs: Path, tmp_path: Path) -> None:
    """The CA of the CI before issue 1263. The check must refuse it, or it checks nothing."""
    ca_key, ca_crt, crt = tmp_path / "ca.key", tmp_path / "ca.crt", tmp_path / "tls.crt"
    openssl(
        ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=javv-ci-ca"]
        + ["-keyout", str(ca_key), "-out", str(ca_crt)]
    )
    openssl(
        ["x509", "-req", "-in", str(certs / "tls.csr"), "-days", "2", "-out", str(crt)]
        + ["-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial"]
        + ["-extfile", str(certs / "ext")]
    )
    with pytest.raises(ssl.SSLCertVerificationError, match="key usage"):
        handshake(ca_crt, crt, certs / "tls.key")
