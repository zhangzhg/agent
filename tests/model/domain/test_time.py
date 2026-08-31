import unittest

from model.domain.time import Epoch, GameCalendar, GameTime


class GameTimeTests(unittest.TestCase):
    def test_add_shichen_rolls_over_day(self):
        t = GameTime.new(Epoch.TAIYI, 100, 1, 30, 11)
        nxt = t.add_shichen(1)
        self.assertEqual((nxt.month, nxt.day, nxt.shichen), (2, 1, 0))

    def test_add_shichen_rolls_over_year_and_recomputes_ganzhi(self):
        t = GameTime.new(Epoch.TAIYI, 1, 12, 30, 11)
        nxt = t.add_shichen(1)
        self.assertEqual(nxt.year, 2)
        self.assertEqual(nxt.ganzhi, "乙丑")  # 甲子(1) -> 乙丑(2)

    def test_ordering(self):
        a = GameTime.new(Epoch.TAIYI, 100, 1, 1, 0)
        b = a.add_shichen(5)
        self.assertLess(a, b)
        self.assertLessEqual(a, a)
        self.assertGreater(b, a)

    def test_shichen_until_is_signed(self):
        a = GameTime.new(Epoch.TAIYI, 100, 1, 1, 0)
        b = a.add_shichen(7)
        self.assertEqual(a.shichen_until(b), 7)
        self.assertEqual(b.shichen_until(a), -7)

    def test_tidal_day(self):
        d1 = GameTime.new(Epoch.TAIYI, 100, 3, 1, 0)
        d15 = GameTime.new(Epoch.TAIYI, 100, 3, 15, 0)
        d2 = GameTime.new(Epoch.TAIYI, 100, 3, 2, 0)
        self.assertTrue(GameCalendar.is_tidal_day(d1))
        self.assertTrue(GameCalendar.is_tidal_day(d15))
        self.assertFalse(GameCalendar.is_tidal_day(d2))

    def test_tidal_days_crossed_counts_once_per_hit(self):
        start = GameTime.new(Epoch.TAIYI, 100, 3, 1, 0)
        end = start.add_shichen(12 * 20)  # 跨越约 20 天，命中初一(已是start自身,不计)与十五
        count = GameCalendar.tidal_days_crossed(start, end)
        self.assertEqual(count, 1)  # 只应命中 3月15日 一次（3月1日是起点，不含在(start, end]内）


if __name__ == "__main__":
    unittest.main()
