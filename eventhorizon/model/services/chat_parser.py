"""model/services/chat_parser.py — 玩家脑洞文本解析（对应 README 1.11 /
GAME_DESIGN §3.1）。

MVP 是精确别名表，只做映射，不调用大模型/向量；失败返回 None——TODO #1 提过的
"同义词多了会退化成必须背咒语"，V2 向量匹配已经落地，但故意没放在这个类里：
PlayTurnService.handle_player_text 在这里返回 None 之后，先试向量兜底
（matching.py::find_best_matching_command），再试实时大模型创作
（live_content_author.py），两者都是"这个类解析不了"之后的下一层，不属于
"纯文本映射"这个模块的职责。

`move`/`retreat_start`/`inspect_npc` 是"系统命令"（GAME_DESIGN §3.1 表格）：不是
事件库里的 GameEventDef，直接由 ChatParser 内置识别，PlayTurnService / controller
按 event_id 特判处理，不查 EventRepository。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model.domain.events import GameEventDef
    from model.domain.scenario import ScenarioGraph

MOVE_EVENT_ID = "move"
RETREAT_START_EVENT_ID = "retreat_start"
INSPECT_NPC_EVENT_ID = "inspect_npc"
SCAN_EVENT_ID = "scan"

# 只读查询命令：不改状态、不进 AgentEventHistory，controller 直接调只读服务，不走 PlayTurnService。
QUERY_EVENT_IDS = frozenset({INSPECT_NPC_EVENT_ID, SCAN_EVENT_ID})

_MOVE_PREFIXES = ("去", "前往", "回")
_MOVE_PATTERN = re.compile(r"^(?:去|前往|回)\s*(.+)$")
# 句首版本覆盖不了"我想去{地点}"这类自然语言包裹——"去"/"前往"放宽成全文搜索
# （取第一次出现之后到句尾的内容当目的地）；"回"故意不放宽：常见于否定句
# （"我不想回去"之类），且"回{地点}"本来就是祈使句开头的固定用法，句首锚定
# 收益已经够，放宽风险更大于收益。
_MOVE_PATTERN_UNANCHORED = re.compile(r"(?:去|前往)\s*(.+)$")
# "去"在中文里大量作为动词前缀出现（去做、去看、出去、回去），放宽成全文搜索之后，
# 任何含"去"的句子都会被当成移动。两道防线：(1) parse() 里别名表先于移动解析
# （见 parse() 的说明）；(2) 这里挡住"目的地"明显不是地名的残渣——"我不想去了"
# 会切出"了"、"回去吧"会切出"去吧"，这种残渣一旦当成目的地送进 PlayTurnService，
# find_location_by_name 找不到，就会去调 LiveContentAuthor 实时创作一个叫"了"的
# 地点并写进世界快照（解析 bug 传导成持久化数据污染，真实发生过）。
_NON_PLACE_TAILS = frozenset({
    "了", "吧", "呢", "吗", "的", "啊", "呀", "着", "过",
    "去吧", "了吧", "去了", "不了", "哪", "哪儿", "哪里", "什么地方",
})
_MIN_DESTINATION_LEN = 2  # 游戏内地点名最短也是"集市""城门"这样的两字词
_RETREAT_ALIASES = ("闭关修炼", "闭关")
_INSPECT_PATTERNS = (
    re.compile(r"^打听\s*(.+)$"),
    re.compile(r"^看看那(?:个|位)?人?[，,]?\s*(.*)$"),
)
# 神识扫描（GAME_DESIGN §5.3）：不消耗回合的只读探索命令，跟 inspect_npc 同一类。
_SCAN_ALIASES = ("神识扫描", "用神识扫描", "扫描", "运转神识")
_PRONOUN_WORDS = ("它", "这个", "那个", "这", "那")
_DEFAULT_OBJECT_FILLABLE_EVENT_IDS = frozenset({"buy", "watch", "fight", "apprentice"})


def _looks_like_place(destination: str) -> bool:
    """切出来的"目的地"像不像个地名——挡住"我不想去了"切出的"了"、"回去吧"切出的
    "去吧"这类语气残渣。这类残渣一旦当成目的地送进 PlayTurnService._handle_move，
    find_location_by_name 必然找不到，接着就会调 LiveContentAuthor 实时创作一个叫
    "了"的地点并写进世界快照——解析层的小失误传导成持久化数据污染。"""
    destination = destination.strip()
    if len(destination) < _MIN_DESTINATION_LEN:
        return False
    return destination not in _NON_PLACE_TAILS


@dataclass
class ParsedCommand:
    event_id: str
    location_hint: str | None
    target: str | None
    args: dict
    is_query: bool = False  # True：只读查询，controller 不得转给 PlayTurnService


@dataclass
class ParsedReply:
    """挂起态下的解析结果：选中了哪个局部选项 / 哪条流程图出边。"""

    option_index: int | None = None  # 对应 GameEventDef.reply_options
    edge_id: str | None = None  # 对应 ScenarioEdge
    dismissed: bool = False  # 「算了」：放弃挂起项


_DISMISS_PHRASES = ("算了", "不了", "不买了", "走了", "无视", "不管了")


class ChatParser:
    def __init__(
        self,
        alias_to_event_id: dict[str, str],
        object_fillable_event_ids: frozenset[str] = _DEFAULT_OBJECT_FILLABLE_EVENT_IDS,
    ) -> None:
        """短语 → event_id，来自已发布命令型 GameEventDef.aliases（如「吃饭」→ eat）。
        object_fillable_event_ids：这些 event_id 命中「它/这个」等代词时，用
        scene_focus 回填宾语（GAME_DESIGN §3.1 代词解析）。"""
        self._alias_to_event_id = alias_to_event_id
        self._object_fillable_event_ids = object_fillable_event_ids

    def parse(self, raw_text: str, scene_focus: str | None = None) -> ParsedCommand | None:
        """只做映射。失败返回 None（听不懂）。不调用大模型。
        「去围观」在有 scene_focus 时可映射到 watch，target=scene_focus；
        代词解析：「把它买下来」等价于「把{scene_focus}买下来」（§3.1）。"""
        text = raw_text.strip()
        if not text:
            return None

        # 系统命令（打听/扫描/闭关）仍然排在事件别名表之前：它们的短语跟别名有真实
        # 重叠——"闭关修炼"里含着 MEDITATE 的别名"修炼"，先跑别名表会把闭关吞成打坐。
        for pattern in _INSPECT_PATTERNS:
            m = pattern.match(text)
            if m:
                target = m.group(1).strip() or None
                return ParsedCommand(event_id=INSPECT_NPC_EVENT_ID, location_hint=None, target=target, args={}, is_query=True)

        if any(alias in text for alias in _SCAN_ALIASES):
            return ParsedCommand(event_id=SCAN_EVENT_ID, location_hint=None, target=None, args={}, is_query=True)

        if any(alias in text for alias in _RETREAT_ALIASES):
            return ParsedCommand(event_id=RETREAT_START_EVENT_ID, location_hint=None, target=None, args={})

        # 事件别名表先于移动解析：移动的"去"是全文搜索（_MOVE_PATTERN_UNANCHORED），
        # 而"去"在中文里大量作为动词前缀出现，一旦让移动先跑，"去吃点东西"（EAT 自己
        # 注册的别名！）会被解析成"移动到『吃点东西』"，"我打算去修炼一下"会被解析成
        # "移动到『修炼一下』"——注册好的别名成了永远匹配不上的死代码，而且整条四层
        # 兜底链（README §1.13）都被这一层截胡，向量兜底/实时创作/idle_wander 全都没
        # 机会跑。移动只是众多命令里的一种，不该有优先权；只有别名都没命中，才把这
        # 句话当成移动意图来解释。
        alias_match = self._match_alias(text, scene_focus)
        if alias_match is not None:
            return alias_match

        return self._match_move(text)

    def _match_alias(self, text: str, scene_focus: str | None) -> ParsedCommand | None:
        """事件别名表匹配，**最长别名优先**。命中时顺带把"去{地点}"前缀里的地点
        摘出来当 location_hint（README 1.11 的例子："去酒楼吃饭" → 地点=酒楼、
        行动=eat），不然别名一命中就把地点信息整个丢了。

        为什么必须按长度排序而不是按字典顺序取第一个命中：别名之间存在真实的子串
        包含关系——IDLE_WANDER 的"走走看看""四处看看"里都含着 WATCH 的"看看"。
        按插入顺序遍历的话，先注册的 WATCH 会把后注册的 IDLE_WANDER 那两个别名
        永久遮死（注册了却永远匹配不上的死代码）。谁匹配得更长、谁就更具体，
        这是别名匹配该有的语义，也顺带防住以后新增别名时再踩同一个坑
        （tests/model/services/test_chat_parser.py::SeededAliasReachabilityTests
        会盯着这件事）。"""
        best_alias: str | None = None
        best_event_id: str | None = None
        for alias, event_id in self._alias_to_event_id.items():
            if alias in text and (best_alias is None or len(alias) > len(best_alias)):
                best_alias, best_event_id = alias, event_id
        if best_alias is None:
            return None
        target = self._resolve_target(text, best_alias, best_event_id, scene_focus)
        location_hint = self._extract_location_prefix(text, best_alias)
        return ParsedCommand(event_id=best_event_id, location_hint=location_hint, target=target, args={})

    @staticmethod
    def _extract_location_prefix(text: str, alias: str) -> str | None:
        """"去酒楼吃饭" + 别名"吃饭" → "酒楼"。只认"命中的别名结尾在句尾"这种最
        规整的情形，摘不干净就返回 None——宁可丢掉地点信息走原有流程，也不要摘出
        个残句来当地名（那正是 _NON_PLACE_TAILS 要防的那类污染）。"""
        m = _MOVE_PATTERN.match(text) or _MOVE_PATTERN_UNANCHORED.search(text)
        if not m:
            return None
        tail = m.group(1).strip()
        if not tail.endswith(alias):
            return None
        destination = tail[: -len(alias)].strip()
        return destination if _looks_like_place(destination) else None

    def _match_move(self, text: str) -> ParsedCommand | None:
        m = _MOVE_PATTERN.match(text) or _MOVE_PATTERN_UNANCHORED.search(text)
        if not m:
            return None
        destination = m.group(1).strip()
        if not _looks_like_place(destination):
            return None
        return ParsedCommand(event_id=MOVE_EVENT_ID, location_hint=destination, target=None, args={})

    def _resolve_target(self, text: str, alias: str, event_id: str, scene_focus: str | None) -> str | None:
        if "围观" in alias or ("看" in alias and event_id != INSPECT_NPC_EVENT_ID):
            return scene_focus
        if event_id in self._object_fillable_event_ids and scene_focus is not None:
            if any(pronoun in text for pronoun in _PRONOUN_WORDS):
                return scene_focus
        return None

    def suggest_aliases(self, candidates: "list[GameEventDef]", n: int = 2) -> list[str]:
        """从当前地点的命令池里现取 n 个常见别名，供软性引导用（GAME_DESIGN §1.1）。
        不是写死的固定文案——PlayTurnService 拿这个拼「要不试试…」。"""
        out: list[str] = []
        for defn in candidates:
            if not defn.is_command or not defn.aliases:
                continue
            out.append(defn.aliases[0])
            if len(out) >= n:
                break
        return out

    def parse_reply(
        self,
        raw_text: str,
        pending: "GameEventDef | None",
        scenario: "ScenarioGraph | None",
        node_id: str | None,
    ) -> ParsedReply | None:
        """挂起态专用：只在局部选项表里匹配（reply_options.aliases 或该节点出边的
        aliases）。与全局别名表分开，「买下来」不必注册成全局命令事件。"""
        text = raw_text.strip()
        if not text:
            return None
        if any(phrase in text for phrase in _DISMISS_PHRASES):
            return ParsedReply(dismissed=True)
        if pending is not None:
            for idx, option in enumerate(pending.reply_options):
                if any(alias in text for alias in option.aliases):
                    return ParsedReply(option_index=idx)
        if scenario is not None and node_id is not None:
            for edge in scenario.edges_from(node_id):
                if any(alias in text for alias in edge.aliases):
                    return ParsedReply(edge_id=edge.edge_id)
        return None
