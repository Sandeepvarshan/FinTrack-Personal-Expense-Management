"""Create/refresh backend/*/.env files with ONE shared, strong JWT secret.

Why one shared secret?
    The User Service signs login tokens (JWTs). Every other service verifies
    them. Verification only works if all services hold the same secret.

Usage (from the repository root):
    python scripts/setup_env.py           # keep an existing valid secret, else make one
    python scripts/setup_env.py --rotate  # force a brand-new secret (logs everyone out)

The secret itself is never printed. Other lines (DB password, ports...) are left alone.
"""
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = {"", "change-this-secret", "replace_with_a_long_random_secret"}
SECRET_LINE = re.compile(r"^JWT_SECRET=(.*?)(\r?)$", re.MULTILINE)


def is_strong(value: str) -> bool:
    return value not in PLACEHOLDERS and len(value) >= 32


def read_raw(path: Path) -> str:
    """Read a file WITHOUT newline translation so CRLF/LF endings are preserved."""
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def existing_strong_secret(env_files: list[Path]) -> str | None:
    for env_file in env_files:
        if env_file.exists():
            match = SECRET_LINE.search(read_raw(env_file))
            if match and is_strong(match.group(1).strip()):
                return match.group(1).strip()
    return None


def main() -> int:
    service_dirs = sorted(
        d for d in (ROOT / "backend").iterdir()
        if d.is_dir() and (d / ".env.example").exists() and "JWT_SECRET" in (d / ".env.example").read_text(encoding="utf-8")
    )
    env_files = [d / ".env" for d in service_dirs]
    rotate = "--rotate" in sys.argv
    secret = None if rotate else existing_strong_secret(env_files)
    action = "reused existing strong secret"
    if secret is None:
        secret = secrets.token_urlsafe(48)
        action = "generated a new secret"

    for service_dir in service_dirs:
        env_file = service_dir / ".env"
        if not env_file.exists():
            env_file.write_bytes((service_dir / ".env.example").read_bytes())
            print(f"created  {env_file.relative_to(ROOT)} from .env.example (set DB_PASSWORD yourself!)")
        text = read_raw(env_file)
        if SECRET_LINE.search(text):
            text = SECRET_LINE.sub(lambda m: f"JWT_SECRET={secret}{m.group(2)}", text)
        else:
            eol = "\r\n" if "\r\n" in text else "\n"
            text = text.rstrip("\r\n") + f"{eol}JWT_SECRET={secret}{eol}"
        with open(env_file, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        print(f"updated  {env_file.relative_to(ROOT)}")

    print(f"\nDone: {action}, written to {len(service_dirs)} services (secret not displayed).")
    print("Restart all services so they pick up the new secret.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
