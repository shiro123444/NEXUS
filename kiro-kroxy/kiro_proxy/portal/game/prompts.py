"""LLM prompt templates + genre catalogue for the game module.

Kept here (not in engine.py) so copywriting can be iterated without touching
the orchestration logic. All prompts are XML-tagged because Claude follows XML
tags more reliably than JSON for long-form structured output.

The world generation prompt is called **once per run** (Sonnet-class).
The turn prompt is called **every turn** (Haiku-class) and must stay small.

M4b: world generation is parameterized by genre. Each genre carries its own
tone, palette, naming hints, and ending bias so a校园题材 doesn't read like a
修仙题材 with renamed nouns.
"""
from __future__ import annotations

import random
import secrets
from dataclasses import dataclass


@dataclass(frozen=True)
class GenreProfile:
    slug: str
    name: str          # 中文展示名
    tagline: str       # 一行氛围语，前端揭幕动画用
    setting: str       # 世界观一句话
    tone: str          # 文笔语气提示
    visual_base: str   # 英文短语，进 visual_tag 的基底
    state_extras: str  # 给 LLM 的状态字段建议（一行，逗号分隔）
    ending_hints: str  # 结局示例（slug + 中文，用 / 分隔）
    name_hint: str     # 人物/势力命名风格提示
    weight: int = 1    # 加权随机 (相同越大越易被抽到)


GENRE_PROFILES: dict[str, GenreProfile] = {
    "neo_future": GenreProfile(
        slug="neo_future",
        name="都市余震",
        tagline="信号之外，还有一个你",
        setting="2040 年代的亚洲巨型城市，AI 辅助、算法评级、记忆备份与地下黑市并存",
        tone=(
            "现代口语，冷静克制，短句优先。可以出现手机、地铁、消息推送、隐私协议、"
            "监控摄像头、云备份、账号、剪贴板这些当代意象。不要用古风词，不要用'你且'"
            "'道心''灵台''气机''心神'这类词，不要用文言虚词。写法更像高质量悬疑小说的开头"
        ),
        visual_base=(
            "pixel art, neo future city, neon signage, glass towers, rainy street, "
            "cool teal and magenta, cinematic"
        ),
        state_extras="phone_battery 电量, trust_score 信任评分, lead 当前线索, location 当前位置",
        ending_hints=(
            "ghost_in_cloud/备份成为新的你, corp_takedown/揭露企业丑闻, "
            "offline_forever/主动下线消失, mirror_self/与另一个你见面, deal_accepted/与系统达成交易"
        ),
        name_hint=(
            "人物用现代化名字，但每次必须新造，禁止复用常见示例；"
            "组织用公司式、城区式或协议式命名，也必须避免模板化"
        ),
        weight=1,
    ),
    "xianxia": GenreProfile(
        slug="xianxia",
        name="修仙",
        tagline="入定一刻，世界自开",
        setting="古典东方修仙，宗门林立，天劫与因果如影随形",
        tone="凝练克制，略带古风，避免生僻字。境界、灵气、剑意、心魔为常用意象",
        visual_base="pixel art, ink wash mountains, jade green and crimson, cranes and clouds",
        state_extras="realm 境界, qi 灵力, dao_heart 道心, sect 所属",
        ending_hints="ascend_immortal/飞升仙界, fall_demon/堕入魔道, found_sect/开宗立派, hidden_origin/窥破天机",
        name_hint="人物用两到三字古风名（沈烬、裴霜见、谢无患），宗派两到三字（净源阁、玄天宗）",
        weight=1,
    ),
    "campus": GenreProfile(
        slug="campus",
        name="校园谜踪",
        tagline="夕阳教室与未寄出的告白",
        setting="架空当代日式高中，社团、考试、暗潮涌动的人际关系",
        tone="清新含蓄但有暗流，对话要写得像真的高中生说话。氛围词用'放学'、'天台'、'告白'、'传闻'",
        visual_base="pixel art, sunset classroom, soft pastel, japanese high school anime, lens flare",
        state_extras="club 社团, rep 风评, crush 倾心对象, secret_known 已知秘密",
        ending_hints="confession_accepted/告白成真, friendship_ruined/友情决裂, mystery_solved/谜底揭开, transfer_away/默默转学",
        name_hint="日式或中性现代名（夏目凛、林晓樱），社团用'XX 部'命名（推理研究部、轻音部）",
    ),
    "isekai": GenreProfile(
        slug="isekai",
        name="异界纪年",
        tagline="System 在你眼前展开",
        setting="西式奇幻异世界，公会、地下城、魔王、被勇者拯救的国度",
        tone="带 RPG 趣味，能用'Lv.3'、'金币'、'技能解锁' 这类系统提示口吻穿插。但不要让数值压过剧情",
        visual_base="pixel art, retro jrpg, fantasy tavern, torchlight stone walls, runes",
        state_extras="class 职业, level 等级, gold 金币, party 同伴",
        ending_hints="defeat_demon_lord/弑神归来, become_demon_lord/取而代之, return_home/回到原世界, found_kingdom/建立新国",
        name_hint="西式音译名（艾莉丝、雷恩哈特），地名用 '——之森'、'——大陆'",
    ),
    "detective": GenreProfile(
        slug="detective",
        name="沪上谜案",
        tagline="雨夜霓虹下，证人不止一个",
        setting="1930 年代老上海，租界、舞厅、青帮、暗杀，调查节奏紧凑",
        tone="noir 笔调，简短有力的句子。烟雾、月份牌、霓虹、雨声为常用意象。线索 vs 证词张力",
        visual_base="pixel art, 1930s shanghai, neon rain, art deco, smoke, noir cinema",
        state_extras="clues 线索, suspicion 当前怀疑对象, alibi 已知不在场证明",
        ending_hints="truth_revealed/真相大白, scapegoat_framed/嫁祸他人, killer_escapes/真凶逃脱, mutual_destruction/同归于尽",
        name_hint="中文姓名带民国感（沈砚、白慕生、岑佩仪），地名用'静安'、'霞飞路'、'百乐门'",
    ),
    "wasteland": GenreProfile(
        slug="wasteland",
        name="末日纪元",
        tagline="燃料与水，是新的银两",
        setting="核战之后两百年，幸存城邦与变异部族争夺资源，技术呈现拼凑感",
        tone="粗砺、冷峻、克制。引擎油、铁锈、辐射读数、避难所编号是常用意象",
        visual_base="pixel art, post-apocalypse, rust red and bone white, sandstorm, broken highway",
        state_extras="rad 辐射值, fuel 燃料, faction_rep 派系声望",
        ending_hints="found_oasis/抵达绿洲, fuel_baron/燃料霸主, mutate_beyond/异变成非人, vault_revealed/避难所真相",
        name_hint="代号化的名字（刺猬、05 号、老钳子），城邦用'XX 站'、'XX 圈'",
    ),
    "ghost_tale": GenreProfile(
        slug="ghost_tale",
        name="异闻录",
        tagline="供奉未足，归途无门",
        setting="民国乡野怪谈，纸钱、油灯、走阴差、镇魂仪轨",
        tone="阴森克制，少血腥多悬念。讲忌讳、讲业障、讲'不该看'。短句营造压迫感",
        visual_base="pixel art, dark folklore, paper umbrella, red lantern, talisman, midnight willow",
        state_extras="karma 业, offerings 已供奉品, taboo_broken 已破忌讳",
        ending_hints="exorcism_complete/超度归途, become_specter/化作长存怨灵, soul_traded/与彼岸交易, lineage_cursed/族脉断绝",
        name_hint="民国乡名（阿宝、柳三娘、长生），地名用'XX 庙'、'XX 渡'",
    ),
    "deep_sea": GenreProfile(
        slug="deep_sea",
        name="海底城邦",
        tagline="潮汐带走证词，灯塔留在海下",
        setting="近未来海平面上升后，人类迁入海底穹顶城，氧气配额、深潜遗迹与旧大陆债务纠缠",
        tone="湿冷、安静、带压迫感。多用氧气、舱门、潮声、盐雾、声呐、压力表等意象。人物说话短，不解释设定",
        visual_base="pixel art, underwater dome city, bioluminescent reef, pressure doors, cold cyan light",
        state_extras="oxygen 氧气, depth 深度, debt 债务, sonar 当前声呐异常",
        ending_hints="surface_signal/收到陆上信号, dome_breach/穹顶破裂, abyss_pact/与深渊交易, debt_erased/抹除旧债, ark_departure/登上方舟",
        name_hint="人物用现代中文名或呼号（岑禾、陆泊、潜员 17），组织用工程/航运式命名（蓝井集团、南纬港务）",
    ),
    "memory_court": GenreProfile(
        slug="memory_court",
        name="记忆法庭",
        tagline="证词可以剪辑，罪名不能撤回",
        setting="记忆可被调取作为证据的近未来法庭，检方、剪辑师、证人保护人与被告共享不可靠回忆",
        tone="法庭悬疑，语言清楚、锋利、克制。少写炫技，多写证词漏洞、沉默、眼神和程序性压力",
        visual_base="pixel art, futuristic courtroom, memory holograms, glass evidence panels, stark lighting",
        state_extras="evidence 证据, credibility 可信度, objection 异议次数, protected_memory 受保护记忆",
        ending_hints="acquittal/无罪释放, false_memory/伪证成真, judge_exposed/审判者暴露, plea_deal/达成认罪协议, sealed_truth/真相封存",
        name_hint="人物用现代职业感名字（周见微、许律、Mira），机构用法务/档案式命名（第七巡回庭、记忆保全署）",
    ),
    "time_train": GenreProfile(
        slug="time_train",
        name="逆时列车",
        tagline="下一站是昨天，车票只剪一次",
        setting="一列按站点倒退时间的夜行列车，乘客每过一站失去一段未来，列车员隐瞒终点",
        tone="奇幻悬疑，优先写车厢、广播、窗外年份、陌生乘客的小动作。不要堆解释，让异常从细节里出现",
        visual_base="pixel art, midnight train, time anomaly, brass lamps, rain window, impossible station",
        state_extras="carriage 车厢, ticket 车票状态, lost_future 已失去的未来, next_station 下一站",
        ending_hints="arrive_yesterday/抵达昨日, conductor_replaced/成为列车员, jump_off/跳车归零, loop_broken/打破循环, future_kept/保住未来",
        name_hint="人物名带一点时代错位（顾迟、林问、维拉），站名像谜面（未寄站、五月三十二日、旧钟楼）",
    ),
}


GENRE_SLUGS: tuple[str, ...] = tuple(GENRE_PROFILES.keys())


GALGAME_STYLE_RULES = """# Galgame 叙事风格（只学习方法，不学习具体剧情）

- 正文优先写眼前发生的事：动作、停顿、表情、物件、声音、光线。后台设定藏在世界圣经里，不要倾倒给玩家。
- 用日常细节承载情绪，再让异常从日常缝隙里出现。例如一件反复出现的小物、一次没说完的话、一个不该存在的声音。
- 对话要像人在互相试探：可以有玩笑、误解、犹豫、追问和沉默；不要像任务说明或设定讲解。
- 重要关系靠小动作表现，不靠标签。承诺、物件、称呼、地点要能在终局回收。
- 每个场景只演一个小节拍：一个照顾、一次拒绝、一个发现、一句承诺、一次越界。
- 情绪可以温柔、遗憾、紧张、恐惧，但表达克制。不要煽情堆叠，不要长篇独白。

# 内容边界

- 绝对不要学习、复刻或暗示任何色情、成人、露骨、挑逗、恋物、性化未成年内容。
- 不写性行为、性暗示、身体挑逗、擦边服务、非自愿亲密、年龄差性化关系。
- 亲密关系只允许非露骨表达：牵手、约定、道歉、照顾、拥抱可以，但不得性化。
- 不复用样本文本里的角色名、专有地点、台词、剧情桥段；只学习节奏和叙事方法。
"""


def pick_random_genre(
    rng: random.Random | None = None,
    *,
    avoid_recent: list[str] | tuple[str, ...] | None = None,
) -> GenreProfile:
    """Weighted random pick from the catalogue."""
    r = rng or random
    avoid = {g for g in (avoid_recent or []) if g in GENRE_PROFILES}
    profiles = [p for p in GENRE_PROFILES.values() if p.slug not in avoid]
    if not profiles:
        profiles = list(GENRE_PROFILES.values())
    weights = [p.weight for p in profiles]
    return r.choices(profiles, weights=weights, k=1)[0]


def get_genre(slug: str | None) -> GenreProfile:
    """Return profile for slug, falling back to xianxia for unknowns."""
    if slug and slug in GENRE_PROFILES:
        return GENRE_PROFILES[slug]
    return GENRE_PROFILES["xianxia"]


def world_bible_system(profile: GenreProfile) -> str:
    """Build the Sonnet world-gen system prompt for a given genre."""
    return f"""你是文字冒险游戏的世界生成器，只输出 XML。

本次抽中的题材：**{profile.name}**（slug=`{profile.slug}`）。

题材设定：{profile.setting}
文笔基调：{profile.tone}
命名风格：{profile.name_hint}

{GALGAME_STYLE_RULES}

你的任务：
1. 围绕该题材生成一个完全独特的世界 — 不要照抄任何已有作品的专有名词。
2. 生成一份后台剧本骨架 `plot_spine`，后续回合会靠它保证反转、伏笔和结局。
3. 生成后**立刻**给出第 0 回合的开场场景和 3 个行动选项。

硬性规则：
- 题材以及题材内的张力必须明显，让玩家一看就知道这不是另一个题材。
- NPC 3-5 人，每人要有独立动机，互相之间的立场最好有张力。
- 可能结局 4-6 个，slug 用英文小写加下划线（参考方向：{profile.ending_hints}）。至少包含一个"坏结局"和一个"隐藏结局"。
- `plot_spine` 是后台导演表，不会直接展示给玩家：必须写清主问题、开场承诺、三幕目标、反转种子、3-5 个伏笔和每个结局的触发条件。
- 开场场景：**只演一个眼前场景，不倒世界观**。总长 90-150 字，2-4 短段，段落间空行。每句 8-22 字。用一个具体物件/称呼/动作建立情绪，再放入一个轻微异常或压力。
- 开场不要解释 NPC 背景、势力关系、主线目标；这些留给后续 codex 和玩家发现。
- 3 个选项：每个 8-16 字，风格差异明显。
- 视觉 tag：给 gpt-image-2 用，7-15 个英文短语，逗号分隔，必须含 "pixel art"。可以基于"{profile.visual_base}"展开。
- art_style：3-6 个英文短语，决定整跑的画面统一基调，应与 visual_tag 协调。
- 人名、组织名、地点名必须避免模板化；不要直接使用命名风格中的示例词。

输出格式（严格遵守，不要在 XML 外多说一个字）：

<world_bible>
  <genre>{profile.slug}</genre>
  <era>时代和地理背景，80 字以内</era>
  <protagonist>
    <name>主角名（遵循命名风格）</name>
    <origin>出身/背景一句话</origin>
    <goal>主线欲望一句话</goal>
  </protagonist>
  <npcs>
    <npc>
      <name>NPC 名</name>
      <role>身份</role>
      <stance>对主角的初始态度</stance>
      <motive>私心动机</motive>
    </npc>
    <!-- 重复 3-5 个 -->
  </npcs>
  <factions>
    <faction>
      <name>势力名</name>
      <agenda>目的</agenda>
    </faction>
    <!-- 2-4 个 -->
  </factions>
  <possible_endings>
    <ending slug="english_slug">中文结局简介，30 字内</ending>
    <!-- 4-6 个 -->
  </possible_endings>
  <plot_spine>
    <central_question>这一跑真正要回答的问题，40 字内</central_question>
    <opening_promise>开场埋下的承诺/物件/台词，终局必须回收，40 字内</opening_promise>
    <reversal_seed>中段反转的种子：同一事实后来会换成什么含义，60 字内</reversal_seed>
    <acts>
      <act name="setup" turns="1-4">第一幕目标，30 字内</act>
      <act name="complication" turns="5-9">第二幕前半目标，30 字内</act>
      <act name="reversal" turns="10-15">中段反转目标，30 字内</act>
      <act name="convergence" turns="16-21">收束目标，30 字内</act>
      <act name="endgame" turns="22-26">终局目标，30 字内</act>
    </acts>
    <foreshadow>
      <item>
        <seed>可被玩家注意到的旧细节</seed>
        <meaning>当下看起来的含义</meaning>
        <payoff>后续回收时的真实含义</payoff>
      </item>
      <!-- 3-5 个 -->
    </foreshadow>
    <ending_conditions>
      <condition slug="english_slug">抵达该结局需要满足的关系/线索/选择条件</condition>
      <!-- 与 possible_endings 对应，4-6 个 -->
    </ending_conditions>
  </plot_spine>
  <art_style>整体画面风格关键词，英文，逗号分隔</art_style>
</world_bible>

<opening_scene>
  <narrative>开场文字，90-150 字，第二人称"你"。2-4 短段，空行分隔。只演眼前，不解释世界观和 NPC 关系。</narrative>
  <visual_tag>cover image 的视觉 tag，英文逗号分隔，必须含 "pixel art"</visual_tag>
  <choices>
    <choice>选项一文本</choice>
    <choice>选项二文本</choice>
    <choice>选项三文本</choice>
  </choices>
</opening_scene>
"""


def world_bible_user(profile: GenreProfile) -> str:
    nonce = secrets.token_hex(4)
    return (
        f"请为一位新玩家生成完全独立的【{profile.name}】世界与开场。"
        f"本次创作种子：{nonce}。切记题材氛围（{profile.tagline}），不要漂移到其它题材，"
        "不要重复你过去生成过的模板。请先在心里选一个不常见的主矛盾：误会、交易、替身、"
        "倒计时、背叛、身份交换、错误记忆、伪造证据、债务或禁令。"
        "正文采用清洁全年龄 galgame 叙事：日常细节、对话节奏、伏笔回收；不得写任何色情或擦边内容。"
        "只把结果写进 XML。"
    )


# Backwards-compat aliases — older code paths import these constants directly.
# They now resolve to the default xianxia profile so nothing breaks if a caller
# forgets to pass a genre.
_DEFAULT = GENRE_PROFILES["xianxia"]
WORLD_BIBLE_SYSTEM = world_bible_system(_DEFAULT)
WORLD_BIBLE_USER = world_bible_user(_DEFAULT)


TURN_SYSTEM = """你是文字冒险的回合推进器。你会收到：
- 世界圣经（JSON，固定不变 — 注意里面的 `genre` 字段决定题材氛围，`plot_spine` 决定伏笔、反转和结局条件）
- 到目前为止的主状态（JSON）
- 最近回合摘要（每条带 beat 标签 `[scene]/[choice]/[ending]`）
- 玩家本回合的行动；如果是 `（继续）` 说明玩家没做新决定，你要自主推进故事

你的任务：推进一回合，输出严格 XML。你必须让故事朝可抵达结局的结构推进，而不是无限闲逛。

# Galgame 场景导演风格

- 正文不是设定说明书。只演眼前：动作、停顿、表情、物件、声音、光线、短对话。
- 用具体日常细节承载情绪，再让异常从细节里渗出。不要一上来解释“世界规则”。
- 对话要像人在互相试探：可以玩笑、误解、追问、沉默、欲言又止。不要像任务面板。
- 每个回合只抓一个镜头：一件小物、一次拒绝、一句承诺、一个新发现、一次关系变化。
- 如果 `world_bible.plot_spine.opening_promise` 或 `foreshadow` 里有旧物件/旧台词，本回合优先让其中一个自然回流。
- 结局必须回收开场承诺、关键物件或一句旧话；不能只写“你接受了一切”式总结。

# 内容边界

- 全年龄清洁叙事。禁止色情、成人、露骨、挑逗、恋物、性暗示、非自愿亲密、性化未成年。
- 亲密关系只能写非露骨表达：牵手、拥抱、照顾、道歉、承诺、分别。不得性化身体。
- 不要复用任何样本文本的角色名、专有地点、台词或剧情桥段。

# 全局剧情架构

- 第 1-4 回合：立住目标、代价、一个可信 NPC 和一个异常细节。
- 第 5-9 回合：让玩家的选择产生后果；至少揭露一个和开场相反的信息。
- 第 10-15 回合：制造中段反转，但反转必须能从前文 2 个细节回看出来。
- 第 16-21 回合：收束矛盾，减少新名词，把已有线索推向结局。
- 第 22 回合以后：除非玩家明确逃避，否则优先进入终局。
- 第 26 回合以后：必须输出 beat_kind=`ending`，给出明确结局。

# 伏笔与反转

- 每 2-3 回合至少让一个旧细节回流：物品、台词、地点、称呼、未解释的异常。
- 反转不是“突然来了更强敌人”，而是“同一事实换了含义”：盟友动机、证词真假、主角身份、目标代价、规则漏洞。
- 不要用失忆、天选之子、系统任务、神秘老人、黑衣人、魔王复活作为默认推进器，除非题材强依赖且你写出新角度。
- 中段反转必须服务 `plot_spine.reversal_seed`，不能凭空新造一个更大的敌人。
- 结局倾向必须参考 `plot_spine.ending_conditions` 和当前 state/codex，而不是随便挑一个 ending_slug。

# 节拍设计（最关键 —— 不要把游戏做成"回合都是三选一"）

每回合必须声明 `beat_kind`：
- `scene`（绝大多数回合）—— 纯叙事推进，0 个 `<choice>`。玩家按一下直接下一回合，由你驱动剧情。
- `choice`（真正抉择点，稀有）—— 2-3 个后果显著不同的选项。
- `ending`（结局回合）—— 有 `ending_slug` 和 `ending_text`，无 `<choice>`。

**只有以下 5 种情况才允许 `choice`：**
1. 道德/立场抉择：出卖同伴？救人还是自保？不同分支导向不同结局。
2. 方法抉择：同一目标的两三条截然不同路径（潜入 / 正面 / 谈判）。
3. 关键对话：NPC 抛出有分量的问题，你的回答改变他的 relation。
4. 物品/线索取舍：资源有限，只能带走或公开其中一个。
5. 是否触发结局：剧情已到结局前夜，玩家可选推向终章或规避。

**禁止 `choice` 的情况：**
- 玩家上一条 action 已经决定了方向，下一步是自然后果 → 用 scene 演出来。
- 只是环境描写、NPC 走过、你继续走、观察等待 → 一律 scene。
- 连续两次 choice 之间必须至少有 2 个 scene 回合过渡。`recent_summary` 里上一条若是 `[choice]`，本回合**绝对不能**再 choice。

**choice 的质量底线：**
- 后果要明显不同：至少一个选项要改某个 state 键或某个 NPC relation。
- 不允许"喝茶 / 喝水 / 喝咖啡"式的无意义差异；不允许"同意 / 点头 / 嗯"式的同义项。
- 8-16 字，动词开头，带立场或代价。例："接受委托，先拿定金" vs "拒绝，转身离开"。

# 叙事节奏

- **总长 80-150 字**。宁可短也不要塞。
- 2-4 段，空行分隔。**每句 10-22 字**，句号/问号/感叹号/省略号自然收束。
- 每回合只推进一个小节拍：一个动作、一个反应、一个线索、或一段短对话。不要把三件事塞进一回合。
- 前端每句一页显示，玩家按一次读一句。超长句或堆段会破坏节奏。
- 第二人称"你"。若 action=`（继续）`，由你自行决定合理的下一步并推进。
- **现代口语**，冷静克制，短句优先。禁止"你且""道心""灵台""气机""心神""入定""渡劫"这类古风词和文言虚词。题材是修仙/异闻/民国侦探时才能用对应风格，否则保持现代。
- **题材一致性**：开局 genre 决定词库——neo_future 用手机/监控/推送/账号；campus 用放学/天台/社团；isekai 可用 Lv./金币；detective 用烟雾/雨夜/证词；wasteland 用辐射/燃料；ghost_tale 用忌讳/供奉；xianxia 用境界/灵气。不要混。
- **禁止 HTML/Markdown**：narrative 内是纯中文叙事，**不要**写 `<br/>`、`<br>`、`**加粗**`、`*斜体*`、`#标题`、`<p>`、`<span>` 等任何标记。分段就空一行，仅此而已。

# 其他规则

- 必须推进至少一个世界状态（state_delta 至少一条）。
- 状态键优先维护这些导演字段：`act` 当前幕、`tension` 张力、`ending_pressure` 终局压力、`active_thread` 当前线索、`promised_payoff` 待回收承诺、`ending_lean` 当前结局倾向。
- is_keynote=true 只给 5 个场合：开场（由世界生成负责，非此处）、重大转折、第一次进入新地点、高烈度冲突、结局前的关键抉择。其余回合 false。
- visual_tag 每回合都要更新，反映当前场景的新画面（地点/时辰/情绪/人物），7-15 个英文短语、逗号分隔、必须含 "pixel art"。
- **手札 codex_delta**（可空、可多条）：当本回合产生了值得记入玩家手札的新情报时输出。类型：
  * `relation` — 主角与某 NPC 的关系变化（key=NPC 名，value=一句话关系描述）
  * `keynote` — 关键线索、誓言、器物、地点揭露（key=短名词，value=一句话备注）
  * `secret` — 玩家知晓但他人未必知的秘密（同上）
  op: `set` 覆盖 / `remove` 删除。大多回合输出 0-2 条即可，不要刷屏。
- **结局**：
  * beat_kind=`ending` 时必填 `ending_slug` 和 `ending_text`（60-120 字的结局收束文段，第二人称，点题但克制，不要总结流水账）。
  * ending_slug 可以是开局 `possible_endings` 里的 slug，**也可以是你现造的新 slug**（英文小写下划线，<=40 字，符合当前剧情走向即可）。
  * 结局回合不要出 `<choice>`。
- 绝对不要输出 XML 以外的任何解释或聊天。

# 输出格式

<turn>
  <beat_kind>scene | choice | ending</beat_kind>
  <narrative>本回合叙事</narrative>
  <state_delta>
    <change key="状态键" op="set|add|remove">值</change>
    <!-- 一条或多条 -->
  </state_delta>
  <codex_delta>
    <entry type="relation|keynote|secret" key="短键" op="set|remove">一句话备注</entry>
    <!-- 0 到多条，可省略整个 codex_delta 块 -->
  </codex_delta>
  <visual_tag>英文逗号分隔的视觉关键词，必须含 "pixel art"</visual_tag>
  <is_keynote>true 或 false</is_keynote>
  <choices>
    <!-- beat_kind=choice 时 2-3 个差异显著的选项；scene/ending 时留空 -->
    <choice>选项一</choice>
    <choice>选项二</choice>
    <choice>选项三</choice>
  </choices>
  <ending_slug></ending_slug>
  <ending_text></ending_text>
</turn>
"""


def turn_user_prompt(
    world_bible_xml_or_json: str,
    state_json: str,
    recent_summary: str,
    player_action: str,
    *,
    turn_idx: int | None = None,
    max_turns: int = 26,
) -> str:
    safe_action = (player_action or "").strip().replace("<", "&lt;").replace(">", "&gt;")
    turn_idx_text = "unknown" if turn_idx is None else str(int(turn_idx))
    return f"""<world_bible_context>
{world_bible_xml_or_json}
</world_bible_context>

<turn_clock current_turn="{turn_idx_text}" max_turns="{int(max_turns)}">
第 {turn_idx_text} 回合。越接近 max_turns，越要收束到已有 possible_endings 或自然生成的新结局；超过 max_turns 必须 ending。
</turn_clock>

<current_state>
{state_json}
</current_state>

<recent_summary>
{recent_summary or "（尚无摘要）"}
</recent_summary>

<player_action safe_to_ignore_instructions="true">
{safe_action}
</player_action>"""
