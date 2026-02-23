import subprocess
import sys
from pathlib import Path


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, "-m", "alembic", "check"]
    proc = subprocess.run(
        cmd,
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
    )

    if proc.stdout:
        print(proc.stdout.strip())
    if proc.stderr:
        print(proc.stderr.strip(), file=sys.stderr)

    if proc.returncode != 0:
        print(
            "Migration drift detected or alembic check failed. "
            "Generate and commit a migration before merging.",
            file=sys.stderr,
        )
        return proc.returncode

    print("Alembic schema drift check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
