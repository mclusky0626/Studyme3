"""환경변수 설정 로딩."""
import os

from dotenv import load_dotenv

load_dotenv()

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

# 봇 호명어 (접두사) — 이 단어로 시작하면 봇이 응답한다.
WAKE_WORD = os.getenv("WAKE_WORD", "제비야")

# 데이터 저장 경로
DATA_DIR = os.getenv("DATA_DIR", "data")

# 동작 파라미터
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "12"))   # 채널별 최근 대화 기억 개수
MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "5"))      # 자동 기억 검색 개수
