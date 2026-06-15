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


def _field(obj, name: str, default=None):
    """OpenAI-compatible providers may return SDK objects or plain dicts."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _first_message_content(res) -> str:
    choices = _field(res, "choices", [])
    if not choices:
        return ""
    msg = _field(choices[0], "message")
    return (_field(msg, "content") or "").strip()


async def embed(text: str) -> list[float]:
    client = _client("gemini")
    res = await client.embeddings.create(model=config.EMBED_MODEL, input=text)
    return res.data[0].embedding


_ollama_client: AsyncOpenAI | None = None


def _ollama() -> AsyncOpenAI:
    """Ollama의 OpenAI 호환 엔드포인트 클라이언트(로컬, 키 불필요)."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = AsyncOpenAI(base_url=config.OLLAMA_BASE_URL, api_key="ollama")
    return _ollama_client


async def describe_image(data_uri: str, caption: str = "") -> str:
    """이미지를 나중에 검색·기억하기 좋게 한국어로 사실적으로 묘사한다(기억 저장용)."""
    prompt = (
        "이 이미지를 나중에 검색해서 떠올리기 좋게 한국어 한두 문장으로 비민감하게 묘사해라. "
        "성적 요소나 노출은 직접적·자세히 묘사하지 말고, 필요한 경우 의상, 구도, 스타일, "
        "분위기 같은 완곡한 시각 단서로만 표현해라. "
        "무엇이 보이는지 핵심 위주로(인물·사물·장소·색감·분위기). 군더더기 없이."
    )
    if caption:
        prompt += f" 보낸 사람이 함께 적은 말: {caption}"
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_uri}},
    ]
    res = await _client(_current).chat.completions.create(
        model=get_model(),
        messages=[{"role": "user", "content": content}],
        max_tokens=300, temperature=0,
    )
    return _first_message_content(res) or "이미지 설명을 생성하지 못함"


async def judge_engage(bot_name: str, history_text: str, new_message: str,
                       was_talking_to_me: bool = False) -> bool:
    """단톡방에서 봇이 이 메시지에 끼어들어 답하는 게 자연스러운지 판단한다 (YES/NO).

    호명 후 활성 창 안에서, 로컬 규칙으로 명확히 가려지지 않은 메시지에만 호출된다.
    기본 백엔드는 Ollama 로컬 경량 모델(config.ENGAGE_JUDGE)이라 토큰을 쓰지 않는다.
    핵심은 '누구에게 하는 말인가' — 다른 사람을 부르면 끼어들지 않는다.
    """
    sys = (
        f'너는 디스코드 단톡방 참여자 "{bot_name}"(봇)다. [새 메시지]가 너에게 하는 말이거나 '
        f"너에 대한 말이면 YES, 다른 사람에게 하는 말이거나 너와 무관한 사담이면 NO. "
        f"오직 YES 또는 NO로만 답해라.\n\n"
        f"판단 기준:\n"
        f"- 너를 부르거나 너에게 묻는 말 -> YES\n"
        f"- 너의 직전 말에 대한 반응/이어지는 질문 -> YES\n"
        f'- 너의 정체를 묻는 말("쟤 누구야?","봇이야?") -> YES\n'
        f'- 다른 사람 이름을 부르는 말("철수야~") -> NO\n'
        f"- 너와 상관없는 잡담 -> NO\n\n"
        f"예시:\n"
        f"[상황] {bot_name}가 방금 자기소개함 / [새 메시지] 쟤가 누구임? -> YES\n"
        f"[상황] A가 {bot_name}와 대화중 / [새 메시지] 그래서 그게 뭔데? -> YES\n"
        f"[상황] A가 {bot_name}와 대화중 / [새 메시지] 응 고마워 너 덕분이야 -> YES\n"
        f"[상황] A가 {bot_name}와 대화중 / [새 메시지] 야 철수야 밥먹자 -> NO\n"
        f"[상황] A가 {bot_name}와 대화중 / [새 메시지] 근데 영희는 언제 온대? -> NO\n"
        f"[상황] 사람들끼리 잡담중 / [새 메시지] ㅋㅋㅋ 철수 어디감 -> NO"
    )
    situation = (
        f"이 사람은 직전까지 {bot_name}와 대화 중이었다."
        if was_talking_to_me else
        f"이 사람이 직전에 {bot_name}와 대화 중이었는지는 불분명하다."
    )
    user = f"[최근 대화]\n{history_text}\n\n[상황] {situation}\n[새 메시지] {new_message}"
    try:
        if config.ENGAGE_JUDGE == "ollama":
            client, model = _ollama(), config.OLLAMA_JUDGE_MODEL
        else:
            client, model = _client(_current), get_model()
        res = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": sys},
                      {"role": "user", "content": user}],
            temperature=0,
            # gemini-2.5-flash 등 thinking 모델이 사고 토큰을 쓰고도 답을 내도록 넉넉히 둔다
            max_tokens=256,
        )
        ans = _first_message_content(res).upper()
        return ans.startswith("Y") or "YES" in ans
    except Exception as e:
        # Ollama 미설치/미실행 등 — 끼어들지 않는 쪽으로 안전하게.
        import logging
        logging.getLogger("memorybot").warning("끼어들기 판단 실패(%s): %s", config.ENGAGE_JUDGE, e)
        return False


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
        choices = _field(res, "choices", [])
        msg = _field(choices[0], "message", {}) if choices else {}
        tool_calls = _field(msg, "tool_calls") or []
        content = _field(msg, "content") or ""
        if not tool_calls:
            return content

        messages.append({
            "role": "assistant",
            "content": content,
            "tool_calls": [
                {
                    "id": _field(tc, "id"),
                    "type": "function",
                    "function": {
                        "name": _field(_field(tc, "function", {}), "name"),
                        "arguments": _field(_field(tc, "function", {}), "arguments"),
                    },
                }
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            func = _field(tc, "function", {})
            name = _field(func, "name")
            arguments = _field(func, "arguments") or "{}"
            try:
                args = json.loads(arguments)
                result = await dispatch(name, args)
            except Exception as e:  # 도구 실패가 대화 전체를 죽이지 않도록
                result = {"error": str(e)}
            messages.append({
                "role": "tool",
                "tool_call_id": _field(tc, "id"),
                "content": json.dumps(result, ensure_ascii=False),
            })

    return "도구 호출이 너무 길어져서 여기서 멈췄어요. 다시 한번 물어봐 주세요."
