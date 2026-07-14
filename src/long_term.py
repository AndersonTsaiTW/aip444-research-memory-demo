import uuid
from datetime import datetime, timezone
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

from src.config import (
    CHROMA_PATH,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
)


def _default_embedding_function():
    return OpenAIEmbeddingFunction(
        api_key=OPENROUTER_API_KEY,
        model_name=EMBEDDING_MODEL,
        api_base=OPENROUTER_BASE_URL,
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, path: str = CHROMA_PATH, collection_name: str = COLLECTION_NAME, embedding_function=None):
        self._client = chromadb.PersistentClient(path=path)
        self._embedding_function = embedding_function or _default_embedding_function()
        self._collection_name = collection_name

    def _collection(self):
        return self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_function,
            configuration={"hnsw": {"space": "cosine"}},
        )

    def save_memory(self, content: str, label: str, importance: int, source: str) -> dict:
        memory_id = str(uuid.uuid4())
        timestamp = _now()
        metadata = {
            "content": content,
            "label": label,
            "importance": importance,
            "created_at": timestamp,
            "updated_at": timestamp,
            "source": source,
            "status": "active",
            "supersedes": "",  # Chroma metadata can't hold None; empty string means "no predecessor"
            "valid_from": timestamp,
            "valid_until": "",
        }
        self._collection().add(ids=[memory_id], documents=[f"{label}: {content}"], metadatas=[metadata])
        return {"id": memory_id, **metadata}

    def update_memory(self, memory_id: str, new_content: str, source: str) -> dict:
        """Non-destructive: marks the old row superseded and inserts a new row (§4.1)."""
        collection = self._collection()
        existing = collection.get(ids=[memory_id], include=["metadatas"])
        if not existing["ids"]:
            raise ValueError(f"No memory found with id {memory_id}")

        old_metadata = dict(existing["metadatas"][0])
        old_content = old_metadata["content"]
        timestamp = _now()

        old_metadata["status"] = "superseded"
        old_metadata["valid_until"] = timestamp
        old_metadata["updated_at"] = timestamp
        collection.update(ids=[memory_id], metadatas=[old_metadata])

        new_id = str(uuid.uuid4())
        label = old_metadata["label"]
        new_metadata = {
            "content": new_content,
            "label": label,
            "importance": old_metadata["importance"],
            "created_at": timestamp,
            "updated_at": timestamp,
            "source": source,
            "status": "active",
            "supersedes": memory_id,
            "valid_from": timestamp,
            "valid_until": "",
        }
        collection.add(ids=[new_id], documents=[f"{label}: {new_content}"], metadatas=[new_metadata])
        return {"id": new_id, "supersedes_content": old_content, **new_metadata}

    def delete_memory(self, memory_id: str) -> dict:
        """Soft delete only — status flips to 'deleted', the row is never physically removed (§4.1)."""
        collection = self._collection()
        existing = collection.get(ids=[memory_id], include=["metadatas"])
        if not existing["ids"]:
            raise ValueError(f"No memory found with id {memory_id}")

        metadata = dict(existing["metadatas"][0])
        timestamp = _now()
        metadata["status"] = "deleted"
        metadata["valid_until"] = timestamp
        metadata["updated_at"] = timestamp
        collection.update(ids=[memory_id], metadatas=[metadata])
        return {"id": memory_id, **metadata}

    def list_memories(self, include_inactive: bool = False) -> list[dict]:
        results = self._collection().get(include=["metadatas"])
        memories = [{"id": mid, **meta} for mid, meta in zip(results["ids"], results["metadatas"])]
        if not include_inactive:
            memories = [m for m in memories if m["status"] == "active"]
        memories.sort(key=lambda m: m["created_at"])
        return memories


_default_store: Optional[MemoryStore] = None


def _store() -> MemoryStore:
    global _default_store
    if _default_store is None:
        _default_store = MemoryStore()
    return _default_store


def save_memory(content: str, label: str, importance: int, source: str) -> dict:
    return _store().save_memory(content, label, importance, source)


def update_memory(memory_id: str, new_content: str, source: str) -> dict:
    return _store().update_memory(memory_id, new_content, source)


def delete_memory(memory_id: str) -> dict:
    return _store().delete_memory(memory_id)


def list_memories(include_inactive: bool = False) -> list[dict]:
    return _store().list_memories(include_inactive)
