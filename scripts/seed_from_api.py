import argparse
import asyncio

from sqlalchemy.dialects.postgresql import insert

from app.database import SessionLocal, engine
from app.models import Base, Kanji
from app.services.external_api import fetch_kanji_detail, fetch_kanji_list


async def seed_level(level: str, concurrency: int) -> int:
    characters = await fetch_kanji_list(level)
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_one(character: str):
        async with semaphore:
            return await fetch_kanji_detail(character, level)

    kanji_data = await asyncio.gather(*(fetch_one(character) for character in characters))
    async with SessionLocal() as session:
        for item in kanji_data:
            statement = insert(Kanji).values(
                character=item.character,
                level=item.level,
                meanings=item.meanings,
                onyomi=item.onyomi,
                kunyomi=item.kunyomi,
                stroke_count=item.stroke_count,
                grade=item.grade,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[Kanji.character],
                set_={
                    "level": statement.excluded.level,
                    "meanings": statement.excluded.meanings,
                    "onyomi": statement.excluded.onyomi,
                    "kunyomi": statement.excluded.kunyomi,
                    "stroke_count": statement.excluded.stroke_count,
                    "grade": statement.excluded.grade,
                },
            )
            await session.execute(statement)
        await session.commit()
    return len(kanji_data)


async def main(levels: list[str], concurrency: int) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    for level in levels:
        imported = await seed_level(level, concurrency)
        print(f"{level}: {imported} Kanji tersimpan")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Impor data Kanji JLPT dari kanjiapi.dev")
    parser.add_argument("--levels", nargs="+", choices=["N5", "N4", "N3"], default=["N5", "N4", "N3"])
    parser.add_argument("--concurrency", type=int, default=8)
    arguments = parser.parse_args()
    if arguments.concurrency < 1:
        parser.error("--concurrency harus minimal 1")
    asyncio.run(main(arguments.levels, arguments.concurrency))
