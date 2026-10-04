"""The local certificate authority: created once, server certificate renewed on its own."""

from __future__ import annotations

import ssl
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID

from app.config import load_settings, valid_hostname
from app.netinfo import machine_name
from app.tls import (
    CA_CERT_FILE,
    CA_COMMON_NAME,
    CA_DAYS,
    CA_KEY_FILE,
    RENEW_BEFORE_DAYS,
    SERVER_CERT_FILE,
    SERVER_DAYS,
    SERVER_KEY_FILE,
    TlsState,
    describe_certificates,
    ensure_certificates,
    planned_names,
)
from tests.conftest import TEST_KEY

DNS = ["football.localdomain", "desktop", "localhost"]
IPS = ["192.0.2.105", "127.0.0.1"]
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def load(path) -> x509.Certificate:
    return x509.load_pem_x509_certificate(path.read_bytes())


def test_first_start_creates_ca_and_server_certificate(tmp_path):
    ca, server, actions = ensure_certificates(tmp_path, DNS, IPS, now=NOW)

    for name in (CA_CERT_FILE, CA_KEY_FILE, SERVER_CERT_FILE, SERVER_KEY_FILE):
        assert (tmp_path / name).exists()
    assert actions == ["created the certificate authority", "issued a server certificate (first start)"]
    assert set(server.dns_names) == set(DNS)
    assert set(server.ip_addresses) == set(IPS)
    assert server.days_left(NOW) == pytest.approx(SERVER_DAYS, abs=0.01)
    assert server.days_left(NOW) <= 825, "iOS rejects server certificates longer than 825 days"
    assert ca.days_left(NOW) == pytest.approx(CA_DAYS, abs=0.01)
    assert CA_COMMON_NAME in ca.subject
    assert len(server.fingerprint_sha256) == 95 and server.fingerprint_sha256.count(":") == 31

    leaf = load(tmp_path / SERVER_CERT_FILE)
    root = load(tmp_path / CA_CERT_FILE)
    leaf.verify_directly_issued_by(root)
    eku = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    assert ExtendedKeyUsageOID.SERVER_AUTH in eku
    assert leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False
    assert root.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    # server.crt carries the CA as well, so clients get the full chain.
    assert (tmp_path / SERVER_CERT_FILE).read_bytes().count(b"BEGIN CERTIFICATE") == 2
    assert b"PRIVATE" not in (tmp_path / SERVER_CERT_FILE).read_bytes()


def test_second_start_changes_nothing(tmp_path):
    ca1, server1, _ = ensure_certificates(tmp_path, DNS, IPS, now=NOW)
    ca2, server2, actions = ensure_certificates(tmp_path, DNS, IPS, now=NOW + timedelta(days=1))
    assert actions == []
    assert ca1 == ca2
    assert server1 == server2


def test_new_name_reissues_only_the_server_certificate(tmp_path):
    ca1, server1, _ = ensure_certificates(tmp_path, DNS, IPS, now=NOW)
    ca2, server2, actions = ensure_certificates(tmp_path, DNS + ["gameday.localdomain"], IPS, now=NOW)
    assert ca1 == ca2
    assert server2 != server1
    assert "gameday.localdomain" in server2.dns_names
    assert actions == ["issued a server certificate (the names it covers changed)"]


def test_new_ip_reissues_the_server_certificate(tmp_path):
    _, server1, _ = ensure_certificates(tmp_path, DNS, IPS, now=NOW)
    _, server2, actions = ensure_certificates(tmp_path, DNS, ["192.0.2.50", "127.0.0.1"], now=NOW)
    assert server2 != server1
    assert "192.0.2.50" in server2.ip_addresses
    assert actions == ["issued a server certificate (the names it covers changed)"]


def test_expiring_server_certificate_is_renewed(tmp_path):
    ca1, server1, _ = ensure_certificates(tmp_path, DNS, IPS, now=NOW)
    later = NOW + timedelta(days=SERVER_DAYS - RENEW_BEFORE_DAYS + 1)
    ca2, server2, actions = ensure_certificates(tmp_path, DNS, IPS, now=later)
    assert ca1 == ca2
    assert server2.not_after > server1.not_after
    assert len(actions) == 1 and "expires in" in actions[0]


def test_expired_server_certificate_is_renewed(tmp_path):
    _, server1, _ = ensure_certificates(tmp_path, DNS, IPS, now=NOW)
    _, server2, actions = ensure_certificates(tmp_path, DNS, IPS, now=NOW + timedelta(days=SERVER_DAYS + 5))
    assert server2.not_after > server1.not_after
    assert actions == ["issued a server certificate (it has expired)"]


def test_unreadable_server_files_are_replaced(tmp_path):
    ensure_certificates(tmp_path, DNS, IPS, now=NOW)
    (tmp_path / SERVER_CERT_FILE).write_text("not a certificate", encoding="utf-8")
    ca, server, actions = ensure_certificates(tmp_path, DNS, IPS, now=NOW)
    assert len(actions) == 1 and "could not be read" in actions[0]
    load(tmp_path / SERVER_CERT_FILE).verify_directly_issued_by(load(tmp_path / CA_CERT_FILE))


def test_server_certificate_from_a_foreign_ca_is_replaced(tmp_path):
    other, mine = tmp_path / "other", tmp_path / "mine"
    ensure_certificates(other, DNS, IPS, now=NOW)
    ensure_certificates(mine, DNS, IPS, now=NOW)
    for name in (SERVER_CERT_FILE, SERVER_KEY_FILE):
        (mine / name).write_bytes((other / name).read_bytes())
    _, _, actions = ensure_certificates(mine, DNS, IPS, now=NOW)
    assert actions == ["issued a server certificate (it was not issued by the current certificate authority)"]


def test_mismatched_key_is_replaced(tmp_path):
    other, mine = tmp_path / "other", tmp_path / "mine"
    ensure_certificates(other, DNS, IPS, now=NOW)
    ensure_certificates(mine, DNS, IPS, now=NOW)
    (mine / SERVER_KEY_FILE).write_bytes((other / SERVER_KEY_FILE).read_bytes())
    _, _, actions = ensure_certificates(mine, DNS, IPS, now=NOW)
    assert actions == ["issued a server certificate (the key on disk does not match the certificate)"]


def test_expiring_ca_is_replaced_with_a_warning(tmp_path):
    ca1, _, _ = ensure_certificates(tmp_path, DNS, IPS, now=NOW)
    ca2, _, actions = ensure_certificates(tmp_path, DNS, IPS, now=NOW + timedelta(days=CA_DAYS - 10))
    assert ca2 != ca1
    assert actions[0].startswith("replaced the certificate authority")
    assert "every device must trust the new one" in actions[0]
    assert actions[1] == "issued a server certificate (the certificate authority changed)"


def test_planned_names_cover_hostname_machine_and_loopback():
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, lan_hostname="football.localdomain")
    dns, ips = planned_names(settings)
    assert dns[0] == "football.localdomain"
    assert "localhost" in dns
    assert "127.0.0.1" in ips
    assert len(dns) == len(set(dns)) and len(ips) == len(set(ips))
    machine = machine_name().strip().lower().split(".", 1)[0]  # the first label only (a Mac reports Name.local)
    if machine and len(machine) <= 63 and valid_hostname(machine):
        assert machine in dns
        assert f"{machine}.localdomain" in dns


def test_planned_names_without_a_lan_hostname():
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY)
    dns, ips = planned_names(settings)
    assert "localhost" in dns
    assert all("." not in name or name == "localhost" for name in dns)


def test_a_long_or_dotted_machine_name_still_makes_a_certificate(tmp_path, monkeypatch):
    """macOS reports "Name.local", and CI machines have names past the 64-character limit of a certificate's
    common name (public release Phase 9: the macOS CI run)."""
    long_name = "Mac-" + "1" * 59 + ".local"  # 69 characters, a 63-character first label
    monkeypatch.setattr("app.tls.machine_name", lambda: long_name)
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path))
    dns, _ = planned_names(settings)
    assert ("mac-" + "1" * 59) in dns and long_name.lower() not in dns
    state = TlsState.prepare(settings, now=NOW)
    assert state.ca_cert_path.exists()
    monkeypatch.setattr("app.tls.machine_name", lambda: "m" * 70)  # a single label past 63: left out
    assert "m" * 70 not in planned_names(settings)[0]


def test_tls_state_prepare_and_refresh(tmp_path):
    settings = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path), lan_hostname="football.localdomain")
    state = TlsState.prepare(settings, now=NOW)
    assert state.cert_dir == tmp_path / "certs"
    assert state.context.minimum_version == ssl.TLSVersion.TLSv1_2
    assert state.ca_cert_path.exists()
    assert state.refresh(settings, now=NOW) is False

    renamed = load_settings(env_file=None, cfbd_api_key=TEST_KEY, data_dir=str(tmp_path), lan_hostname="gameday.localdomain")
    assert state.refresh(renamed, now=NOW) is True
    assert "gameday.localdomain" in state.server.dns_names

    summary = state.summary()
    assert summary["enabled"] is True
    assert summary["ca"]["name"] == CA_COMMON_NAME
    assert "PRIVATE" not in str(summary)
    assert summary["server"]["days_left"] > RENEW_BEFORE_DAYS


def test_describe_certificates(tmp_path):
    assert "will be created" in describe_certificates(tmp_path / "certs")
    ensure_certificates(tmp_path / "certs", DNS, IPS)
    line = describe_certificates(tmp_path / "certs")
    assert "valid until" in line
    assert "football.localdomain" in line
