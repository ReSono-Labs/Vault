from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.vault_runtime.memory.openai_embeddings import (
    EmbeddingUnavailable,
    OpenAIEmbeddings,
    ScopedOpenAIEmbeddingFactory,
)


def test_r1_embedding_provider_uses_real_configured_profile() -> None:
    captured: dict[str, object] = {}

    def execute(**values):
        captured.update(values)
        return [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    provider = OpenAIEmbeddings(
        "secret", safety_source="user-1:workspace-1",
        model="text-embedding-3-small", dimensions=3, executor=execute,
    )

    assert provider.embed_many(("first", "second")) == [
        [0.1, 0.2, 0.3], [0.4, 0.5, 0.6],
    ]
    assert captured == {
        "api_key": "secret",
        "model": "text-embedding-3-small",
        "inputs": ["first", "second"],
    }


def test_embedding_provider_rejects_fake_or_wrong_dimension_vectors() -> None:
    provider = OpenAIEmbeddings(
        "secret", safety_source="scope", dimensions=3,
        executor=lambda **_values: [[1.0, 2.0]],
    )
    with pytest.raises(EmbeddingUnavailable):
        provider.embed("memory")


def test_scoped_factory_uses_each_users_resolved_provider_access() -> None:
    class Credentials:
        def background_access(self, *, user_id: str, workspace_id: str):
            assert (user_id, workspace_id) == ("user-2", "workspace-2")
            return SimpleNamespace(value="individual-key"), "gpt-5.6-sol"

    provider = ScopedOpenAIEmbeddingFactory(Credentials())("user-2", "workspace-2")

    assert provider.model_key == "text-embedding-3-small"
    assert provider.dimensions == 1536
