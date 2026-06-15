"""Gemini / Grok 공용 LLM 클라이언트.

두 API 모두 OpenAI 호환 엔드포인트를 제공하므로 openai SDK 하나로 처리한다.
임베딩은 xAI에 임베딩 API가 없어서 항상 Gemini를 사용한다.
"""
import json

from openai import AsyncOpenAI

import config

PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key": lambda: config.GEMINI_API_KEY,
        "model": lambda: config.GEMINI_MODEL,
    },
    "grok": {
        "base_url": "https://api.x.ai/v1",
        "api_key": lambda: config.XAI_API_KEY,
        "model": lambda: config.GROK_MODEL,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key": lambda: config.OPENAI_API_KEY,
        "model": lambda: config.OPENAI_MODEL,
    },
}

_current = config.LLM_PROVIDER if config.LLM_PROVIDER in PROVIDERS else "gemini"
_clients: dict[str, AsyncOpenAI] = {}


def list_providers() -> list[str]:
    return list(PROVIDERS)


def get_provider() -> str:
    return _current


def get_model() -> str:
    return PROVIDERS[_current]["model"]()


def set_provider(name: str) -> bool:
    """모델 제공자 전환. 알 수 없는 이름이면 False, 키가 없으면 RuntimeError."""
    global _current
    name = name.lower()
    if name not in PROVIDERS:
        return False
    if not PROVIDERS[name]["api_key"]():
        raise RuntimeError(f"{name} API 키가 .env에 설정되어 있지 않아요.")
    _current = name
    return True


def _client(provider: str) -> AsyncOpenAI:
    if provider not in _clients:
        p = PROVIDERS[provider]
        key = p["api_key"]()
        if not key:
            raise RuntimeError(f"{provider} API 키가 .env에 설정되어 있지 않아요.")
        _clients[provider] = AsyncOpenAI(base_url=p["base_url"], api_key=key)
    return _clients[provider]


async def embed(text: str) -> list[float]:
    client = _client("gemini")
    res = await client.embeddings.create(model=config.EMBED_MODEL, input=text)
    return res.data[0].embedding


async def judge_addressed(bot_name: str, history_text: str, message_text: str) -> bool:
    """접두사 없는 메시지가 '봇에게 하는 말'인지 가볍게 판단한다 (YES/NO).

    호명 후 활성 대화 창 안에서만 호출되며, 끼어들기를 막기 위해 보수적으로 판단한다.
    """
    sys = (
        f'너는 디스코드 대화에서 방금 들어온 메시지가 봇 "{bot_name}"에게 하는 말인지 '
        "판단하는 분류기다. 직전까지 봇과 대화가 오갔다. 새 메시지가 봇에게 묻거나, "
        "봇의 직전 말에 답하거나, 봇이 이어서 반응하길 기대하는 흐름이면 YES. "
        "다른 사람끼리의 잡담이거나 봇과 무관하면 NO. "
        "오직 YES 또는 NO 한 단어로만 답해라."
    )
    user = f"[최근 대화]\n{history_text}\n\n[새 메시지]\n{message_text}"
    try:
        res = await _client(_current).chat.completions.create(
            model=get_model(),
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": user}],
            temperature=0,
            # gemini-2.5-flash 등 thinking 모델이 사고 토큰을 쓰고도 답을 내도록 넉넉히 둔다
            max_tokens=256,
        )
        ans = (res.choices[0].message.content or "").strip().upper()
        return ans.startswith("Y")
    except Exception:
        return False  # 판단 실패 시 끼어들지 않음


async def run_agent(messages: list[dict], tools: list[dict], dispatch,
                    max_rounds: int = 6) -> str:
    """펑션컬링 루프. 모델이 도구 호출을 멈추고 답변을 내놓을 때까지 반복한다.

    dispatch: async (name, args) -> dict 형태의 도구 실행 함수.
    """
    client = _client(_current)
    model = get_model()

    for _ in range(max_rounds):
        res = await client.chat.completions.create(
            model=model, messages=messages, tools=tools,
        )
        msg = res.choices[0].message
        if not msg.tool_calls:
            return msg.content or ""

        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
                result = await dispatch(tc.function.name, args)
            except Exception as e:  # 도구 실패가 대화 전체를 죽이지 않도록
                result = {"error": str(e)}
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return "도구 호출이 너무 길어져서 여기서 멈췄어요. 다시 한번 물어봐 주세요."
