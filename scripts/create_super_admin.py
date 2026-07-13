"""Create the platform super admin — run once against your production database.

Usage (PowerShell, from the project root, venv active):
    $env:DATABASE_URL = "<your Neon connection string>"
    python scripts/create_super_admin.py
    Remove-Item Env:DATABASE_URL     # clean up afterwards

The script is safe to re-run: it refuses to create a duplicate.
"""
import asyncio
import getpass
import sys
from pathlib import Path

# Ensure the project root is importable even when run as
# `python scripts/create_super_admin.py` (Python roots imports at the
# script's folder, not the current directory).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import SessionLocal, engine
from app.core.config import settings
from app.core.security import hash_password
from app.models.school import User, Role


async def main() -> None:
    host = settings.DATABASE_URL.split("@")[-1].split("/")[0] if "@" in settings.DATABASE_URL else settings.DATABASE_URL
    print(f"Target database host: {host}")
    if settings.is_sqlite:
        print("WARNING: this is the local SQLite dev database, not Neon.")
    ok = input("Type 'yes' to continue: ").strip().lower()
    if ok != "yes":
        print("Aborted.")
        return

    email = input("Super admin email: ").strip().lower()
    if "@" not in email:
        print("That does not look like an email. Aborted.")
        return
    password = getpass.getpass("Password (min 8 chars, typing is hidden): ")
    if len(password) < 8:
        print("Password too short. Aborted.")
        return
    first = input("First name: ").strip() or "Platform"
    last = input("Last name: ").strip() or "Owner"

    async with SessionLocal() as db:
        existing = (await db.execute(select(User).where(
            User.email == email))).scalars().first()
        if existing:
            print(f"A user with {email} already exists — nothing created.")
            return
        db.add(User(school_id=None, email=email,
                    hashed_password=hash_password(password),
                    role=Role.SUPER_ADMIN, first_name=first, last_name=last))
        await db.commit()
    print(f"Super admin {email} created. You can now sign in and onboard schools.")
    await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
