"""
Updater smoke test.

Covers the parts of ``src/updater.py`` that need no GUI and no network:
version parsing/comparison, release-asset selection per OS and the streaming
download. Pass ``--online`` to additionally hit the real GitHub API.

Run:  python tools/updater_smoke.py [--online]
"""

import sys
import tempfile
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

import updater  # noqa: E402

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    if actual == expected:
        print(f"  ok   {label}")
    else:
        failures.append(label)
        print(f"  FAIL {label}: got {actual!r}, expected {expected!r}")


# -- version parsing / comparison -------------------------------------------

print("version parsing:")
check("plain", updater.parse_version("2.4.0"), (2, 4, 0, 1))
check("v prefix", updater.parse_version("v2.4.0"), (2, 4, 0, 1))
check("short", updater.parse_version("2.4"), (2, 4, 0, 1))
check("prerelease", updater.parse_version("2.4.0-rc1"), (2, 4, 0, 0))

try:
    updater.parse_version("not-a-version")
    failures.append("garbage version rejected")
    print("  FAIL garbage version should raise UpdateError")
except updater.UpdateError:
    print("  ok   garbage version raises UpdateError")

print("version comparison:")
check("patch bump", updater.is_newer("2.3.1", "2.3.0"), True)
check("minor bump", updater.is_newer("2.4.0", "2.3.9"), True)
check("same", updater.is_newer("2.3.0", "2.3.0"), False)
check("older", updater.is_newer("2.2.0", "2.3.0"), False)
check("rc below final", updater.is_newer("2.4.0-rc1", "2.3.0"), True)
check("rc of current", updater.is_newer("2.3.0-rc1", "2.3.0"), False)

print("update kind (decides popup vs. silent install):")
check("patch", updater.update_kind("2.3.1", "2.3.0"), "patch")
check("patch from prerelease", updater.update_kind("2.3.1", "2.3.0-rc1"), "patch")
check("minor", updater.update_kind("2.4.0", "2.3.0"), "minor")
check("minor jumps patches", updater.update_kind("2.4.1", "2.3.0"), "minor")
check("major", updater.update_kind("3.0.0", "2.9.9"), "major")
check("nothing to do", updater.update_kind("2.3.0", "2.3.0"), None)
check("downgrade", updater.update_kind("2.2.0", "2.3.0"), None)

# -- asset selection ---------------------------------------------------------

release = updater.Release(
    version="2.4.0",
    tag="v2.4.0",
    notes="",
    page_url="https://example.invalid/v2.4.0",
    assets={
        "UniDocs-2.4.0-windows-x86_64-setup.exe": "https://example.invalid/win-setup",
        "UniDocs-windows-x86_64.zip": "https://example.invalid/win-zip",
        "UniDocs-linux-x86_64.zip": "https://example.invalid/linux-zip",
        "UniDocs-macos-universal.zip": "https://example.invalid/macos-zip",
    },
)

print("asset selection:")
check(
    "windows prefers the installer",
    updater.asset_for(release, "Windows")[0],
    "UniDocs-2.4.0-windows-x86_64-setup.exe",
)
check("linux", updater.asset_for(release, "Linux")[0], "UniDocs-linux-x86_64.zip")
check("macos", updater.asset_for(release, "Darwin")[0], "UniDocs-macos-universal.zip")
check("unknown os", updater.asset_for(release, "FreeBSD"), None)
check("no assets", updater.asset_for(updater.Release("1.0.0", "v1.0.0", "", "", {}), "Windows"), None)

print("self-update platform gate:")
check("windows", updater.can_self_update("Windows"), True)
check("linux", updater.can_self_update("Linux"), False)

print("can UniDocs install this asset itself:")
SETUP_EXE = ("UniDocs-2.4.0-windows-x86_64-setup.exe", "https://example.invalid/win-setup")
WINDOWS_ZIP = ("UniDocs-windows-x86_64.zip", "https://example.invalid/win-zip")
LINUX_ZIP = ("UniDocs-linux-x86_64.zip", "https://example.invalid/linux-zip")
check("windows setup", updater.can_install_asset(SETUP_EXE, "Windows"), True)
check("windows zip", updater.can_install_asset(WINDOWS_ZIP, "Windows"), False)
check("linux zip", updater.can_install_asset(LINUX_ZIP, "Linux"), False)
check("linux setup file", updater.can_install_asset(SETUP_EXE, "Linux"), False)
check("no asset", updater.can_install_asset(None, "Windows"), False)

# -- download ----------------------------------------------------------------

print("download:")
with tempfile.TemporaryDirectory() as tmp:
    payload = b"unidocs" * 5000
    source = Path(tmp) / "UniDocs-linux-x86_64.zip"
    source.write_bytes(payload)

    seen: list[tuple[int, int]] = []
    out = updater.download(source.as_uri(), Path(tmp) / "target", progress=lambda d, t: seen.append((d, t)))

    check("bytes written", out.read_bytes(), payload)
    check("progress reported", bool(seen), True)
    check("total seen", seen[-1][1], len(payload))
    check("last chunk complete", seen[-1][0], len(payload))

    # A missing URL must surface as UpdateError and leave no half-written file.
    empty = Path(tmp) / "empty"
    try:
        updater.download((Path(tmp) / "nope.zip").as_uri(), empty)
        failures.append("missing url rejected")
        print("  FAIL missing url should raise UpdateError")
    except updater.UpdateError:
        print("  ok   missing url raises UpdateError")
        check("no leftover file", list(empty.iterdir()), [])

# -- live check (opt-in) -----------------------------------------------------

if "--online" in sys.argv:
    print("live check against GitHub:")
    try:
        latest = updater.fetch_latest()
        print(f"  ok   latest release {latest.tag} with {len(latest.assets)} asset(s)")
        for name in latest.assets:
            print(f"         {name}")
    except updater.UpdateError as ex:
        print(f"  note offline / unavailable: {ex}")

print()
if failures:
    print(f"{len(failures)} FAILURE(S): {failures}")
    sys.exit(1)
print("UPDATER OK")
