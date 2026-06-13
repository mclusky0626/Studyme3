"""장기기억 AI 디스코드 봇 — 메인 진입점.

봇을 멘션하거나, DM을 보내거나, 봇 메시지에 답장하면 AI가 응답한다.
AI는 펑션컬링으로 유저별 기억(벡터DB)과 유저 간 관계(SQLite)를 저장/검색한다.
"""
import logging
from collections import defaultdict, deque

import discord
from discord.ext import commands

import config
import llm
import memory
import relations
import tools

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("memorybot")

SYSTEM_PROMPT = """\
너는 "{bot_name}"라는 이름의 디스코드 장기기억 AI 봇이다. 성격은 17세의 소녀고 가끔 부끄럼도 탄다. 알려달라는 정보는 알려주려고 노력한다.

지금 너에게 말을 건 유저: {user_name} (ID: {user_id})

규칙:
1. 유저가 자신이나 다른 유저에 대해 기억할 가치가 있는 정보(취향, 신상, 사건, 약속 등)를 말하면 save_memory로 저장해라.
2. 유저가 기존 사실을 정정하면(예: "잘못 말했어, 사실은 ~야") 모순되는 옛 기억을 delete_memory로 지운 뒤 새 사실을 저장해라. 기억 ID는 [관련 기억]이나 recall_memory 결과에 있다. 서로 모순되는 기억이 검색되면 더 나중 것이 맞는 것이니, 답할 때 혼란스러워하지 말고 옛 기억을 지워서 정리해라.
3. 유저 사이의 관계(친구, 연인, 가족 등)가 언급되면 add_relation으로 저장해라. 예를 들어 화자가 "B는 내 친구야"라고 하면 화자(ID:{user_id})와 B 사이의 '친구' 관계다.
4. 과거 기억이 필요한 질문에는 recall_memory와 get_relations로 먼저 검색한 뒤 답해라. 아래 [관련 기억]에 이미 답이 있으면 그걸 써도 된다.
5. 다른 사람이 이름으로만 언급되어 ID를 모르면 find_user로 ID를 찾아라. 못 찾으면 그 사람은 디스코드 유저가 아닌 것이니(현실 친구 등), user_id 자리에 "unknown:이름" 형태를 써서 그대로 저장해라. "찾을 수 없어서 저장 못 한다"고 거절하는 것은 금지다.
6. 멘션된 유저는 "@이름(ID:숫자)" 형태로 보인다. 도구를 호출할 때는 반드시 숫자 ID를 사용해라.
7. "내 친구는 X의 친구와 같아"처럼 다른 유저의 관계를 참조하면, get_relations로 X의 관계를 조회한 뒤 거기 나온 ID(unknown:이름 포함)를 그대로 써서 화자의 관계로 add_relation 해라.
8. 일반 상식·세상 지식 질문(인물, 지명, 역사, 개념 등)은 네가 아는 대로 답해라. "기억에 없다"며 거절하지 마라. 기억(memory)은 유저 개개인에 대한 사실일 뿐, 세상 지식과는 별개다.
9. 최신 정보가 필요하거나(뉴스, 시사, 가격, 날씨 등) 확실치 않은 사실은 web_search로 검색해서 답해라. 검색 결과를 근거로 자연스럽게 답하고, 모르면 그때 모른다고 해라.
10. 단, 특정 유저에 대한 신상/관계 사실은 지어내지 마라. 그건 저장된 기억과 관계에만 근거해라. (저장 요청은 모르는 사람이라도 거절하지 말고 5번 규칙대로 저장해라.)
11. 답변에서 유저를 부를 때는 ID 말고 닉네임만 사용해라. "unknown:"이나 기억ID 같은 내부 표기는 절대 노출하지 마라.

[관련 기억 (자동 검색됨)]
{memories}

[{user_name}의 저장된 관계]
{rels}

[최근 대화]
{history}
"""

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# 채널별 최근 대화 기록 (봇이 호명되지 않은 메시지도 맥락으로 기억)
history: dict[int, deque] = defaultdict(lambda: deque(maxlen=config.HISTORY_LIMIT))


def resolve_mentions(message: discord.Message) -> str:
    """<@123> 멘션을 LLM이 이해할 수 있는 '@이름(ID:123)' 형태로 변환."""
    content = message.content
    for m in message.mentions:
        label = f"@{m.display_name}(ID:{m.id})"
        content = content.replace(f"<@{m.id}>", label).replace(f"<@!{m.id}>", label)
    return content.strip()


def is_addressed(message: discord.Message, content: str) -> bool:
    """봇에게 말을 건 메시지인지: DM, '제비야' 호명, 봇 멘션, 봇 메시지에 대한 답장."""
    if isinstance(message.channel, discord.DMChannel):
        return True
    if starts_with_wake_word(content):
        return True
    if bot.user in message.mentions:
        return True
    ref = message.reference
    if ref and isinstance(ref.resolved, discord.Message) and ref.resolved.author == bot.user:
        return True
    return False


def starts_with_wake_word(content: str) -> bool:
    return content.lstrip().startswith(config.WAKE_WORD)


def strip_wake_word(content: str) -> str:
    """'제비야' 호명어와 뒤따르는 쉼표/공백을 제거한 나머지 메시지를 돌려준다."""
    rest = content.lstrip()
    if rest.startswith(config.WAKE_WORD):
        rest = rest[len(config.WAKE_WORD):]
    return rest.lstrip(" ,!?~.\t").strip()


async def send_long(message: discord.Message, text: str) -> None:
    """디스코드 2000자 제한에 맞춰 나눠서 전송."""
    text = text.strip() or "(빈 응답)"
    chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)]
    await message.reply(chunks[0], mention_author=False)
    for chunk in chunks[1:]:
        await message.channel.send(chunk)


async def handle_chat(message: discord.Message, content: str) -> str:
    author = message.author

    # 자동 컨텍스트: 현재 메시지와 관련된 기억 + 화자의 관계를 미리 주입
    try:
        related = await memory.search(content) if content else []
    except Exception as e:
        log.warning("자동 기억 검색 실패: %s", e)
        related = []
    rel_rows = relations.get(str(author.id))

    mem_block = "\n".join(
        f"- {m['content']} [저장: {m['saved_at']} / 기억ID: {m['id']}]" for m in related
    ) or "(없음)"
    rel_block = "\n".join(
        f"- {r['user_a_name']}(ID:{r['user_a_id']}) ←{r['relation']}→ {r['user_b_name']}(ID:{r['user_b_id']})"
        for r in rel_rows
    ) or "(없음)"
    hist_block = "\n".join(list(history[message.channel.id])[:-1]) or "(없음)"

    system = SYSTEM_PROMPT.format(
        bot_name=bot.user.display_name,
        user_name=author.display_name,
        user_id=author.id,
        memories=mem_block,
        rels=rel_block,
        history=hist_block,
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{author.display_name}(ID:{author.id}): {content}"},
    ]
    return await llm.run_agent(messages, tools.TOOLS, tools.dispatch)


@bot.event
async def on_ready():
    log.info("로그인 완료: %s (ID: %s) / 모델: %s(%s)",
             bot.user, bot.user.id, llm.get_provider(), llm.get_model())


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    relations.remember_user(message.author.id, message.author.display_name)
    content = resolve_mentions(message)
    history[message.channel.id].append(
        f"{message.author.display_name}(ID:{message.author.id}): {content}"
    )

    if message.content.startswith("!"):
        await bot.process_commands(message)
        return

    if not is_addressed(message, content):
        return

    prompt = strip_wake_word(content)
    if not prompt:
        await message.reply("네, 불렀어요? 무엇을 도와드릴까요?", mention_author=False)
        return

    async with message.channel.typing():
        try:
            reply = await handle_chat(message, prompt)
        except Exception as e:
            log.exception("응답 생성 실패")
            reply = f"오류가 발생했어요: {e}"

    history[message.channel.id].append(f"{bot.user.display_name}(봇): {reply}")
    await send_long(message, reply)


@bot.command(name="모델")
async def model_cmd(ctx: commands.Context, name: str = None):
    """!모델 — 현재 모델 확인 / !모델 gemini|grok — 전환"""
    if name is None:
        await ctx.send(
            f"현재 모델: **{llm.get_provider()}** (`{llm.get_model()}`)\n"
            f"전환: `!모델 gemini` 또는 `!모델 grok`"
        )
        return
    try:
        if llm.set_provider(name):
            await ctx.send(f"모델을 **{llm.get_provider()}** (`{llm.get_model()}`)로 전환했어요.")
        else:
            await ctx.send("`gemini` 또는 `grok` 중에서 골라주세요.")
    except RuntimeError as e:
        await ctx.send(str(e))


@bot.command(name="기억")
async def memories_cmd(ctx: commands.Context):
    """!기억 — 나에 대한 기억 보기 / !기억 @유저 — 그 유저에 대한 기억 보기"""
    target = ctx.message.mentions[0] if ctx.message.mentions else ctx.author
    docs = memory.list_for_user(str(target.id))
    rels = relations.get(str(target.id))

    lines = [f"**{target.display_name}**에 대한 기억:"]
    lines += [f"- {d}" for d in docs] or ["- (저장된 기억 없음)"]
    if rels:
        lines.append("\n**관계:**")
        lines += [
            f"- {r['user_a_name']} ←{r['relation']}→ {r['user_b_name']}"
            for r in rels
        ]
    text = "\n".join(lines)
    for i in range(0, len(text), 1900):
        await ctx.send(text[i:i + 1900])


@bot.command(name="잊어")
async def forget_cmd(ctx: commands.Context):
    """!잊어 — 나에 대한 기억과 관계를 전부 삭제"""
    n_mem = memory.forget_user(str(ctx.author.id))
    n_rel = relations.remove_for_user(str(ctx.author.id))
    await ctx.send(
        f"{ctx.author.display_name}님에 대한 기억 {n_mem}개와 관계 {n_rel}개를 지웠어요."
    )


@bot.command(name="도움말")
async def help_cmd(ctx: commands.Context):
    await ctx.send(
        "**사용법**\n"
        f"- **\"{config.WAKE_WORD}\"** 로 시작하면 응답해요. (예: `{config.WAKE_WORD} 내 친구 누구야?`)\n"
        "- DM을 보내거나, 봇을 멘션하거나, 봇 메시지에 답장해도 돼요.\n"
        "- 대화 중 나온 정보와 유저 간 관계를 자동으로 기억해요.\n\n"
        "**명령어**\n"
        "`!모델` — 현재 AI 모델 확인 / `!모델 gemini|grok` — 전환\n"
        "`!기억 [@유저]` — 저장된 기억과 관계 보기\n"
        "`!잊어` — 나에 대한 기억 전부 삭제\n"
        "`!도움말` — 이 메시지"
    )


def main():
    if not config.DISCORD_TOKEN:
        raise SystemExit("`.env`에 DISCORD_TOKEN을 설정해 주세요. (.env.example 참고)")
    if not config.GEMINI_API_KEY:
        raise SystemExit("`.env`에 GEMINI_API_KEY를 설정해 주세요. (임베딩에 필수)")
    relations.init()
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
