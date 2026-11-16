from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx

from app.models import TranslationCache
from app.services import translation_service


class FakeSession:
    def __init__(self, cached_rows: list[TranslationCache] | None = None) -> None:
        self.cached_rows = cached_rows or []
        self.executed_statements = []

    async def scalars(self, statement):
        self.assert_statement(statement)
        return self.cached_rows

    @staticmethod
    def assert_statement(statement) -> None:
        if statement is None:
            raise AssertionError("Expected a translation cache query")

    async def execute(self, statement) -> None:
        self.executed_statements.append(statement)


class TranslationServiceTests(IsolatedAsyncioTestCase):
    async def test_translates_unique_glosses_and_stores_cache_rows(self) -> None:
        client_type = httpx.AsyncClient
        requested_texts: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            text = request.url.params["q"]
            requested_texts.append(text)
            translations = {"sun": "matahari", "sun; light": "matahari; cahaya"}
            return httpx.Response(
                200,
                json={
                    "responseStatus": 200,
                    "responseData": {"translatedText": translations[text]},
                },
            )

        def make_client(**kwargs):
            return client_type(transport=httpx.MockTransport(handler), **kwargs)

        session = FakeSession()
        with patch.object(translation_service.httpx, "AsyncClient", side_effect=make_client):
            localized, unavailable = await translation_service.translate_meaning_groups(
                session,
                {"日": ["sun"], "明": ["sun", "light"]},
                "id",
            )

        self.assertEqual(localized, {"日": "matahari", "明": "matahari; cahaya"})
        self.assertFalse(unavailable)
        self.assertCountEqual(requested_texts, ["sun", "sun; light"])
        self.assertEqual(len(session.executed_statements), 1)

    async def test_uses_cached_translation_without_calling_provider(self) -> None:
        session = FakeSession(
            [TranslationCache(source_text="sun", translated_text="matahari")]
        )

        with patch.object(translation_service.httpx, "AsyncClient") as client:
            localized, unavailable = await translation_service.translate_meaning_groups(
                session,
                {"日": ["sun"]},
                "id",
            )

        self.assertEqual(localized, {"日": "matahari"})
        self.assertFalse(unavailable)
        client.assert_not_called()
        self.assertEqual(session.executed_statements, [])

    async def test_reports_provider_failure_for_english_fallback(self) -> None:
        client_type = httpx.AsyncClient

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.method, "GET")
            return httpx.Response(429, json={"error": "quota exceeded"})

        def make_client(**kwargs):
            return client_type(transport=httpx.MockTransport(handler), **kwargs)

        with patch.object(translation_service.httpx, "AsyncClient", side_effect=make_client):
            localized, unavailable = await translation_service.translate_meaning_groups(
                FakeSession(),
                {"日": ["sun"]},
                "id",
            )

        self.assertEqual(localized, {})
        self.assertTrue(unavailable)

    async def test_does_not_translate_when_ui_language_is_english(self) -> None:
        with patch.object(translation_service.httpx, "AsyncClient") as client:
            localized, unavailable = await translation_service.translate_meaning_groups(
                FakeSession(),
                {"日": ["sun"]},
                "en",
            )

        self.assertEqual(localized, {})
        self.assertFalse(unavailable)
        client.assert_not_called()
