import argparse
import asyncio

from app.database import SessionLocal
from app.models import AppUser


async def promote(auth_user_id: str) -> None:
    async with SessionLocal() as session:
        account = await session.get(AppUser, auth_user_id)
        if account is None:
            raise SystemExit(
                "Account not found. The user must sign in to Japango first."
            )
        account.role = "sensei"
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote an existing Japango account to Sensei."
    )
    parser.add_argument("auth_user_id", help="Neon Auth user ID")
    args = parser.parse_args()
    asyncio.run(promote(args.auth_user_id))
    print(f"Promoted {args.auth_user_id} to Sensei.")


if __name__ == "__main__":
    main()
