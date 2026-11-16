from unittest import IsolatedAsyncioTestCase

from app.models import AppState, Bunpou
from app.services.grammar_seed import STARTER_GRAMMAR, seed_grammar


class SeedSession:
    def __init__(self, state: AppState | None, existing_count: int = 0) -> None:
        self.state = state
        self.existing_count = existing_count
        self.added = []
        self.committed = False

    async def get(self, model, key):
        return self.state

    async def scalar(self, statement):
        return self.existing_count

    def add_all(self, items):
        self.added.extend(items)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.committed = True


class GrammarSeedTests(IsolatedAsyncioTestCase):
    async def test_deleted_starter_grammar_is_not_restored_after_initial_seed(self) -> None:
        session = SeedSession(AppState(key="starter_grammar_seeded", value="true"))

        await seed_grammar(session)

        self.assertEqual(session.added, [])
        self.assertFalse(session.committed)

    async def test_existing_grammar_is_preserved_and_marked_as_seeded(self) -> None:
        session = SeedSession(None, existing_count=2)

        await seed_grammar(session)

        self.assertEqual(len(session.added), 1)
        self.assertIsInstance(session.added[0], AppState)
        self.assertTrue(session.committed)

    async def test_empty_database_receives_starter_grammar_once(self) -> None:
        session = SeedSession(None)

        await seed_grammar(session)

        grammar_rows = [item for item in session.added if isinstance(item, Bunpou)]
        self.assertEqual(len(grammar_rows), len(STARTER_GRAMMAR))
        self.assertTrue(any(isinstance(item, AppState) for item in session.added))
