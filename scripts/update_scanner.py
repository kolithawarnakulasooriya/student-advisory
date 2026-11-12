"""Update local scanner signatures separately from network-isolated document jobs."""

import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
folder = root / "local-data/clamav"
folder.mkdir(parents=True, mode=0o700, exist_ok=True)
(folder / "freshclam.conf").write_text(
    "DatabaseDirectory /signatures\nDatabaseMirror database.clamav.net\n"
)
result = subprocess.run(
    [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--mount",
        f"type=bind,src={folder},dst=/signatures",
        "--entrypoint",
        "freshclam",
        "advisory-parser:0.3",
        "--config-file=/signatures/freshclam.conf",
        "--stdout",
    ],
    check=True,
    capture_output=True,
    text=True,
)
print(result.stdout, end="")
print(result.stderr, end="")
# FreshClam can exit zero during CDN cooldown without checking updates.
for database in ("daily", "main", "bytecode"):
    if not any(
        message in result.stdout
        for message in (
            f"{database}.cvd database is up-to-date",
            f"{database}.cld database is up-to-date",
            f"{database}.cvd updated",
            f"{database}.cld updated",
        )
    ):
        raise SystemExit(
            "Signatures were not fully verified; freshness marker retained."
        )

(folder / "last-successful-update").touch()
