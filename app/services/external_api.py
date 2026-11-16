from typing import Any

import httpx

from app.config import settings
from app.schemas import KanjiData, VocabularyData


async def fetch_kanji_list(level: str) -> list[str]:
    if level not in {"N5", "N4", "N3"}:
        raise ValueError(f"Unsupported JLPT level: {level}")
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        response = await client.get(f"{settings.kanji_api_base_url}/kanji/jlpt-{level[1:]}")
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("Kanji API returned an unexpected kanji list")
    return data


async def fetch_kanji_detail(character: str, level: str) -> KanjiData:
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        response = await client.get(f"{settings.kanji_api_base_url}/kanji/{character}")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
    return KanjiData(
        character=character,
        level=level,
        meanings=data.get("meanings", []),
        onyomi=data.get("on_readings", []),
        kunyomi=data.get("kun_readings", []),
        stroke_count=data.get("stroke_count"),
        grade=data.get("grade"),
    )


async def search_jisho(query: str, page: int = 1) -> list[VocabularyData]:
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        response = await client.get(
            settings.jisho_api_url,
            params={"keyword": query, "page": page},
        )
        response.raise_for_status()
        payload = response.json()

    result: list[VocabularyData] = []
    for entry in payload.get("data", []):
        japanese = entry.get("japanese", [])
        senses = entry.get("senses", [])
        if not japanese:
            continue
        words = [item.get("word") for item in japanese if item.get("word")]
        readings = [item.get("reading") for item in japanese if item.get("reading")]
        meanings = [
            meaning
            for sense in senses
            for meaning in sense.get("english_definitions", [])
        ]
        word = words[0] if words else readings[0] if readings else ""
        if word:
            result.append(
                VocabularyData(
                    word=word,
                    reading=readings[0] if readings else None,
                    meanings=meanings,
                )
            )
    return result
