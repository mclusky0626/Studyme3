"""환경변수 설정 로딩."""
import os

from dotenv import load_dotenv

load_dotenv()

# macOS Python.org 빌드는 시스템 루트 인증서가 없어 aiohttp SSL 연결이 실패한다.
# aiohttp가 내부적으로 쓰는 _SSL_CONTEXT_VERIFIED를 certifi CA 번들로 교체한다.
try:
    import ssl as _ssl
    import certifi as _certifi
    import aiohttp.connector as _conn
    _certifi_ctx = _ssl.create_default_context(cafile=_certifi.where())
    _conn._SSL_CONTEXT_VERIFIED = _certifi_ctx
except Exception:
    pass

# 필수
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # 임베딩에 필수 (채팅은 선택)

# 선택
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# LLM 설정
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # gemini | grok | openai
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
SEARCH_MODEL = os.getenv("SEARCH_MODEL", "gemini-2.5-flash")  # 웹 검색(그라운딩) 전용

# 봇 호명어 (접두사) — 이 단어로 시작하면 봇이 응답한다.
WAKE_WORD = os.getenv("WAKE_WORD", "제비야")

# 데이터 저장 경로
DATA_DIR = os.getenv("DATA_DIR", "data")

# 동작 파라미터
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "12"))   # 채널별 최근 대화 기억 개수
MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "5"))      # 자동 기억 검색 개수
ENGAGE_WINDOW_SEC = int(os.getenv("ENGAGE_WINDOW_SEC", "90"))  # 호명 후 이 시간(초) 안에는 접두사 없이도 봇이 대화 이어감

# 첨부 이미지 저장 경로
IMAGE_DIR = os.getenv("IMAGE_DIR", "images")

# 이 이모지로 메시지에 반응하면 그 메시지 내용을 장기기억에 저장한다.
SAVE_EMOJI = os.getenv("SAVE_EMOJI", "🧠")

# 봇 페르소나 — bots.json/BOT_PERSONA로 봇마다 다르게 줄 수 있다.
PERSONA = os.getenv("BOT_PERSONA", "성격은 17세의 소녀고 가끔 부끄럼도 탄다.")

# ── AI끼리 대화 기능 ───────────────────────────────────────────────
# 평소엔 봇끼리 서로 무시하고, !대화 명령으로 시작한 활성 대화에서만 주고받는다.
AI_CHAT_ENABLED = os.getenv("AI_CHAT_ENABLED", "1") not in ("0", "false", "False", "")
AI_CHAT_MAX_TURNS_PER_BOT = int(os.getenv("AI_CHAT_MAX_TURNS_PER_BOT", "6"))  # 봇당 발화 상한(총 ≤ 2N)
AI_CHAT_TURN_DELAY = float(os.getenv("AI_CHAT_TURN_DELAY", "5"))  # 턴 사이 딜레이(초)
AI_CHAT_IDLE_SEC = int(os.getenv("AI_CHAT_IDLE_SEC", "300"))      # 이 시간 지나면 새 대화로 간주

# 형제 봇 호명어 목록 — bots.json에 정의된 모든 봇 중 '나'를 제외한 것.
ALL_WAKES: list[str] = []
SIBLING_WAKES: list[str] = []
_bots_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bots.json")
if os.path.exists(_bots_path):
    try:
        import json as _json
        with open(_bots_path, encoding="utf-8") as _f:
            _bots = _json.load(_f)
        ALL_WAKES = [
            b["wake_word"]
            for k, b in _bots.items()
            if not k.startswith("_") and isinstance(b, dict) and b.get("wake_word")
        ]
        SIBLING_WAKES = [w for w in ALL_WAKES if w != WAKE_WORD]
    except Exception:
        pass
