"""LLM 펑션컬링 도구 정의 + 실행(dispatch)."""
import memory
import relations
import web

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "특정 유저에 대한 새로운 사실을 장기기억에 저장한다. "
                "유저의 취향, 신상정보, 사건, 약속 등 나중에 기억할 가치가 있는 정보일 때 사용. "
                "기존 사실을 정정하는 내용이면 저장 전에 recall_memory로 옛 기억을 찾아 "
                "delete_memory로 먼저 지울 것."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": (
                            "저장할 사실. 3인칭 서술로, 유저 이름과 ID를 포함해서 작성. "
                            "예: '철수(ID:123)는 고양이 두 마리를 키운다.'"
                        ),
                    },
                    "user_id": {
                        "type": "string",
                        "description": "이 사실의 주인공인 유저의 디스코드 ID",
                    },
                    "user_name": {
                        "type": "string",
                        "description": "해당 유저의 닉네임",
                    },
                },
                "required": ["content", "user_id", "user_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "장기기억에서 의미 기반(벡터) 검색을 한다. 유저에 대한 과거 정보가 필요할 때 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색할 내용 (자연어 문장)",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "특정 유저에 대한 기억만 검색하려면 그 유저의 디스코드 ID (선택)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": (
                "장기기억에서 특정 기억을 ID로 삭제한다. "
                "유저가 기존 사실을 정정하거나(예: '잘못 말했어, 사실은 ~야') "
                "잊어달라고 할 때, recall_memory 결과나 [관련 기억]에 표시된 ID로 호출."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "삭제할 기억의 ID 목록",
                    },
                },
                "required": ["memory_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_relation",
            "description": "두 유저 사이의 관계(친구, 연인, 형제, 팀원 등)를 저장한다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_a_id": {"type": "string", "description": "첫 번째 유저의 디스코드 ID"},
                    "user_a_name": {"type": "string", "description": "첫 번째 유저의 닉네임"},
                    "relation": {
                        "type": "string",
                        "description": "관계 이름. 예: '친구', '여자친구', '동생'. 방향이 있는 관계면 'B는 A의 (relation)'으로 해석된다.",
                    },
                    "user_b_id": {"type": "string", "description": "두 번째 유저의 디스코드 ID"},
                    "user_b_name": {"type": "string", "description": "두 번째 유저의 닉네임"},
                },
                "required": ["user_a_id", "user_a_name", "relation", "user_b_id", "user_b_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_relations",
            "description": "특정 유저가 포함된 모든 관계를 조회한다. '내 친구 누구야?' 같은 질문에 사용.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_ref": {
                        "type": "string",
                        "description": "유저의 디스코드 ID 또는 닉네임",
                    },
                },
                "required": ["user_ref"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "인터넷을 검색해 최신 정보나 사실을 가져온다. "
                "유저가 시사, 인물, 지명, 뉴스, 가격, 날씨 등 너의 지식만으로 "
                "확실치 않거나 최신성이 필요한 것을 물으면 사용해라."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "검색어 (자연어 또는 키워드)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_user",
            "description": "닉네임으로 서버에서 본 적 있는 유저를 찾아서 디스코드 ID를 알아낸다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "찾을 닉네임 (일부만 입력해도 됨)",
                    },
                },
                "required": ["name"],
            },
        },
    },
]


async def dispatch(name: str, args: dict) -> dict:
    if name == "save_memory":
        # unknown:이름 유저도 장부에 올려서 다음 find_user에서 찾을 수 있게 한다
        relations.remember_user(args["user_id"], args["user_name"])
        await memory.save(args["content"], args["user_id"], args["user_name"])
        return {"ok": True, "saved": args["content"]}

    if name == "recall_memory":
        found = await memory.search(args["query"], args.get("user_id"))
        if not found:
            return {"memories": [], "note": "관련된 기억이 없음"}
        return {"memories": found}

    if name == "delete_memory":
        n = memory.delete(args["memory_ids"])
        return {"ok": True, "deleted": n}

    if name == "add_relation":
        relations.remember_user(args["user_a_id"], args["user_a_name"])
        relations.remember_user(args["user_b_id"], args["user_b_name"])
        relations.add(
            args["user_a_id"], args["user_a_name"], args["relation"],
            args["user_b_id"], args["user_b_name"],
        )
        return {"ok": True}

    if name == "get_relations":
        rows = relations.get(args["user_ref"])
        if not rows:
            return {"relations": [], "note": "저장된 관계가 없음"}
        return {
            "relations": [
                {
                    "user_a": f"{r['user_a_name']}(ID:{r['user_a_id']})",
                    "relation": r["relation"],
                    "user_b": f"{r['user_b_name']}(ID:{r['user_b_id']})",
                }
                for r in rows
            ]
        }

    if name == "web_search":
        res = await web.search(args["query"])
        if not res["available"]:
            return {"error": "웹 검색 기능이 설정되어 있지 않음(google-genai 미설치)"}
        if not res["answer"]:
            return {"answer": "", "sources": [], "note": "검색 결과를 찾지 못함"}
        return {"answer": res["answer"], "sources": res["sources"]}

    if name == "find_user":
        users = relations.find_users(args["name"])
        if not users:
            return {
                "users": [],
                "note": (
                    "서버에서 본 적 없는 이름임. 디스코드 유저가 아닐 수 있음(현실 친구 등). "
                    "이 경우 저장을 거절하지 말고 user_id 자리에 'unknown:이름' 형태를 써서 "
                    "save_memory / add_relation을 그대로 진행할 것."
                ),
            }
        return {"users": users}

    return {"error": f"알 수 없는 도구: {name}"}
