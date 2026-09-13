"""model/services/live_content_author.py — 对局中解析失败兜底专用的实时创作
能力：规则解析器（chat_parser.py）和向量兜底（matching.py::find_best_matching_
command）都处理不了玩家这句话时，最后一层退路——调用大模型理解意图，创作出的
内容立即落库生效，不经过草稿/人工发布。

这是 README §1.12"对局隔离"的一次有意识例外，用户已明确要求、明确知晓后果
（会绕开 validate_event_def 的联动校验之外的一切人工审核）。跟另外两种已有的
"对局里能碰大模型"的用法都不是一回事：

  - LlmAuthorPort（model/services/ports.py）：仅限录入侧（admin_controller.py），
    产出草稿、需要人工审核发布才生效——test_layering.py 的
    PlayPathIsolationFromLlmAuthorTests 继续正确地禁止它出现在
    play_turn.py/matching.py/chat_parser.py，这条边界没有变。
  - live_narrative_writer.py（LlmEventWriter）：只补一句缺失的叙事文案，不创造
    新的 GameEventDef/Location，落库的是"补全"不是"新增"。
  - 这里（LiveContentAuthor）：明确会创造全新的 GameEventDef / Location / Route
    并立即生效——三者用途、风险、落库时机都不一样，改一个不要照抄另一个的假设。

安全边界（不是"完全不设防"，而是"不做人工审核，但仍然过自动校验/先核实数据/
先问清楚"）：
  - 事件创作的 result_pool/deferred_result_pool 只放开 state_change（跟
    LlmEventFlavorAuthor 同一套安全过滤），没有 item_drop/chain_event 这类会
    悬空引用的类型。分支事件（reply_options）的 results 是例外：额外放开
    item_drop（见 result_pool_safety.py::sanitize_branch_results 的说明——
    item_id 不要求对应真实登记的物品，这次对局临时创作的产物本来就不经草稿
    审核，Inventory 只是个 id->count 的字典，不校验也不会破坏什么）。
  - 地点创作的 kind 必须落在 LocationKind 白名单内。
  - 两种创作在动手之前都先让模型自己判断"信息够不够/说不说得通"：
    needs_clarification（缺关键信息，追问一次——见 play_turn.py 的
    PendingClarification 挂起态）、reject（说不通，直接拒绝）、ready（可以创作/
    已确认是已有内容）三态，不是"要么瞎编、要么听不懂"两态。
  - 地点创作额外带一个 list_locations 工具（真正的 function calling，见
    model/services/llm_tool_loop.py）：模型先查一遍游戏里真实存在的地点，
    发现玩家说的其实是已有地点的另一种措辞时直接复用，不新建近似重复的地点。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from model.services.llm_tool_loop import run_tool_loop
from model.services.result_pool_safety import FIELD_HINT as _FIELD_HINT
from model.services.result_pool_safety import sanitize_branch_results, sanitize_result_pool

_logger = logging.getLogger("eventhorizon.live_content_author")

# 事件触发要有结果，不能"发生了"却什么都没变——prompt 已经明确要求 result_pool
# 至少给 1 条，但实测这个模型（glm-4-flash）经常直接不给，哪怕叙事文案写得很
# 完整（三次连续试验，"帮老太太挑水""弹一曲高山流水""帮摊主吆喝""给乞丐钱"
# "练拳法"全部没带 result_pool）。复查后发现主 prompt 的 JSON 形状示例里
# "result_pool": [] 本身就是空数组——跟示例后面文字说"不能是空数组"自相矛盾，
# 模型很可能是在照抄示例格式，不是纯粹不听话；已把示例改成非空的。即便如此，
# 仍然可能漏填，所以留了两道后手：(1) author_command_event 发现漏填时先窄范围
# 补问一次（_retry_result_pool，只让模型针对已经写好的叙事单独回答 result_pool，
# 负担比"从头构思整个场景"小得多）；(2) 补问也没给时，才落到这里的默认效果——
# 跟直接拒绝整个事件相比，给一个不痛不痒但方向稳妥的默认效果更实用，总不能因为
# 模型漏填一个字段，就把一句写得好好的叙事整个扔掉，逼玩家重说一遍。用"修为略有
# 精进"：小幅正面、跟叙事内容无关也不违和，比乱猜"该加钱还是扣钱"安全。
_DEFAULT_RESULT_POOL = [{"kind": "state_change", "field": "cultivation", "delta": 1.0}]


class LlmClient(Protocol):
    def complete(self, prompt: str) -> str: ...
    def complete_with_tools(self, messages: list[dict], tools: list[dict]) -> dict: ...


# 跟 _COMMAND_PROMPT_TEMPLATE 里 JSON 形状示例的 variants 占位描述文字一字不差——
# 见 author_command_event 里"照抄示例占位符"防护的说明。改示例文案时记得同步改
# 这个常量，两边一旦不一致，这道防护就形同虚设。
_EXAMPLE_VARIANT_PLACEHOLDER = "第二人称叙事文案，40-120字，古风白话文风格"

_COMMAND_PROMPT_TEMPLATE = (
    "你是一款文字修仙游戏的实时叙事引擎。玩家当前身处「{location_type}」，说：\n"
    "「{player_text}」\n\n"
    "只输出下面三种情况之一对应的 JSON，不要有任何多余文字、解释或代码块标记"
    "（不要用 ```）：\n\n"
    "1. 这句话缺了关键信息，没法确定具体该发生什么场景（比如说了动作但看不出"
    "对象/方式，含糊到没法落笔）：只输出\n"
    '{{"needs_clarification": true, "question": "一句自然的追问，帮玩家把话说清楚"}}\n\n'
    "2. 这句话明显不构成任何合理的游戏内动作（乱敲的字符、跟修仙世界毫无关系的话、"
    "纯粹的测试文本）：只输出\n"
    '{{"reject": true}}\n\n'
    "3. 这句话确实表达了一个具体、能直接构思出场景的动作意图（即使措辞不寻常）："
    "构思一个刚好能回应这个动作的场景，只输出一个 JSON 数组，恰好 1 个元素，"
    "形如（注意示例里 result_pool 不是空的——你的输出也绝不能是空数组）：\n"
    '[{{"tags": ["生活"], "aliases": [], "variants": ["第二人称叙事文案，'
    '40-120字，古风白话文风格"], "weight": 1.0, "duration_shichen": 1, '
    '"cooldown_shichen": 0, "priority": 5, '
    '"result_pool": [{{"kind": "state_change", "field": "satiety", "delta": -5}}], '
    '"deferred_result_pool": [], "item_query": ""}}]\n'
    "（这一支适用：tags 从「生活、修炼、社交、奇遇、战斗、经济」里选 1-2 个；"
    "result_pool 必须至少给 1 条、最多 3 条，绝对不能是空数组——玩家做了这个动作，"
    "就该有点什么随之变化，哪怕很小（帮了别人得点感激/小赏钱，出了力饱食略降，"
    "动了气心魔略升，破财或得财，诸如此类），不能让「发生了」和「什么都没变」"
    "划等号；只能是 state_change，field 只能从这几个里选：" + _FIELD_HINT + "；"
    "variants 里只能用这些占位符：{{地点}} {{境界}} {{金钱}} "
    "{{年龄}} {{天气}} {{对象}}）\n\n"
    "deferred_result_pool 是可选的：只有当这个动作明显还留了一个「当下还没兑现、"
    "要等这段故事线自己收尾才会真正发生」的另一面影响时才填（比如这次帮了忙得了"
    "感激，但也可能得罪了对头、日后要找麻烦；或者顺手做了件事，后果没那么快"
    "显现）——形状跟 result_pool 一样，1-2 条，同样只能是 state_change、field 同"
    "样只能从上面那几个里选。大多数动作没有这种延后影响，这时候不用给这个字段，"
    "或者给空数组，不要为了填满它而硬凑。\n\n"
    "reply_options 也是可选的，专门用在「这个场景本身的结果取决于玩家接下来的"
    "选择」时（比如看到一件贵重物品，是买下来还是看一眼就走；遇到可疑的人，是"
    "搭话还是无视）——这种情况不要直接给 result_pool（写空数组即可，反正不会被"
    "用到），改成 2-4 个分支，形如：\n"
    '"reply_options": [\n'
    '  {{"aliases": ["买", "买下来"], "response_text": "你付了钱，把东西收好。", '
    '"results": [{{"kind": "item_drop", "item_id": "物品的中文名称", "n": 1}}, '
    '{{"kind": "state_change", "field": "money", "delta": -30}}]}},\n'
    '  {{"aliases": ["算了", "不买", "走了"], "response_text": "你看了一眼，摇摇头走开了。", '
    '"results": []}}\n'
    "]\n"
    "每个分支：aliases 是玩家接下来大概会怎么说（2-4 个短语，覆盖不同措辞）；"
    "response_text 是选中这个分支后的应答文案；results 结构跟 result_pool 一样，"
    "额外多放开一种 item_drop（表示获得一件具体实物，item_id 直接写这件物品的"
    "中文名称，不需要是游戏里已经登记过的物品——由系统兜底处理），可以留空数组"
    "表示这个分支什么都不会发生。绝大多数动作没有「等玩家选」这个维度，直接给"
    "result_pool 就够了；只有明确带有决策意味的场景才用 reply_options。"
)

_RESULT_POOL_RETRY_TEMPLATE = (
    "你刚才为一款文字修仙游戏构思了这样一段场景叙事：\n"
    "「{variant_text}」\n\n"
    "但漏填了 result_pool（游戏状态变化）——玩家做了这个动作，就该有点什么随之"
    "变化，哪怕很小，不能「发生了」等于「什么都没变」。请只针对这段叙事，补上"
    "对应的 result_pool，只输出下面这一个 JSON 对象，不要有任何多余文字、解释或"
    "代码块标记（不要用 ```）：\n"
    '{{"result_pool": [{{"kind": "state_change", "field": "字段", "delta": 数值}}]}}\n'
    "1-3 条，只能是 state_change，field 只能从这几个里选：" + _FIELD_HINT
)

# play_turn.py::_maybe_conclude_live_result 用——判断玩家这句话算不算把一条
# "留了尾巴"的伏笔翻篇了（见 PendingLiveResult 类注释）。故意设计成"宽松认定收尾"：
# 玩家明确表示不想再理会、或者聊起完全不相关的新话题，都算收尾，不要求玩家非得
# "正面回应"这条伏笔才算完——不然伏笔可能因为玩家没兴趣接话就永远悬着，把
# "未结束不能抽下一个奇遇"的限制锁死（play_turn.py 那边另有问满次数强制落地的
# 兜底，但这里先在 prompt 层面尽量避免走到那一步）。
_CONCLUSION_CHECK_TEMPLATE = (
    "游戏里有一段还没画上句号的伏笔：「{narrative_hint}」\n"
    "玩家刚说：「{player_text}」\n\n"
    "请判断，从玩家这句话来看，这段伏笔是不是已经自然收尾/翻篇了——哪怕玩家只是"
    "明确表示不想再理会这件事、或者聊起了完全不相关的新话题，只要不是还在追问/"
    "继续跟这件事互动，都算收尾。只输出下面这一个 JSON 对象，不要有任何多余"
    "文字、解释或代码块标记（不要用 ```）：\n"
    '{{"concluded": true}} 或者 {{"concluded": false}}'
)

_LOCATION_PROMPT_TEMPLATE = (
    "你是一款文字修仙游戏的实时叙事助手。玩家当前身处「{current_name}」"
    "（地点类型：{current_type}），说想去「{hint}」，但按名字/别名直接查找没找到"
    "现成的地点。你可以调用 list_locations 工具查看游戏里当前真实存在的地点，"
    "确认「{hint}」是不是其实就是某个已有地点的另一种说法（措辞不同但明显是同"
    "一个地方），避免创作出一个跟已有地点撞车的近似重复地点。\n\n"
    "确认完之后，只输出一个 JSON 对象，不要有任何多余文字、解释或代码块标记"
    "（不要用 ```），是下面这几种之一：\n"
    '1. 其实是已有地点（只是措辞不同）：{{"existing_location_id": "从 list_locations '
    '结果里选一个 location_id"}}\n'
    '2. 当前地点内部/近旁的一个新子场所（比如城市里的集市、藏经阁、演武场——玩家'
    '在城里逛逛就能到，不构成一次远行）：{{"name": "地点名，2-6个汉字，符合修仙'
    '世界观", "kind": "从这几个类型里选一个：{kinds}", "is_internal": true}}\n'
    '3. 一个明显在外部的新地方（比如另一座城市、门派、地域）：跟 2 同样的字段，'
    '"is_internal": false\n'
    '4. 这句话本身太含糊，判断不出是找已有地点还是要去一个什么样的新地方：'
    '{{"needs_clarification": true, "question": "一句自然的追问"}}\n'
    '5. 完全说不通、纯粹的胡言乱语：{{"reject": true}}'
)


@dataclass(frozen=True, slots=True)
class LiveLocationDecision:
    name: str
    kind: str
    location_type: str
    is_internal: bool


@dataclass(frozen=True, slots=True)
class LiveAuthorOutcome:
    """author_command_event/author_location 共用的三态结果——ready 才是"可以
    真的落库/生效"，needs_clarification 对应 play_turn.py 的 PendingClarification
    挂起态（追问一次，最多 3 轮，见那边的实现），reject 走调用方原有的"听不懂"/
    "找不到地方"兜底文案。"""

    kind: Literal["ready", "needs_clarification", "reject"]
    command_raw: dict | None = None
    location_decision: "LiveLocationDecision | None" = None
    existing_location_id: str | None = None
    question: str | None = None


def _clamp_float(value, default: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _clamp_int(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


class LiveContentAuthor:
    def __init__(self, client: LlmClient) -> None:
        self._client = client

    def author_command_event(self, player_text: str, location_type: str) -> LiveAuthorOutcome:
        prompt = _COMMAND_PROMPT_TEMPLATE.format(player_text=player_text, location_type=location_type)
        try:
            raw = self._client.complete(prompt)
        except Exception as exc:
            _logger.warning("实时事件创作失败：%s", exc)
            return LiveAuthorOutcome(kind="reject")
        parsed = _parse_json_value(raw)
        if isinstance(parsed, dict):
            if parsed.get("needs_clarification"):
                question = str(parsed.get("question") or "").strip()
                if question:
                    return LiveAuthorOutcome(kind="needs_clarification", question=question)
            return LiveAuthorOutcome(kind="reject")
        if not isinstance(parsed, list) or not parsed:
            return LiveAuthorOutcome(kind="reject")
        item = parsed[0]
        if not isinstance(item, dict):
            return LiveAuthorOutcome(kind="reject")
        variants = [str(v).strip() for v in item.get("variants", []) if str(v).strip()]
        # 实测偶尔会照抄 prompt 里 JSON 形状示例的占位描述文字本身（"第二人称叙事
        # 文案，40-120字，古风白话文风格"），而不是替换成真正的场景文案——这是
        # 模型把示例格式和示例内容混淆了，不是玩家该看到的东西，宁可整条拒绝也
        # 不能把这句话原样发给玩家。
        variants = [v for v in variants if v != _EXAMPLE_VARIANT_PLACEHOLDER]
        if not variants:
            return LiveAuthorOutcome(kind="reject")
        reply_options = self._build_branch_reply_options(item.get("reply_options"))
        if reply_options:
            # 分支事件：结果由玩家接下来选哪个分支决定，宿主事件自己的
            # result_pool/deferred_result_pool 永远不会被用到（跟库内既有的
            # needs_reply 事件同一套约定，见 _encounter() 测试 helper 的写法），
            # 没必要走补问/默认值兜底那一套，直接留空。
            result_pool: list[dict] = []
            deferred_result_pool: list[dict] = []
        else:
            result_pool = sanitize_result_pool(item.get("result_pool"))
            if not result_pool:
                # 模型没给结果——先补问一次（窄任务：只让模型针对已经写好的这段叙事
                # 单独回答 result_pool，跟"从头构思一整个场景"相比负担小得多，更可能
                # 老实填上），补问也没给，才真的落到模块顶部的 _DEFAULT_RESULT_POOL。
                result_pool = self._retry_result_pool(variants[0])
            if not result_pool:
                _logger.warning("实时创作的事件缺少 result_pool（含补问），落到默认效果：%s", variants[0])
                result_pool = list(_DEFAULT_RESULT_POOL)
            # 可选的"留了尾巴"的另一面影响——大多数动作没有，空数组是正常情况，
            # 不像 result_pool 那样需要默认值兜底（见 prompt 里的说明）。
            deferred_result_pool = sanitize_result_pool(item.get("deferred_result_pool"))
        command_raw = {
            "tags": [str(t).strip() for t in item.get("tags", []) if str(t).strip()],
            "aliases": [str(a).strip() for a in item.get("aliases", []) if str(a).strip()],
            "variants": variants,
            "weight": _clamp_float(item.get("weight"), default=1.0, lo=0.1, hi=5.0),
            "duration_shichen": _clamp_int(item.get("duration_shichen"), default=1, lo=0, hi=8),
            "cooldown_shichen": _clamp_int(item.get("cooldown_shichen"), default=0, lo=0, hi=48),
            "priority": _clamp_int(item.get("priority"), default=5, lo=1, hi=9),
            "result_pool": result_pool,
            "deferred_result_pool": deferred_result_pool,
            "reply_options": reply_options,
        }
        return LiveAuthorOutcome(kind="ready", command_raw=command_raw)

    def _build_branch_reply_options(self, raw_options) -> list[dict]:
        """把模型给的 reply_options 转成 validate_event_def 认得的形状（跟
        ReplyOption 字段一一对应，chain_event_id 留空——分支链到别的事件不在这次
        范围内）。至少要有 2 个合法分支才算数：只有 1 个分支等于没有选择，直接
        走普通的 result_pool 更简单，不该退化成"只有一条路"的伪分支。"""
        if not isinstance(raw_options, list):
            return []
        out: list[dict] = []
        for entry in raw_options:
            if not isinstance(entry, dict):
                continue
            aliases = [str(a).strip() for a in entry.get("aliases", []) if str(a).strip()]
            if not aliases:
                continue
            out.append({
                "aliases": aliases,
                "response_text": str(entry.get("response_text") or "").strip(),
                "results": sanitize_branch_results(entry.get("results")),
            })
            if len(out) >= 4:  # 别让一条事件的分支堆得离谱多
                break
        return out if len(out) >= 2 else []

    def check_storyline_concluded(self, narrative_hint: str, player_text: str) -> bool:
        """PendingLiveResult 攒着的延迟结果要不要在这一轮落地——见 model/domain/
        agent.py::PendingLiveResult 类注释和 play_turn.py::_maybe_conclude_live_result。
        出错/解析失败时保守地当"还没收尾"（False），留到下一轮再问，调用方那边
        自己有问满次数强制落地的兜底，这里不用替它兜底。"""
        prompt = _CONCLUSION_CHECK_TEMPLATE.format(narrative_hint=narrative_hint, player_text=player_text)
        try:
            raw = self._client.complete(prompt)
        except Exception as exc:
            _logger.warning("伏笔收尾判断失败：%s", exc)
            return False
        parsed = _parse_json_object(raw)
        if parsed is None:
            return False
        return bool(parsed.get("concluded"))

    def _retry_result_pool(self, variant_text: str) -> list[dict]:
        prompt = _RESULT_POOL_RETRY_TEMPLATE.format(variant_text=variant_text)
        try:
            raw = self._client.complete(prompt)
        except Exception as exc:
            _logger.warning("result_pool 补问失败：%s", exc)
            return []
        item = _parse_json_object(raw)
        if item is None:
            return []
        return sanitize_result_pool(item.get("result_pool"))

    def author_location(
        self, hint: str, current_location_name: str, current_location_type: str,
        list_locations: "Callable[[], list[dict]]",
    ) -> LiveAuthorOutcome:
        from model.domain.map import LocationKind

        kinds = [k.value for k in LocationKind]
        prompt = _LOCATION_PROMPT_TEMPLATE.format(
            current_name=current_location_name, current_type=current_location_type, hint=hint, kinds="、".join(kinds)
        )
        tools = [{
            "type": "function",
            "function": {
                "name": "list_locations",
                "description": "查询游戏里当前真实存在、玩家可见的地点列表",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        tool_impls = {"list_locations": lambda: list_locations()}
        content = run_tool_loop(self._client, [{"role": "user", "content": prompt}], tools, tool_impls)
        if content is None:
            return LiveAuthorOutcome(kind="reject")
        item = _parse_json_object(content)
        if item is None:
            return LiveAuthorOutcome(kind="reject")
        if item.get("reject"):
            return LiveAuthorOutcome(kind="reject")
        if item.get("needs_clarification"):
            question = str(item.get("question") or "").strip()
            if question:
                return LiveAuthorOutcome(kind="needs_clarification", question=question)
            return LiveAuthorOutcome(kind="reject")
        existing_id = item.get("existing_location_id")
        if existing_id:
            return LiveAuthorOutcome(kind="ready", existing_location_id=str(existing_id))
        name = str(item.get("name", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not name or kind not in kinds:
            return LiveAuthorOutcome(kind="reject")
        decision = LiveLocationDecision(
            name=name, kind=kind, location_type=kind, is_internal=bool(item.get("is_internal", False))
        )
        return LiveAuthorOutcome(kind="ready", location_decision=decision)


def _parse_json_value(raw: str):
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        _logger.warning("LLM output is not valid JSON, discarding")
        return None


def _parse_json_object(raw: str) -> dict | None:
    parsed = _parse_json_value(raw)
    return parsed if isinstance(parsed, dict) else None
