# 장기기억 AI 디스코드 봇

대화에서 나온 정보를 **벡터 데이터베이스(ChromaDB)** 에 저장하고, 유저 간 **관계*(친구, 연인 등)를 SQLite에 저장하는 장기기억 AI 디스코드 봇.

예시:
> A: "B는 내 친구야" → 봇이 관계 저장
> B: "내 친구가 누구야?" → 봇: "A님이요!"

## 구조

| 파일 | 역할 |
|---|---|
| `bot.py` | 디스코드 봇 본체. 반응할때 사용 |
| `llm.py` | Gemini·Grok 공용 클라이언트 + 펑션컬링 루프 |
| `memory.py` | ChromaDB 벡터 장기기억 (유저ID·닉네임 메타데이터 포함) |
| `relations.py` | SQLite 관계 그래프 + 닉네임↔유저ID 장부 |
| `tools.py` | AI가 호출하는 도구: `save_memory`, `recall_memory`, `add_relation`, `get_relations`, `find_user` |

- Gemini와 Grok 둘 다 OpenAI 호환 API를 제공하므로 `openai` SDK 하나로 두 모델을 모두 지원합니다.
- 임베딩은 xAI에 임베딩 API가 없어서 항상 Gemini(`gemini-embedding-001`)를 사용합니다. → **Gemini 키는 필수**, Grok 키는 선택.
- 모든 기억은 유저의 디스코드 ID 기준으로 저장되므로 닉네임이 바뀌어도 기억이 유지됩니다.

## 설치

```powershell
# 1. 가상환경 생성 + 패키지 설치
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 2. 환경변수 설정
copy .env.example .env
# .env 파일을 열어 토큰/API 키 입력
```


```powershell
venv\Scripts\python bot.py
```

## 사용법

봇을 **멘션**하거나, **DM**을 보내거나, **봇 메시지에 답장**하면 대화할 수 있습니다.
대화 중 나온 정보(취향, 사실, 약속)와 유저 간 관계는 AI가 펑션컬링으로 자동 저장합니다.

| 명령어 | 설명 |
|---|---|
| `!모델` | 현재 AI 모델 확인 |
| `!모델 gemini` / `!모델 grok` | 채팅 모델 전환 |
| `!기억 [@유저]` | 저장된 기억과 관계 보기 |
| `!잊어` | 나에 대한 기억·관계 전부 삭제 |
| `!도움말` | 도움말 |

## 데이터 저장 위치

- `data/chroma/` — 벡터DB (기억)
- `data/relations.db` — SQLite (관계, 닉네임 장부)

둘 다 `.gitignore`에 포함되어 있어 커밋되지 않습니다.
