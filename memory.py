"""ChromaDB 기반 벡터 장기기억 저장소."""
import os
import time
import uuid

import chromadb

import config
import llm

os.makedirs(config.DATA_DIR, exist_ok=True)
_chroma = chromadb.PersistentClient(path=os.path.join(config.DATA_DIR, "chroma"))
_col = _chroma.get_or_create_collection("memories", metadata={"hnsw:space": "cosine"})


async def save(content: str, user_id: str, user_name: str) -> str:
    vec = await llm.embed(content)
    mem_id = str(uuid.uuid4())
    _col.add(
        ids=[mem_id],
        embeddings=[vec],
        documents=[content],
        metadatas=[{"user_id": str(user_id), "user_name": user_name, "ts": time.time()}],
    )
    return mem_id


async def search(query: str, user_id: str | None = None,
                 top_k: int | None = None) -> list[dict]:
    """의미 기반 검색. user_id를 주면 그 유저에 대한 기억만 검색한다."""
    total = _col.count()
    if total == 0:
        return []
    vec = await llm.embed(query)
    res = _col.query(
        query_embeddings=[vec],
        n_results=min(top_k or config.MEMORY_TOP_K, total),
        where={"user_id": str(user_id)} if user_id else None,
    )
    return [
        {"content": doc, "user_id": meta["user_id"], "user_name": meta["user_name"]}
        for doc, meta in zip(res["documents"][0], res["metadatas"][0])
    ]


def list_for_user(user_id: str) -> list[str]:
    res = _col.get(where={"user_id": str(user_id)})
    return res["documents"] or []


def forget_user(user_id: str) -> int:
    res = _col.get(where={"user_id": str(user_id)})
    if res["ids"]:
        _col.delete(ids=res["ids"])
    return len(res["ids"])
