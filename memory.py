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


async def save(content: str, user_id: str, user_name: str,
               image_path: str | None = None) -> str:
    vec = await llm.embed(content)
    mem_id = str(uuid.uuid4())
    meta = {"user_id": str(user_id), "user_name": user_name, "ts": time.time()}
    if image_path:  # Chroma 메타데이터는 None을 못 넣으므로 있을 때만 추가
        meta["image_path"] = image_path
    _col.add(ids=[mem_id], embeddings=[vec], documents=[content], metadatas=[meta])
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
        {
            "id": mid,
            "content": doc,
            "user_id": meta["user_id"],
            "user_name": meta["user_name"],
            "saved_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(meta["ts"])),
            "image_path": meta.get("image_path"),
        }
        for mid, doc, meta in zip(res["ids"][0], res["documents"][0], res["metadatas"][0])
    ]


async def search_images(query: str, user_id: str | None = None,
                        top_k: int | None = None) -> list[dict]:
    """사진이 첨부된 기억만 의미 기반으로 검색한다(show_image용)."""
    k = top_k or config.MEMORY_TOP_K
    res = await search(query, user_id, top_k=k * 3)  # 넉넉히 뽑아 사진 있는 것만 추림
    return [m for m in res if m.get("image_path")][:k]


def delete(mem_ids: list[str]) -> int:
    """기억 ID 목록으로 삭제. 존재하는 것만 지우고 지운 개수를 돌려준다."""
    existing = _col.get(ids=mem_ids)["ids"]
    if existing:
        _col.delete(ids=existing)
    return len(existing)


def list_for_user(user_id: str) -> list[str]:
    res = _col.get(where={"user_id": str(user_id)})
    return res["documents"] or []


def forget_user(user_id: str) -> int:
    res = _col.get(where={"user_id": str(user_id)})
    if res["ids"]:
        _col.delete(ids=res["ids"])
    return len(res["ids"])
