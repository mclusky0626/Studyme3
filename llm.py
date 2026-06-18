"""Gemini / Grok 공용 LLM 클라이언트.

두 API 모두 OpenAI 호환 엔드포인트를 제공하므로 openai SDK 하나로 처리한다.
임베딩은 xAI에 임베딩 API가 없어서 항상 Gemini를 사용한다.
"""
import asyncio
import base64
import json

from openai import AsyncOpenAI

import config

# 네이티브 google-genai (이미지 분석 시 안전필터를 끄기 위해 사용).
# OpenAI 호환 엔드포인트는 safety_settings를 받지 않아서, 조금만 선정적인
# 사진에도 응답을 통째로 비워버린다. 네이티브 SDK로는 OFF 설정이 가능하다.
try:
    from google import genai as _genai
    from google.genai import types as _gtypes
except ImportError:
    _genai = None
    _gtypes = None

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


# ── Gemini 키 자동 전환 ─────────────────────────────────────────────
# 여러 키(config.GEMINI_API_KEYS) 중 한도(429/RESOURCE_EXHAUSTED)가 찬 키를
# 만나면 다음 키로 넘어간다. 모든 Gemini 경로(채팅/임베딩/이미지)가 공유한다.
_gemini_idx = 0


def _is_quota_error(e: Exception) -> bool:
    s = str(e).lower()
    return ("429" in s or "resource_exhausted" in s or "quota" in s
            or "rate limit" in s or "rate_limit" in s or "too many requests" in s)


def _rotate_gemini() -> bool:
    """다음 Gemini 키로 전환한다. 더 없으면 False. 모든 Gemini 클라이언트를 새 키로 재생성."""
    global _gemini_idx, _genai_client
    keys = config.GEMINI_API_KEYS
    if _gemini_idx + 1 >= len(keys):
        return False
    _gemini_idx += 1
    config.GEMINI_API_KEY = keys[_gemini_idx]   # PROVIDERS/native 모두 이 값을 참조
    _clients.pop("gemini", None)                # openai 호환 클라 재생성 유도
    _genai_client = None                        # native genai 클라 재생성 유도
    import logging
    logging.getLogger("memorybot").warning(
        "Gemini 키 한도 추정 — 다음 키로 전환 (#%d/%d)", _gemini_idx + 1, len(keys))
    return True


async def _chat_create(provider: str, **kwargs):
    """chat.completions.create 래퍼. gemini면 한도 시 자동으로 키를 돌려 재시도한다."""
    while True:
        client = _client(provider)
        try:
            return await client.chat.completions.create(**kwargs)
        except Exception as e:
            if provider == "gemini" and _is_quota_error(e) and _rotate_gemini():
                continue
            raise


async def _embed_create(**kwargs):
    while True:
        client = _client("gemini")
        try:
            return await client.embeddings.create(**kwargs)
        except Exception as e:
            if _is_quota_error(e) and _rotate_gemini():
                continue
            raise


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
    res = await _embed_create(model=config.EMBED_MODEL, input=text)
    return res.data[0].embedding


_ollama_client: AsyncOpenAI | None = None


def _ollama() -> AsyncOpenAI:
    """Ollama의 OpenAI 호환 엔드포인트 클라이언트(로컬, 키 불필요)."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = AsyncOpenAI(base_url=config.OLLAMA_BASE_URL, api_key="ollama")
    return _ollama_client


# 텍스트·이미지 양쪽의 모든 위해 카테고리를 OFF로 둔다(친구끼리 사진 공유는 막을 이유가 없음).
def _all_safety_off() -> list:
    if _gtypes is None:
        return []
    # 표준 4개 카테고리만 사용한다. IMAGE_* 카테고리는 이미지 생성 모델 전용이라
    # 일반 vision 모델(gemini-*-flash 등)에 보내면 400을 낸다. vision에서는
    # SEXUALLY_EXPLICIT가 입력 이미지의 선정성도 함께 커버한다.
    cats = [
        "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT",
    ]
    out = []
    for c in cats:
        cat = getattr(_gtypes.HarmCategory, c, None)
        if cat is not None:
            out.append(_gtypes.SafetySetting(category=cat, threshold=_gtypes.HarmBlockThreshold.OFF))
    return out


_genai_client = None


def _genai_native():
    global _genai_client
    if _genai_client is None:
        _genai_client = _genai.Client(api_key=config.GEMINI_API_KEY)
    return _genai_client


def _parse_data_uri(data_uri: str) -> tuple[str, bytes]:
    """'data:image/png;base64,...' -> (mime, bytes)."""
    header, b64 = data_uri.split(",", 1)
    mime = header[5:].split(";", 1)[0] or "image/png"
    return mime, base64.b64decode(b64)


def _describe_sync(data_uri: str, prompt: str) -> str:
    mime, raw = _parse_data_uri(data_uri)
    resp = _genai_native().models.generate_content(
        model=config.GEMINI_MODEL,
        contents=[prompt, _gtypes.Part.from_bytes(data=raw, mime_type=mime)],
        config=_gtypes.GenerateContentConfig(
            safety_settings=_all_safety_off(),
            max_output_tokens=400, temperature=0.4,
        ),
    )
    return (resp.text or "").strip()


async def describe_image(data_uri: str, caption: str = "") -> str:
    """이미지가 무엇인지 한국어로 솔직하게 묘사한다(기억 저장 + 대화 반응용).

    네이티브 google-genai로 안전필터를 꺼서, 노출/선정성이 약간 있는 사진도
    얼버무리지 않고 사실대로 설명한다. 성인물 자체를 만들어내는 게 아니라,
    친구가 보낸 사진을 보고 자연스럽게 반응하기 위한 묘사다.
    """
    prompt = (
        "친구가 디스코드로 보낸 이 사진을 보고, 무엇이 보이는지 한국어로 솔직하고 구체적으로 설명해라. "
        "인물·표정·포즈·의상·사물·장소·색감·분위기 등 눈에 보이는 걸 빠짐없이 2~4문장으로 자세히. "
        "노출이나 선정성이 좀 있더라도 얼버무리거나 거절하지 말고, 친구끼리 보듯 담백하게 사실대로 말해라. "
        "검열하지 말고 무엇이 찍혀 있는지 알 수 있게."
    )
    if caption:
        prompt += f" 보낸 사람이 함께 적은 말: {caption}"
    if _genai is not None and config.GEMINI_API_KEY:
        while True:
            try:
                out = await asyncio.to_thread(_describe_sync, data_uri, prompt)
                if out:
                    return out
                break
            except Exception as e:
                if _is_quota_error(e) and _rotate_gemini():
                    continue
                import logging
                logging.getLogger("memorybot").warning("네이티브 이미지 분석 실패, 호환 경로로 폴백: %s", e)
                break
    # 폴백: OpenAI 호환 경로(안전필터 못 끔 — 차단되면 빈 문자열)
    content = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_uri}},
    ]
    res = await _chat_create(
        _current,
        model=get_model(),
        messages=[{"role": "user", "content": content}],
        max_tokens=400, temperature=0.4,
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
        msgs = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
        # gemini-2.5-flash 등 thinking 모델이 사고 토큰을 쓰고도 답을 내도록 넉넉히 둔다
        if config.ENGAGE_JUDGE == "ollama":
            res = await _ollama().chat.completions.create(
                model=config.OLLAMA_JUDGE_MODEL, messages=msgs, temperature=0, max_tokens=256)
        else:
            res = await _chat_create(
                _current, model=get_model(), messages=msgs, temperature=0, max_tokens=256)
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
    for _ in range(max_rounds):
        # _chat_create가 gemini 한도 시 키를 돌려 재시도한다.
        res = await _chat_create(
            _current, model=get_model(), messages=messages, tools=tools,
        )
        choices = _field(res, "choices", [])
        msg = _field(choices[0], "message", {}) if choices else {}
        tool_calls = _field(msg, "tool_calls") or []
        content = _field(msg, "content") or ""
        if not tool_calls:
            return content

        # thought_signature 등 벤더 전용 필드를 보존하기 위해 msg를 통째로 넣는다.
        # SDK 객체이면 model_dump(), dict이면 그대로 사용한다.
        if hasattr(msg, "model_dump"):
            messages.append(msg.model_dump(exclude_none=True))
        else:
            messages.append(msg)
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
