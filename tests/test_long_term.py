import shutil
import tempfile
import unittest

from src.long_term import MemoryStore


class FakeEmbeddingFunction:
    """Deterministic, dependency-free stand-in for the real OpenRouter embedding call — CRUD
    round-trips don't depend on embedding quality, only on Chroma's storage/metadata behavior.
    Implements the minimal chromadb.api.types.EmbeddingFunction protocol so Chroma's persisted
    collection-config validation accepts it."""

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [[float(hash(text) % 997) / 997.0] * 8 for text in input]

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self(input)

    @staticmethod
    def name() -> str:
        return "fake"

    def get_config(self) -> dict:
        return {}

    @staticmethod
    def build_from_config(config: dict) -> "FakeEmbeddingFunction":
        return FakeEmbeddingFunction()


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = MemoryStore(
            path=self.tmpdir,
            collection_name="test_memories",
            embedding_function=FakeEmbeddingFunction(),
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_memory_creates_active_record(self):
        memory = self.store.save_memory("User is vegetarian", "dietary preference", 4, "I'm a vegetarian")
        self.assertEqual(memory["content"], "User is vegetarian")
        self.assertEqual(memory["label"], "dietary preference")
        self.assertEqual(memory["importance"], 4)
        self.assertEqual(memory["status"], "active")
        self.assertEqual(memory["supersedes"], "")

    def test_update_memory_is_non_destructive(self):
        original = self.store.save_memory("User is vegetarian", "dietary preference", 4, "I'm a vegetarian")
        updated = self.store.update_memory(original["id"], "User is pescatarian", "Actually I eat fish now")

        self.assertEqual(updated["content"], "User is pescatarian")
        self.assertEqual(updated["supersedes"], original["id"])
        self.assertEqual(updated["supersedes_content"], "User is vegetarian")

        all_memories = {m["id"]: m for m in self.store.list_memories(include_inactive=True)}
        self.assertEqual(all_memories[original["id"]]["status"], "superseded")
        self.assertNotEqual(all_memories[original["id"]]["valid_until"], "")
        self.assertEqual(all_memories[updated["id"]]["status"], "active")

    def test_update_memory_raises_for_unknown_id(self):
        with self.assertRaises(ValueError):
            self.store.update_memory("does-not-exist", "new content", "some message")

    def test_delete_memory_is_soft(self):
        memory = self.store.save_memory("User is allergic to peanuts", "food allergy", 5, "I'm allergic to peanuts")
        deleted = self.store.delete_memory(memory["id"])

        self.assertEqual(deleted["status"], "deleted")

        active = self.store.list_memories()
        self.assertNotIn(memory["id"], [m["id"] for m in active])

        everything = self.store.list_memories(include_inactive=True)
        self.assertIn(memory["id"], [m["id"] for m in everything])

    def test_delete_memory_raises_for_unknown_id(self):
        with self.assertRaises(ValueError):
            self.store.delete_memory("does-not-exist")

    def test_list_memories_excludes_inactive_by_default(self):
        active = self.store.save_memory("User is vegetarian", "dietary preference", 4, "msg")
        to_delete = self.store.save_memory("User likes tea", "beverage preference", 2, "msg")
        self.store.delete_memory(to_delete["id"])

        result_ids = [m["id"] for m in self.store.list_memories()]
        self.assertIn(active["id"], result_ids)
        self.assertNotIn(to_delete["id"], result_ids)

    def test_query_active_returns_similarity_and_metadata(self):
        memory = self.store.save_memory("User is vegetarian", "dietary preference", 4, "msg")
        results = self.store.query_active("What do I eat?", n_results=15)

        self.assertTrue(any(r["id"] == memory["id"] for r in results))
        match = next(r for r in results if r["id"] == memory["id"])
        self.assertIn("similarity", match)
        self.assertEqual(match["content"], "User is vegetarian")
        self.assertEqual(match["status"], "active")

    def test_query_active_excludes_superseded_and_deleted(self):
        original = self.store.save_memory("User is vegetarian", "dietary preference", 4, "msg")
        self.store.update_memory(original["id"], "User is pescatarian", "msg")
        deleted = self.store.save_memory("User likes tea", "beverage preference", 2, "msg")
        self.store.delete_memory(deleted["id"])

        results = self.store.query_active("anything", n_results=15)
        result_ids = [r["id"] for r in results]
        self.assertNotIn(original["id"], result_ids)  # now superseded
        self.assertNotIn(deleted["id"], result_ids)

    def test_query_active_on_empty_store_returns_empty_list(self):
        self.assertEqual(self.store.query_active("anything"), [])


if __name__ == "__main__":
    unittest.main()
