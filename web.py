"""Gemini의 Google Search 그라운딩을 이용한 웹 검색.

봇이 기억에 없는 최신 정보·사실을 물어볼 때 사용한다.
채팅 모델이 grok이어도 검색은 항상 GEMINI_API_KEY로 수행한다.
google-genai 패키지가 없으면 빈 결과를 돌려줘 봇 전체가 죽지 않게 한다.
"""
import asyncio

import config

try:
    from google import genai
    from google.genai import types
except ImportError:  # 패키지 미설치 시에도 봇이 동작하도록
    genai = None
    types = None

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _search_sync(query: str) -> dict:
    if genai is None:
        return {"available": False, "answer": "", "sources": []}
    resp = _get_client().models.generate_content(
        model=config.SEARCH_MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    answer = (resp.text or "").strip()

    # 그라운딩 출처(있으면) 뽑아내기
    sources: list[dict] = []
    for cand in resp.candidates or []:
        meta = getattr(cand, "grounding_metadata", None)
        for chunk in getattr(meta, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                sources.append({"title": getattr(web, "title", ""), "url": web.uri})
    return {"available": True, "answer": answer, "sources": sources}


async def search(query: str) -> dict:
    """블로킹 검색을 스레드에서 돌려 이벤트 루프를 막지 않게 한다."""
    if genai is None:
        return {"available": False, "answer": "", "sources": []}
    return await asyncio.to_thread(_search_sync, query)
