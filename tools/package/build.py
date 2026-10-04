"""Build the packaged program (public release Phase 10): one folder that runs with nothing installed.

    python tools/package/build.py              build, smoke-test and archive into dist/
    python tools/package/build.py --no-smoke   skip the smoke test
    python tools/package/build.py --dist DIR   build and archive into DIR instead of dist/

Needs the build group: `uv sync --group build` (or pip install -r requirements-build.txt). The steps:

1. Staging files in tools/package/out/: the demo league's source hash (app/demo/upstream.py reads it when the
   generator sources are not on disk, as in a frozen build), the program's icon made from static/icons/, and the
   Windows version resource from app.__version__.
2. PyInstaller with tools/package/kickoff.spec: <dist>/KickoffCompanion/, the program beside its _internal folder.
3. The smoke test, with a `portable` marker beside the program so nothing lands in this computer's app-data folder:
   `--check` exits 0, and the demo answers /api/health, /, /api/season/overview and a script on a free port.
4. The archive, KickoffCompanion-<version>-<os>-<arch>.zip on Windows and .tar.gz elsewhere, with its SHA-256 in a
   file beside it.

Exit code 0 when every step passed, 1 when one failed. .github/workflows/release.yml runs this on each system and
attaches the archives to the GitHub release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from app import APP_NAME, PUBLISHER, __version__  # noqa: E402
from app.demo.upstream import SOURCE_HASH_FILE, source_hash  # noqa: E402
from app.paths import PORTABLE_MARKER  # noqa: E402

NAME = "KickoffCompanion"
SPEC = HERE / "kickoff.spec"
OUT = HERE / "out"
ICON_CANDIDATES = ("icon-256.png", "icon-192.png", "icon-180.png", "icon-512.png")  # the first that exists becomes the icon
SMOKE_SECONDS = 150  # the demo's first start builds the league (about ten seconds) before it listens; CI machines are slower
SMOKE_PATHS = ("/", "/api/season/overview", "/api/live/status", "/static/js/app.js")


def os_tag(system: str = sys.platform) -> str:
    if system.startswith("win"):
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"


def arch_tag(machine: str = platform.machine()) -> str:
    low = machine.lower()
    if low in ("amd64", "x86_64", "x64"):
        return "x64"
    if low in ("arm64", "aarch64"):
        return "arm64"
    return low or "unknown"


def archive_name(version: str = __version__, system: str = sys.platform, machine: str = platform.machine()) -> str:
    return f"{NAME}-{version}-{os_tag(system)}-{arch_tag(machine)}"


def version_tuple(version: str = __version__) -> tuple[int, int, int, int]:
    parts = [int(p) for p in version.split(".")[:4] if p.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    return parts[0], parts[1], parts[2], parts[3]


def version_info_text(version: str = __version__) -> str:
    """PyInstaller's version resource for the Windows program (Properties, Details)."""
    numbers = ", ".join(str(n) for n in version_tuple(version))
    strings = [
        ("CompanyName", PUBLISHER),
        ("FileDescription", APP_NAME),
        ("FileVersion", version),
        ("InternalName", NAME),
        ("LegalCopyright", f"MIT License, {PUBLISHER}"),
        ("OriginalFilename", f"{NAME}.exe"),
        ("ProductName", APP_NAME),
        ("ProductVersion", version),
    ]
    table = ", ".join(f"StringStruct({key!r}, {value!r})" for key, value in strings)
    return (
        "VSVersionInfo(\n"
        f"  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        f"  kids=[StringFileInfo([StringTable('040904B0', [{table}])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],\n"
        ")\n"
    )


def png_size(png: bytes) -> int:
    """The width of a PNG from its header (its height is the same for an icon)."""
    if len(png) < 24 or png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    width, height = struct.unpack(">II", png[16:24])
    if width != height:
        raise ValueError(f"an icon must be square, this PNG is {width} by {height}")
    return int(width)


def ico_bytes(png: bytes) -> bytes:
    """An .ico holding one PNG image (Windows reads PNG entries since Vista), so no imaging package is needed."""
    size = png_size(png)
    dimension = 0 if size >= 256 else size  # 0 stands for 256 in the directory entry
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


def write_staging(out: Path = OUT, static: Path = ROOT / "static") -> dict[str, Path]:
    """The files the spec bundles or uses; returns them by role (hash, version, icon)."""
    out.mkdir(parents=True, exist_ok=True)
    files = {"hash": out / SOURCE_HASH_FILE, "version": out / "version_info.txt"}
    files["hash"].write_text(source_hash() + "\n", encoding="utf-8")
    files["version"].write_text(version_info_text(), encoding="utf-8")
    for name in ICON_CANDIDATES:
        png = static / "icons" / name
        if png.is_file():
            files["icon"] = out / "kickoff.ico"
            files["icon"].write_bytes(ico_bytes(png.read_bytes()))
            break
    return files


def run_pyinstaller(dist: Path, work: Path) -> int:
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(dist), "--workpath", str(work), str(SPEC)]
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def program_path(dist: Path, system: str = sys.platform) -> Path:
    return dist / NAME / (f"{NAME}.exe" if system.startswith("win") else NAME)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fetch(url: str, timeout: float = 5.0) -> tuple[int, bytes]:
    """(status, body) for a GET of our own local server; (0, b"") when it does not answer."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - our own local server
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, OSError, TimeoutError):
        return 0, b""


def smoke_test(program: Path) -> list[str]:
    """Run the built program: what failed, as messages; empty when it passed. A `portable` marker beside the program
    keeps its files there for the test (removed afterwards), so this computer's app-data folder is never touched."""
    problems: list[str] = []
    marker = program.parent / PORTABLE_MARKER
    marker.write_text("", encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory(prefix="kickoff-smoke-") as temp:
            env = {**os.environ, "DATA_DIR": str(Path(temp) / "data"), "LOG_DIR": str(Path(temp) / "logs")}
            check = subprocess.run([str(program), "--check"], capture_output=True, text=True, timeout=180, env=env, cwd=program.parent, check=False)
            if check.returncode != 0 or "settings check" not in check.stdout:
                problems.append(f"--check exited {check.returncode}: {(check.stderr or check.stdout)[-800:]}")
            port = free_port()
            demo = subprocess.Popen(
                [str(program), "--demo", "--no-browser", "--port", str(port), "--clean"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=program.parent,
            )
            try:
                deadline = time.monotonic() + SMOKE_SECONDS
                status = 0
                while time.monotonic() < deadline and demo.poll() is None:
                    status, _ = fetch(f"http://127.0.0.1:{port}/api/health", timeout=2)
                    if status == 200:
                        break
                    time.sleep(1)
                if status != 200:
                    problems.append(f"the demo did not answer /api/health within {SMOKE_SECONDS} s (exit code {demo.poll()})")
                else:
                    for path in SMOKE_PATHS:
                        code, body = fetch(f"http://127.0.0.1:{port}{path}", timeout=60)
                        if code != 200:
                            problems.append(f"GET {path} answered {code}")
                        elif path.startswith("/api/"):
                            errors = json.loads(body).get("errors") or []
                            if errors:
                                problems.append(f"GET {path} carried errors: {errors[:3]}")
            finally:
                demo.terminate()
                try:
                    output, _ = demo.communicate(timeout=30)
                except subprocess.TimeoutExpired:
                    demo.kill()
                    output, _ = demo.communicate()
                if problems:
                    problems.append("demo output: " + (output or "")[-1500:])
    finally:
        marker.unlink(missing_ok=True)
        for leftover in ("data", "logs"):
            shutil.rmtree(program.parent / leftover, ignore_errors=True)
    return problems


def archive(dist: Path, name: str, system: str = sys.platform) -> Path:
    fmt = "zip" if system.startswith("win") else "gztar"
    path = Path(shutil.make_archive(str(dist / name), fmt, root_dir=dist, base_dir=NAME))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (dist / f"{path.name}.sha256").write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dist", type=Path, default=ROOT / "dist", help="where the build and the archive go (default: dist/)")
    parser.add_argument("--no-smoke", action="store_true", help="skip the smoke test")
    parser.add_argument("--no-archive", action="store_true", help="leave the folder as it is, no archive")
    args = parser.parse_args(argv)
    dist = args.dist.resolve()
    shutil.rmtree(dist / NAME, ignore_errors=True)
    staged = write_staging()
    print(f"Staged {', '.join(sorted(p.name for p in staged.values()))} in {OUT}")
    if run_pyinstaller(dist, OUT / "build") != 0:
        print("PyInstaller failed.")
        return 1
    program = program_path(dist)
    if not program.is_file():
        print(f"PyInstaller finished but {program} is missing.")
        return 1
    if not args.no_smoke:
        problems = smoke_test(program)
        if problems:
            print("Smoke test failed:")
            for problem in problems:
                print("  " + problem)
            return 1
        print("Smoke test passed: --check, the demo and its pages.")
    if not args.no_archive:
        path = archive(dist, archive_name())
        print(f"Archive: {path} ({path.stat().st_size / 1e6:.1f} MB), SHA-256 beside it.")
    print(f"Program: {program}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
