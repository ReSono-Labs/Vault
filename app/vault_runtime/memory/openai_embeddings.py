"""R1 OpenAI embedding provider adapted to Vault user/workspace authority."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.vault_runtime.voice.credentials import VoiceProviderCredentialStore


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536
MAX_EMBEDDING_INPUT_CHARACTERS = 16_384

EmbedExecutor = Callable[..., list[list[float]]]


class EmbeddingUnavailable(RuntimeError):
    code = "embedding_unavailable"


class OpenAIEmbeddings:
    """Real provider vectors only; never substitutes hash or keyword vectors."""

    API_ROOT = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: str,
        *,
        safety_source: str,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
        executor: EmbedExecutor | None = None,
    ) -> None:
        if not api_key.strip():
            raise EmbeddingUnavailable("Embedding provider access is unavailable.")
        self._api_key = api_key
        self._safety_id = hashlib.sha256(
            f"resono-vault:{safety_source}".encode("utf-8")
        ).hexdigest()
        self._model = model
        self._dimensions = int(dimensions)
        self._executor = executor

    @property
    def model_key(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        return self.embed_many((text,))[0]

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        cleaned = [item.strip() for item in texts if item and item.strip()]
        if not cleaned:
            raise EmbeddingUnavailable("No text was provided for embedding.")
        if any(len(item) > MAX_EMBEDDING_INPUT_CHARACTERS for item in cleaned):
            raise EmbeddingUnavailable("Embedding input exceeds the supported bound.")
        vectors = (
            self._executor(api_key=self._api_key, model=self._model, inputs=cleaned)
            if self._executor is not None
            else self._http_embed(cleaned)
        )
        return _validate_vectors(vectors, self._dimensions)

    def _http_embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps(
            {"model": self._model, "input": texts, "dimensions": self._dimensions},
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self.API_ROOT + "/embeddings",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "OpenAI-Safety-Identifier": self._safety_id,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read(8_388_608).decode("utf-8"))
        except HTTPError as error:
            code = "credential_rejected" if int(error.code) in (401, 403) else "provider_rejected"
            raise EmbeddingUnavailable(
                f"OpenAI rejected the embedding request ({code})."
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise EmbeddingUnavailable("OpenAI embeddings are currently unreachable.") from error
        data = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingUnavailable("OpenAI returned an invalid embedding response.")
        ordered = sorted(
            (item for item in data if isinstance(item, dict)),
            key=lambda item: int(item.get("index", 0)),
        )
        return [list(item.get("embedding", [])) for item in ordered]


class ScopedOpenAIEmbeddingFactory:
    """Resolves shared or individual provider access for one Vault user scope."""

    def __init__(self, credentials: VoiceProviderCredentialStore) -> None:
        self._credentials = credentials

    def __call__(self, user_id: str, workspace_id: str) -> OpenAIEmbeddings:
        principal = type("ScopedPrincipal", (), {"user_id": user_id, "workspace_id": workspace_id})()
        try:
            credential = self._credentials.resolve(principal, "openai")
        except (AttributeError, TypeError):
            credential, _model = self._credentials.background_access(
                user_id=user_id, workspace_id=workspace_id,
            )
        return OpenAIEmbeddings(
            credential.value, safety_source=f"{user_id}:{workspace_id}",
        )


def _validate_vectors(
    vectors: list[list[float]], expected_dimensions: int,
) -> list[list[float]]:
    if not isinstance(vectors, list) or not vectors:
        raise EmbeddingUnavailable("Embedding provider returned no vectors.")
    validated: list[list[float]] = []
    for vector in vectors:
        if not isinstance(vector, list) or len(vector) != expected_dimensions:
            raise EmbeddingUnavailable("Embedding vector has unexpected dimensions.")
        try:
            values = [float(value) for value in vector]
        except (TypeError, ValueError) as error:
            raise EmbeddingUnavailable("Embedding vector is not numeric.") from error
        if any(value != value or abs(value) == float("inf") for value in values):
            raise EmbeddingUnavailable("Embedding vector contains a non-finite value.")
        validated.append(values)
    return validated
