"""LLM 펑션컬링 도구 정의 + 실행(dispatch)."""
import memory
import relations

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "특정 유저에 대한 새로운 사실을 장기기억에 저장한다. "
                "유저의 취향, 신상정보, 사건, 약속 등 나중에 기억할 가치가 있는 정보일 때 사용."
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
        await memory.save(args["content"], args["user_id"], args["user_name"])
        return {"ok": True, "saved": args["content"]}

    if name == "recall_memory":
        found = await memory.search(args["query"], args.get("user_id"))
        if not found:
            return {"memories": [], "note": "관련된 기억이 없음"}
        return {"memories": found}

    if name == "add_relation":
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

    if name == "find_user":
        users = relations.find_users(args["name"])
        if not users:
            return {"users": [], "note": "해당 닉네임의 유저를 본 적이 없음"}
        return {"users": users}

    return {"error": f"알 수 없는 도구: {name}"}
