import unittest

from model.domain.events import EventVariant, GameEventDef
from model.services.turn_result import TurnResult
from view.narrative_renderer import render_turn, safe_format


def _def(event_id, text):
    return GameEventDef(
        event_id=event_id,
        applicable_locations=("*",),
        applicable_time=None,
        predicate=None,
        weight=1.0,
        duration_shichen=1,
        cooldown_shichen=0,
        max_trigger_per_agent=None,
        exclusive_tags=(),
        priority=5,
        tags=(),
        aliases=(),
        result_pool=(),
        variants=(EventVariant(text),),
    )


class SafeFormatTests(unittest.TestCase):
    def test_known_placeholder_substituted(self):
        self.assertEqual(safe_format("你在{地点}", {"地点": "酒楼"}), "你在酒楼")

    def test_unknown_placeholder_kept_literal_not_raised(self):
        self.assertEqual(safe_format("你在{未知字段}", {}), "你在{未知字段}")

    def test_malformed_braces_do_not_raise(self):
        self.assertEqual(safe_format("坏掉的{占位符", {}), "坏掉的{占位符")


class RenderTurnTests(unittest.TestCase):
    def test_only_consumes_turn_result_fields(self):
        """render_turn 只根据 TurnResult，不构造 pipeline / 不碰 Agent。"""
        defs = {"eat": _def("eat", "你吃了饭。"), "fish": _def("fish", "水缸里有条金龙鱼！")}
        result = TurnResult(command_event_id="eat", command_variant=0, encounter_event_id="fish", encounter_variant=0)
        text = render_turn(result, defs, {})
        self.assertIn("你吃了饭。", text)
        self.assertIn("水缸里有条金龙鱼！", text)

    def test_parse_error_short_circuits(self):
        result = TurnResult(parse_error="听不懂，再说一次？")
        self.assertEqual(render_turn(result, {}, {}), "听不懂，再说一次？")

    def test_reject_reason_short_circuits(self):
        result = TurnResult(reject_reason="条件未满足。")
        self.assertEqual(render_turn(result, {}, {}), "条件未满足。")

    def test_no_parts_falls_back_to_default_text(self):
        self.assertEqual(render_turn(TurnResult(), {}, {}), "无事发生。")


if __name__ == "__main__":
    unittest.main()
