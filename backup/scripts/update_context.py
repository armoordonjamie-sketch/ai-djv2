import argparse
import asyncio
import logging
import os
import sys

# Add project root to path ensuring backend_v2 imports work
sys.path.append(os.getcwd())

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from backend_v2.models.user import User
from backend_v2.models.context import UserContext
from backend_v2.config import DATABASE_URL

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("update_context")

async def update_context(text: str, email: str = "test@example.com"):
    logger.info(f"Connecting to {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        # Find user
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {email} not found. Ensure the user is registered.")
            return

        # Find or create context
        stmt = select(UserContext).where(
            (UserContext.user_id == user.id) & 
            (UserContext.name == "default")
        )
        result = await session.execute(stmt)
        context = result.scalar_one_or_none()
        
        if context:
            context.raw_text = text
            logger.info(f"Updated existing context for {user.email} (ID: {user.id})")
        else:
            context = UserContext(
                user_id=user.id,
                name="default",
                raw_text=text
            )
            session.add(context)
            logger.info(f"Created new context for {user.email} (ID: {user.id})")
        
        await session.commit()
        logger.info("✅ Context successfully saved to database.")
        logger.info(f"New Context Preview: {text[:100]}...")

    await engine.dispose()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update user context from text or file")
    parser.add_argument("--text", help="Context text string")
    parser.add_argument("--file", help="Path to text file containing context")
    parser.add_argument("--email", default="test@example.com", help="User email (default: test@example.com)")
    
    args = parser.parse_args()
    
    context_text = ""
    if args.file:
        if os.path.exists(args.file):
            with open(args.file, "r", encoding="utf-8") as f:
                context_text = f.read()
        else:
            logger.error(f"File not found: {args.file}")
            exit(1)
    elif args.text:
        context_text = args.text
    else:
        logger.error("Must provide --text or --file")
        print("\nUsage:")
        print('  python -m backend_v2.scripts.update_context --text "I like 80s pop"')
        print('  python -m backend_v2.scripts.update_context --file user_context.txt')
        exit(1)
        
    asyncio.run(update_context(context_text, args.email))
