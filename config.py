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

# LLM 설정
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # gemini | grok
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-3")
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
