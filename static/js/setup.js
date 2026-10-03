// Kickoff Companion, the "Connect a device" page (/setup; public release Phase 4b).
// Fills in the app's address and its QR code from /api/setup. With HTTPS on (HTTPS=on in .env) it
// also shows the certificate download and the trust steps. The QR code and the download link work
// even if the details fail to load.

const DASH = "–";

const els = {
  appLink: document.getElementById("app-link"),
  appUrl: document.getElementById("app-url"),
  otherUrls: document.getElementById("other-urls"),
  qr: document.getElementById("qr"),
  name: document.getElementById("ca-name"),
  fingerprint: document.getElementById("ca-fingerprint"),
  until: document.getElementById("ca-until"),
  status: document.getElementById("setup-status"),
  alreadySecure: document.getElementById("already-secure"),
  trust: ["trust-intro", "trust-download", "trust-steps"].map((id) => document.getElementById(id)).filter(Boolean),
};

function text(value) {
  if (value === null || value === undefined) return DASH;
  const s = String(value).trim();
  return s === "" ? DASH : s;
}

function localDate(iso) {
  if (typeof iso !== "string" || !iso) return DASH;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? DASH : d.toLocaleDateString([], { dateStyle: "long" });
}

const isAddress = (url) => typeof url === "string" && /^https?:\/\/[^\s"<>]+$/.test(url);

function showAddress(data) {
  const url = isAddress(data.app_url) ? data.app_url : isAddress(data.https_url) ? data.https_url : null;
  if (url) {
    els.appLink.href = `${url}/`;
    els.appUrl.textContent = url;
  } else {
    els.appUrl.textContent = window.location.origin;
  }
  // Other addresses that reach the same server: the name it announces (kickoff.local) and the
  // number address, for a device that cannot use the first one.
  const others = Array.isArray(data.other_urls) ? data.other_urls.filter(isAddress) : [];
  if (others.length && els.otherUrls) {
    els.otherUrls.textContent = `If that address does not open, the same app is also at ${others.join(" and ")}.`;
    els.otherUrls.hidden = false;
  }
  if (els.qr && typeof data.qr_path === "string" && data.qr_path.startsWith("/setup/")) els.qr.src = data.qr_path;
}

function showTrust(data) {
  for (const section of els.trust) section.hidden = false;
  const ca = data.ca && typeof data.ca === "object" ? data.ca : {};
  els.name.textContent = text(ca.name);
  // The steps name the certificate as this server's actually is (an install from before the
  // public release keeps its original name), and the download link follows the server's path.
  if (typeof ca.name === "string" && ca.name.trim()) for (const node of document.querySelectorAll(".ca-name")) node.textContent = ca.name.trim();
  if (typeof data.download_name === "string" && data.download_name) for (const node of document.querySelectorAll(".ca-file")) node.textContent = data.download_name;
  const link = document.getElementById("download");
  if (link && typeof data.download_path === "string" && data.download_path.startsWith("/setup/")) link.href = data.download_path;
  els.fingerprint.textContent = text(ca.fingerprint_sha256);
  els.until.textContent = localDate(ca.not_after);
  if (window.location.protocol === "https:") els.alreadySecure.hidden = false;
}

async function load() {
  try {
    const response = await fetch("/api/setup", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const body = await response.json();
    const data = body && body.data && typeof body.data === "object" ? body.data : null;
    if (!data) throw new Error("Malformed response");
    showAddress(data);
    if (data.https === true) showTrust(data);
    els.status.textContent = data.https === true ? "HTTPS is on: trust the certificate on each new device first." : "Ready. Nothing to install on a device.";
  } catch (err) {
    els.appUrl.textContent = window.location.origin;
    els.status.textContent = "Could not load the server's details. The QR code and this address still work.";
    console.warn("Setup details failed:", err && err.message ? err.message : err);
  }
}

if (els.qr) els.qr.addEventListener("error", () => { els.qr.hidden = true; });
void load();
