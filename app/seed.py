import asyncio
import sys
from pathlib import Path

from app.bot import create_pool
from app.repository import apply_schema, seed_questions


async def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("app/data/questions.example.json")
    pool = await create_pool()
    try:
        await apply_schema(pool)
        await seed_questions(pool, path)
    finally:
        await pool.close()
    print(f"Вопросы загружены из {path}")


if __name__ == "__main__":
    asyncio.run(main())
