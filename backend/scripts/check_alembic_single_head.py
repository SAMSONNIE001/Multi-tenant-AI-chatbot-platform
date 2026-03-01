import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    heads = list(script.get_heads())

    if len(heads) != 1:
        print(f"[FAIL] Alembic heads={len(heads)} -> {heads}")
        return 1

    print(f"[OK] Alembic single head: {heads[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
