"""Create (or verify) a platform user from the command line.

Usage:
    python create_user.py --email admin@example.com --password 'S3cret!' \
        --name "Admin" --role admin

Credentials are taken from CLI args or the environment
(PM_BOOTSTRAP_EMAIL / PM_BOOTSTRAP_PASSWORD / PM_BOOTSTRAP_NAME / PM_BOOTSTRAP_ROLE).
No credentials are hardcoded.
"""
import argparse
import asyncio
import os
import sys

# Ensure backend directory is in python path
sys.path.append(os.getcwd())

from app.db.session import AsyncSessionLocal
from app.services import user_service
from app.schemas.user import UserCreate


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or verify a platform user")
    parser.add_argument("--email", default=os.getenv("PM_BOOTSTRAP_EMAIL"))
    parser.add_argument("--password", default=os.getenv("PM_BOOTSTRAP_PASSWORD"))
    parser.add_argument("--name", default=os.getenv("PM_BOOTSTRAP_NAME", "Administrator"))
    parser.add_argument("--role", default=os.getenv("PM_BOOTSTRAP_ROLE", "admin"))
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    if not args.email or not args.password:
        print("ERROR: email and password are required (via --email/--password "
              "or PM_BOOTSTRAP_EMAIL/PM_BOOTSTRAP_PASSWORD env vars).")
        return 2

    print(f"Checking for user: {args.email}")
    async with AsyncSessionLocal() as session:
        user = await user_service.get_user_by_email(session, args.email)
        if user:
            print(f"User {args.email} already exists.")
            return 0
        print(f"Creating user {args.email}...")
        try:
            await user_service.create_user(
                session,
                UserCreate(email=args.email, password=args.password,
                           full_name=args.name, role=args.role),
            )
            print("User created successfully.")
            return 0
        except Exception as e:
            print(f"Error creating user: {e}")
            return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
