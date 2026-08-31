import unittest

from model.domain.predicates import EvalContext, Predicate, PredicateGroup, PredicateType, evaluate


class _FixedContext:
    def __init__(self, **kwargs):
        self._values = kwargs

    def attr(self, name):
        return self._values.get(name, 0)

    def realm_rank(self):
        return self._values.get("realm_rank", 0)

    def money(self):
        return self._values.get("money", 0)

    def age(self):
        return self._values.get("age", 0)

    def has_item(self, item_id):
        return item_id in self._values.get("items", ())

    def flag(self, name):
        return name in self._values.get("flags", ())

    def location_type(self):
        return self._values.get("location_type", "")

    def has_cause(self, tag, target):
        return (tag, target) in self._values.get("causes", ())


class PredicateTests(unittest.TestCase):
    def test_leaf_predicates(self):
        ctx = _FixedContext(money=10, realm_rank=2, age=30, items=("玉佩",), flags=("已拜师",), location_type="酒馆")
        self.assertTrue(evaluate(Predicate(PredicateType.MONEY_GTE, (5,)), ctx))
        self.assertFalse(evaluate(Predicate(PredicateType.MONEY_GTE, (50,)), ctx))
        self.assertTrue(evaluate(Predicate(PredicateType.REALM_GTE, (2,)), ctx))
        self.assertTrue(evaluate(Predicate(PredicateType.HAS_ITEM, ("玉佩",)), ctx))
        self.assertTrue(evaluate(Predicate(PredicateType.FLAG, ("已拜师",)), ctx))
        self.assertTrue(evaluate(Predicate(PredicateType.LOCATION_TYPE, ("酒馆",)), ctx))

    def test_and_group_requires_all(self):
        ctx = _FixedContext(money=10, age=6)
        group = PredicateGroup(
            op="AND",
            items=(Predicate(PredicateType.MONEY_GTE, (5,)), Predicate(PredicateType.AGE_GTE, (18,))),
        )
        self.assertFalse(group.evaluate(ctx))  # age 不满足

    def test_or_group_requires_any(self):
        ctx = _FixedContext(money=0, age=30)
        group = PredicateGroup(
            op="OR",
            items=(Predicate(PredicateType.MONEY_GTE, (5,)), Predicate(PredicateType.AGE_GTE, (18,))),
        )
        self.assertTrue(group.evaluate(ctx))  # age 满足即可

    def test_nested_group(self):
        ctx = _FixedContext(money=0, age=30, flags=("已拜师",))
        group = PredicateGroup(
            op="AND",
            items=(
                Predicate(PredicateType.AGE_GTE, (18,)),
                PredicateGroup(op="OR", items=(Predicate(PredicateType.MONEY_GTE, (100,)), Predicate(PredicateType.FLAG, ("已拜师",)))),
            ),
        )
        self.assertTrue(group.evaluate(ctx))


if __name__ == "__main__":
    unittest.main()
