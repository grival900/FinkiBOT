from functools import lru_cache

from sentence_transformers import SentenceTransformer

from backend.core.config import get_settings


@lru_cache
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(
        get_settings().embedding_model_name,
        # BAAI/bge-m3's main branch only ships pytorch_model.bin, no safetensors —
        # `use_safetensors` defaults to "probe for one anyway", which for this model
        # means a second ~2.2GB download of a safetensors conversion living on an
        # unrelated PR ref, that then goes completely unused (the model still loads
        # from pytorch_model.bin on main either way). Confirmed live: this doubled the
        # HF cache volume to ~4.3GB for weights that only need ~2.2GB. Explicitly
        # disabling the probe is a straight win with no downside — there's nothing to
        # "fall back" to since main never had safetensors to prefer in the first place.
        model_kwargs={"low_cpu_mem_usage": False, "use_safetensors": False},
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
