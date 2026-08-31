import unittest

from model.services.event_bus import InProcessEventBus


class Ping:
    def __init__(self, n):
        self.n = n


class Pong:
    pass


class EventBusTests(unittest.TestCase):
    def test_subscriber_receives_published_event(self):
        bus = InProcessEventBus()
        received = []
        bus.subscribe(Ping, lambda e: received.append(e.n))
        bus.publish(Ping(1))
        self.assertEqual(received, [1])

    def test_publish_inside_handler_does_not_reenter_immediately(self):
        """本轮 dispatch 出栈后再投递下游：handler 内 publish 不重入当前 handler,
        而是先把新事件排队，等当前 flush 循环轮到它。"""
        order = []

        bus = InProcessEventBus()

        def on_ping(e):
            order.append(f"ping-start-{e.n}")
            if e.n == 1:
                bus.publish(Ping(2))  # 突破 -> 走火入魔式连锁
            order.append(f"ping-end-{e.n}")

        bus.subscribe(Ping, on_ping)
        bus.publish(Ping(1))
        # ping-start-1 必须先跑完（包括 end-1）才能轮到 ping-start-2：
        # 证明 publish(Ping(2)) 没有在 on_ping(1) 内部立即重入执行。
        self.assertEqual(order, ["ping-start-1", "ping-end-1", "ping-start-2", "ping-end-2"])

    def test_multiple_subscribers_for_same_type(self):
        bus = InProcessEventBus()
        calls = []
        bus.subscribe(Ping, lambda e: calls.append("a"))
        bus.subscribe(Ping, lambda e: calls.append("b"))
        bus.publish(Ping(1))
        self.assertEqual(calls, ["a", "b"])

    def test_unrelated_event_type_not_delivered(self):
        bus = InProcessEventBus()
        received = []
        bus.subscribe(Ping, lambda e: received.append(e))
        bus.publish(Pong())
        self.assertEqual(received, [])


if __name__ == "__main__":
    unittest.main()
