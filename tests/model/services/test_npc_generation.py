"""tests/model/services/test_npc_generation.py — NPC 生成规则（README §3.6）。

之前完全没有测试覆盖（audit 发现的缺口之一）：generate_npc 是纯函数，没人验证过
产出的 Agent 是否满足文档承诺的范围/标记。
"""
import random
import unittest

from model.domain.time import Epoch, GameTime
from model.services.npc_generation import (
    NpcGenerationParams,
    _APTITUDE_MAX,
    _APTITUDE_MIN,
    _ORIGIN_FLAGS,
    generate_aptitude,
    generate_luck,
    generate_npc,
    generate_origin,
    generate_spirit_root,
)


class NpcGenerationTests(unittest.TestCase):
    def test_aptitude_stays_within_documented_bounds(self):
        rng = random.Random(1)
        for _ in range(200):
            value = generate_aptitude(rng)
            self.assertGreaterEqual(value, _APTITUDE_MIN)
            self.assertLessEqual(value, _APTITUDE_MAX)

    def test_spirit_root_is_single_or_dual_element(self):
        rng = random.Random(2)
        for _ in range(50):
            root = generate_spirit_root(rng)
            self.assertTrue(root.endswith("灵根") or root.endswith("双灵根"))

    def test_luck_is_symmetric_around_zero(self):
        rng = random.Random(3)
        values = [generate_luck(rng) for _ in range(500)]
        self.assertTrue(any(v < 0 for v in values))
        self.assertTrue(any(v > 0 for v in values))

    def test_origin_is_one_of_the_documented_four(self):
        rng = random.Random(4)
        for _ in range(50):
            self.assertIn(generate_origin(rng), _ORIGIN_FLAGS)

    def test_generate_npc_is_marked_as_npc(self):
        """is_npc 是 ScheduleService.agents_provider 筛选巡检对象的唯一信号——
        漏了这个标记，NPC 生成得再多也不会被日程巡检到。"""
        params = NpcGenerationParams(
            agent_id="王掌柜", location_id="cangwu_tavern", location_type="酒楼",
            age=45, birth_time=GameTime.new(Epoch.TAIYI, 70, 1, 1, 6), origin="商贾",
        )
        npc = generate_npc(params, rng=random.Random(5))

        self.assertTrue(npc.is_npc)
        self.assertEqual(npc.origin, "商贾")
        self.assertIn("擅长议价", npc.flags)  # 商贾出身对应的初始 flag（§6.1）
        self.assertEqual(npc.state.name, "idle")

    def test_generate_npc_random_origin_when_unspecified(self):
        params = NpcGenerationParams(
            agent_id="路人甲", location_id="cangwu", location_type="城市",
            age=30, birth_time=GameTime.new(Epoch.TAIYI, 80, 1, 1, 6),
        )
        npc = generate_npc(params, rng=random.Random(6))

        self.assertIn(npc.origin, _ORIGIN_FLAGS)


if __name__ == "__main__":
    unittest.main()
