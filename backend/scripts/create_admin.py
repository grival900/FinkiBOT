"""CLI entrypoint to grant admin access: `python -m backend.scripts.create_admin <email>`

Promotes an *already-registered* user (register normally first, via `/auth/register`
or the `/register` page) — deliberately does not create a user with a script-supplied
password, since that risks a weak/known password ending up in shell history or a
Dockerfile layer. Registration always creates a non-admin account.

(`backend.scripts.seed` separately creates a fixed `admin@email.com`/`admin` account
for local dev bootstrap — see its docstring. Use this script instead to promote a
real account for anything shared/deployed.)
"""

import sys

from backend.db import SessionLocal
from backend.models import User

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m backend.scripts.create_admin <email>", file=sys.stderr)
        sys.exit(1)

    email = sys.argv[1].lower()
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email).one_or_none()
        if user is None:
            print(f"No account found for {email!r} — register it first (via /auth/register or /register).", file=sys.stderr)
            sys.exit(1)
        user.is_admin = True
        db.commit()
    print(f"{email} is now an admin.")
