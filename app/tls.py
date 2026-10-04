"""HTTPS for a LAN app that has no public domain name.

The app runs its own tiny certificate authority (CA). On first start it creates the CA and
a server certificate signed by it, under data/certs/. Each device trusts the CA once (the
/setup page walks through it), after which https://<LAN_HOSTNAME>:<PORT> gets a normal
padlock in every browser.

Rules:
- Keys are EC P-256. The server certificate lasts 365 days and is re-issued automatically
  30 days before it expires, or whenever the names it must cover change (a new
  LAN_HOSTNAME or LAN IP). iOS refuses server certificates valid for more than 825 days.
- The CA lasts 10 years. If it is ever replaced, every device must trust it again.
- Private keys never leave data/certs/. Keep that folder private.
"""

from __future__ import annotations

import ipaddress
import logging
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.config import valid_hostname
from app.netinfo import lan_ip, machine_name

if TYPE_CHECKING:
    from app.config import Settings

log = logging.getLogger("kickoff.tls")

CA_DAYS = 3650
SERVER_DAYS = 365
RENEW_BEFORE_DAYS = 30
CA_COMMON_NAME = "Kickoff Companion Local CA"
ORGANIZATION = "Kickoff Companion"
CA_CERT_FILE = "ca.crt"
CA_KEY_FILE = "ca.key"
SERVER_CERT_FILE = "server.crt"
SERVER_KEY_FILE = "server.key"
CA_DOWNLOAD_NAME = "kickoff-companion-ca.crt"
CA_MEDIA_TYPE = "application/x-x509-ca-cert"


@dataclass(frozen=True)
class CertificateInfo:
    """What the rest of the app needs to know about a certificate. No key material."""

    subject: str
    not_before: datetime
    not_after: datetime
    dns_names: tuple[str, ...]
    ip_addresses: tuple[str, ...]
    fingerprint_sha256: str

    def days_left(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (self.not_after - now).total_seconds() / 86400

    @property
    def names(self) -> tuple[str, ...]:
        return self.dns_names + self.ip_addresses

    def summary(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "not_before": _iso(self.not_before),
            "not_after": _iso(self.not_after),
            "days_left": round(self.days_left(), 1),
            "dns_names": list(self.dns_names),
            "ip_addresses": list(self.ip_addresses),
            "fingerprint_sha256": self.fingerprint_sha256,
        }


# --- what the certificate must cover -----------------------------------------------


def planned_names(settings: Settings) -> tuple[list[str], list[str]]:
    """DNS names and IP addresses the server certificate must cover right now."""
    dns: list[str] = []
    if settings.lan_hostname:
        dns.append(settings.lan_hostname)
    if settings.mdns_host:
        dns.append(settings.mdns_host)  # the name the server announces (app/services/mdns.py)
    # The machine's own name, first label only: a Mac reports "Name.local" (public release Phase 9: macOS CI),
    # and a DNS label is at most 63 characters.
    machine = machine_name().strip().lower().split(".", 1)[0]
    if machine and len(machine) <= 63 and valid_hostname(machine):
        dns.append(machine)
        if "." in settings.lan_hostname:
            suffix = settings.lan_hostname.split(".", 1)[1]
            dns.append(f"{machine}.{suffix}")
    dns.append("localhost")

    ips: list[str] = []
    ip = lan_ip()
    if ip:
        ips.append(ip)
    ips.append("127.0.0.1")
    return _dedupe(dns), _dedupe(ips)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


# --- creating and checking certificates ----------------------------------------------


def ensure_certificates(
    cert_dir: Path,
    dns_names: list[str],
    ip_addresses: list[str],
    *,
    now: datetime | None = None,
) -> tuple[CertificateInfo, CertificateInfo, list[str]]:
    """Create or renew the CA and the server certificate as needed.

    Returns (ca_info, server_info, actions). `actions` lists what changed, in plain words,
    and is empty when everything on disk was already fine.
    """
    now = now or datetime.now(timezone.utc)
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_key_path, ca_cert_path = cert_dir / CA_KEY_FILE, cert_dir / CA_CERT_FILE
    server_key_path, server_cert_path = cert_dir / SERVER_KEY_FILE, cert_dir / SERVER_CERT_FILE
    actions: list[str] = []

    ca_key, ca_cert, ca_problem = _load_pair(ca_key_path, ca_cert_path)
    if ca_cert is not None and _expiring(ca_cert, now):
        ca_problem = "it is about to expire"

    server_key = server_cert = None
    server_problem: str | None = None
    if ca_problem is not None:
        had_ca = ca_key_path.exists() or ca_cert_path.exists()
        ca_key, ca_cert = _make_ca(now)
        _write_key(ca_key_path, ca_key)
        _write_certs(ca_cert_path, ca_cert)
        if had_ca:
            actions.append(f"replaced the certificate authority ({ca_problem}); every device must trust the new one")
            server_problem = "the certificate authority changed"
        else:
            actions.append("created the certificate authority")
            server_problem = "first start"
    else:
        server_key, server_cert, server_problem = _load_pair(server_key_path, server_cert_path)
        if server_cert is not None:
            server_problem = _server_problem(server_cert, ca_cert, dns_names, ip_addresses, now)

    if server_problem is not None:
        assert ca_key is not None and ca_cert is not None
        server_key, server_cert = _make_server(now, ca_key, ca_cert, dns_names, ip_addresses)
        _write_key(server_key_path, server_key)
        _write_certs(server_cert_path, server_cert, ca_cert)
        actions.append(f"issued a server certificate ({server_problem})")

    assert ca_cert is not None and server_cert is not None
    return _info(ca_cert), _info(server_cert), actions


def describe_certificates(cert_dir: Path) -> str:
    """One line for `--check`. Reads only; never creates anything."""
    cert_path = cert_dir / SERVER_CERT_FILE
    if not cert_path.exists():
        return f"certificates will be created in {cert_dir} at first start"
    try:
        info = _info(_load_cert(cert_path))
    except (OSError, ValueError) as exc:
        return f"server certificate unreadable, will be re-issued at start ({exc})"
    return f"certificate for {', '.join(info.names)} valid until {info.not_after.date()} ({info.days_left():.0f} days)"


def _load_pair(key_path: Path, cert_path: Path) -> tuple[Any, x509.Certificate | None, str | None]:
    if not key_path.exists() and not cert_path.exists():
        return None, None, "no certificate yet"
    try:
        key = _load_key(key_path)
        cert = _load_cert(cert_path)
    except (OSError, ValueError, TypeError) as exc:
        return None, None, f"the existing files could not be read: {exc}"
    if _spki(key.public_key()) != _spki(cert.public_key()):
        return None, None, "the key on disk does not match the certificate"
    return key, cert, None


def _server_problem(
    cert: x509.Certificate,
    ca_cert: x509.Certificate | None,
    dns_names: list[str],
    ip_addresses: list[str],
    now: datetime,
) -> str | None:
    if ca_cert is None:
        return "there is no certificate authority"
    try:
        cert.verify_directly_issued_by(ca_cert)
    except (ValueError, TypeError, InvalidSignature):
        return "it was not issued by the current certificate authority"
    days = (cert.not_valid_after_utc - now).total_seconds() / 86400
    if days <= 0:
        return "it has expired"
    if days < RENEW_BEFORE_DAYS:
        return f"it expires in {days:.0f} days"
    info = _info(cert)
    if set(info.dns_names) != set(dns_names) or set(info.ip_addresses) != set(ip_addresses):
        return "the names it covers changed"
    return None


def _expiring(cert: x509.Certificate, now: datetime) -> bool:
    return cert.not_valid_after_utc - now < timedelta(days=RENEW_BEFORE_DAYS)


def _make_ca(now: datetime) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, CA_COMMON_NAME),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZATION),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=CA_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _make_server(
    now: datetime,
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cert: x509.Certificate,
    dns_names: list[str],
    ip_addresses: list[str],
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = ec.generate_private_key(ec.SECP256R1())
    # The subject's common name is only a label (clients check the alternative names) and may be 64 characters
    # at most: the first name that fits, else the first address.
    common_name = next((name for name in dns_names if len(name) <= 64), ip_addresses[0] if ip_addresses else "localhost")
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZATION),
        ]
    )
    alt_names: list[x509.GeneralName] = [x509.DNSName(name) for name in dns_names]
    alt_names += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ip_addresses]
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=SERVER_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=False,
                crl_sign=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


# --- files -----------------------------------------------------------------------------


def _load_key(path: Path) -> Any:
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def _load_cert(path: Path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def _write_key(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def _write_certs(path: Path, *certs: x509.Certificate) -> None:
    path.write_bytes(b"".join(cert.public_bytes(serialization.Encoding.PEM) for cert in certs))


def _spki(public_key: Any) -> bytes:
    return public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def _info(cert: x509.Certificate) -> CertificateInfo:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        dns = tuple(san.get_values_for_type(x509.DNSName))
        ips = tuple(str(ip) for ip in san.get_values_for_type(x509.IPAddress))
    except x509.ExtensionNotFound:
        dns, ips = (), ()
    fingerprint = ":".join(f"{byte:02X}" for byte in cert.fingerprint(hashes.SHA256()))
    return CertificateInfo(
        subject=cert.subject.rfc4514_string(),
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        dns_names=dns,
        ip_addresses=ips,
        fingerprint_sha256=fingerprint,
    )


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --- the live state the server uses ---------------------------------------------------


@dataclass
class TlsState:
    """The certificates in use plus the SSL context the listener hands to TLS connections."""

    cert_dir: Path
    ca: CertificateInfo
    server: CertificateInfo
    context: ssl.SSLContext

    @classmethod
    def existing(cls, settings: Settings, *, now: datetime | None = None) -> TlsState | None:
        """With HTTPS off (public release Phase 4b): the certificates of an install that had HTTPS on,
        kept so its devices' https:// bookmarks still answer (with a redirect to http://). None when
        there are none; nothing new is ever created."""
        cert_dir = settings.data_dir / "certs"
        if not ((cert_dir / CA_CERT_FILE).is_file() and (cert_dir / CA_KEY_FILE).is_file()):
            return None
        return cls.prepare(settings, now=now)

    @classmethod
    def prepare(cls, settings: Settings, *, now: datetime | None = None) -> TlsState:
        """Make sure valid certificates exist for the current names, then load them."""
        dns, ips = planned_names(settings)
        cert_dir = settings.data_dir / "certs"
        ca, server, actions = ensure_certificates(cert_dir, dns, ips, now=now)
        _log_actions(actions)
        return cls(cert_dir=cert_dir, ca=ca, server=server, context=_server_context(cert_dir))

    def refresh(self, settings: Settings, *, now: datetime | None = None) -> bool:
        """Re-check names and expiry. Re-issues and hot-loads the certificate when needed.

        Returns True when the certificate in use changed.
        """
        dns, ips = planned_names(settings)
        ca, server, actions = ensure_certificates(self.cert_dir, dns, ips, now=now)
        _log_actions(actions)
        changed = (
            server.fingerprint_sha256 != self.server.fingerprint_sha256
            or ca.fingerprint_sha256 != self.ca.fingerprint_sha256
        )
        if changed:
            self.context.load_cert_chain(str(self.server_cert_path), str(self.server_key_path))
            self.ca, self.server = ca, server
            log.info("TLS: new server certificate in use, valid until %s", server.not_after.date())
        return changed

    @property
    def ca_cert_path(self) -> Path:
        return self.cert_dir / CA_CERT_FILE

    @property
    def server_cert_path(self) -> Path:
        return self.cert_dir / SERVER_CERT_FILE

    @property
    def server_key_path(self) -> Path:
        return self.cert_dir / SERVER_KEY_FILE

    def summary(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "cert_dir": str(self.cert_dir),
            "ca": {"name": CA_COMMON_NAME, **self.ca.summary()},
            "server": self.server.summary(),
        }


def _server_context(cert_dir: Path) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert_dir / SERVER_CERT_FILE), str(cert_dir / SERVER_KEY_FILE))
    return context


def _log_actions(actions: list[str]) -> None:
    for action in actions:
        if action.startswith("replaced the certificate authority"):
            log.warning("TLS: %s", action)
        else:
            log.info("TLS: %s", action)
