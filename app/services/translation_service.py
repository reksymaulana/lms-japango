import asyncio
import logging
from collections.abc import Mapping, Sequence
from html import unescape
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import TranslationCache

logger = logging.getLogger(__name__)
MAX_TRANSLATION_BYTES = 500
TRANSLATION_CONCURRENCY = 4


async def _fetch_translation(client: httpx.AsyncClient, text: str) -> str | None:
    try:
        response = await client.get(
            settings.translation_api_url,
            params={"q": text, "langpair": "en|id"},
        )
        response.raise_for_status()
        payload: Any = response.json()
    except httpx.HTTPError as error:
        logger.warning(
            "MyMemory translation request failed (%s)",
            type(error).__name__,
        )
        return None
    except ValueError:
        logger.warning("MyMemory returned invalid JSON")
        return None

    if not isinstance(payload, dict) or str(payload.get("responseStatus")) != "200":
        logger.warning("MyMemory returned an unsuccessful translation response")
        return None

    response_data = payload.get("responseData")
    translated_text = (
        response_data.get("translatedText")
        if isinstance(response_data, dict)
        else None
    )
    if not isinstance(translated_text, str) or not translated_text.strip():
        logger.warning("MyMemory response did not contain translated text")
        return None
    return unescape(translated_text).strip()


async def translate_meaning_groups(
    session: AsyncSession,
    meaning_groups: Mapping[str, Sequence[str]],
    target_language: str,
) -> tuple[dict[str, str], bool]:
    if target_language != "id":
        return {}, False

    source_by_key = {
        key: "; ".join(meaning.strip() for meaning in meanings if meaning.strip())
        for key, meanings in meaning_groups.items()
    }
    source_texts = {text for text in source_by_key.values() if text}
    if not source_texts:
        return {}, False

    cached_rows = await session.scalars(
        select(TranslationCache).where(
            TranslationCache.source_text.in_(source_texts),
            TranslationCache.source_language == "en",
            TranslationCache.target_language == target_language,
        )
    )
    translated_by_source = {
        item.source_text: item.translated_text for item in cached_rows
    }
    missing = source_texts - translated_by_source.keys()
    failed = False

    if missing:
        valid_texts = []
        for text in missing:
            if len(text.encode("utf-8")) > MAX_TRANSLATION_BYTES:
                logger.warning(
                    "Skipping MyMemory translation because a gloss exceeds 500 bytes"
                )
                failed = True
            else:
                valid_texts.append(text)

        if valid_texts:
            semaphore = asyncio.Semaphore(TRANSLATION_CONCURRENCY)

            async def fetch_limited(
                client: httpx.AsyncClient,
                text: str,
            ) -> tuple[str, str | None]:
                async with semaphore:
                    return text, await _fetch_translation(client, text)

            async with httpx.AsyncClient(timeout=settings.translation_timeout_seconds) as client:
                results = await asyncio.gather(
                    *(fetch_limited(client, text) for text in valid_texts)
                )

            new_cache_entries = []
            for source_text, translated_text in results:
                if translated_text is None:
                    failed = True
                    continue
                translated_by_source[source_text] = translated_text
                new_cache_entries.append(
                    {
                        "source_text": source_text,
                        "source_language": "en",
                        "target_language": target_language,
                        "translated_text": translated_text,
                    }
                )

            if new_cache_entries:
                statement = insert(TranslationCache).values(new_cache_entries)
                await session.execute(
                    statement.on_conflict_do_nothing(
                        constraint="uq_translation_cache_language_pair"
                    )
                )

    localized_by_key = {
        key: translated_by_source[source_text]
        for key, source_text in source_by_key.items()
        if source_text in translated_by_source
    }
    return localized_by_key, failed
