"""content/map.py — MVP 示例世界（GAME_DESIGN §5.1 / §5.2）。

    [藏剑山门]
        |
[黑风谷]—[苍梧城]—[落雁镇]
        |
    [归墟秘境]（隐藏，需神识扫描发现）

供内容团队起步用，非最终稿。城市内部按模板：固定集市/主街/城门 + 随机 1~3 个
（这里手选酒楼 + 当铺，代表"有酒楼的城市生活事件更丰富"）。
"""
from __future__ import annotations

from model.domain.map import Location, LocationKind, Route, WorldState

CANGWU = "cangwu"  # 苍梧城：新手出生地，生活/社交密集
CANGWU_MARKET = "cangwu_market"
CANGWU_STREET = "cangwu_street"  # 主街：出生点默认落这里
CANGWU_GATE = "cangwu_gate"
CANGWU_TAVERN = "cangwu_tavern"
CANGWU_PAWNSHOP = "cangwu_pawnshop"
LUOYAN = "luoyan"  # 落雁镇：集市为主，经济类事件密集
LUOYAN_MARKET = "luoyan_market"
CANGJIAN = "cangjian"  # 藏剑山门：拜师、修炼类事件
HEIFENG = "heifeng"  # 黑风谷：战斗/危险类事件，妖兽出没
GUIXU = "guixu"  # 归墟秘境：高境界限定，隐藏点位


def build_mvp_world() -> WorldState:
    locations = {
        CANGWU: Location(CANGWU, "苍梧城", LocationKind.CITY, "城市", qi_density=0.4),
        CANGWU_MARKET: Location(CANGWU_MARKET, "苍梧城·集市", LocationKind.MARKET, "集市", qi_density=0.4, parent_location_id=CANGWU),
        CANGWU_STREET: Location(CANGWU_STREET, "苍梧城·主街", LocationKind.CITY, "主街", qi_density=0.4, parent_location_id=CANGWU),
        CANGWU_GATE: Location(CANGWU_GATE, "苍梧城·城门", LocationKind.CITY, "城门", qi_density=0.4, parent_location_id=CANGWU),
        CANGWU_TAVERN: Location(CANGWU_TAVERN, "苍梧城·醉仙楼", LocationKind.MARKET, "酒楼", qi_density=0.4, parent_location_id=CANGWU),
        CANGWU_PAWNSHOP: Location(CANGWU_PAWNSHOP, "苍梧城·当铺", LocationKind.MARKET, "当铺", qi_density=0.4, parent_location_id=CANGWU),
        LUOYAN: Location(LUOYAN, "落雁镇", LocationKind.CITY, "城市", qi_density=0.3),
        LUOYAN_MARKET: Location(LUOYAN_MARKET, "落雁镇·集市", LocationKind.MARKET, "集市", qi_density=0.3, parent_location_id=LUOYAN),
        CANGJIAN: Location(CANGJIAN, "藏剑山门", LocationKind.SECT_GATE, "山门", qi_density=0.7),
        HEIFENG: Location(HEIFENG, "黑风谷", LocationKind.WILDERNESS, "荒野", qi_density=0.5, danger_level=0.5),
        GUIXU: Location(
            GUIXU, "归墟秘境", LocationKind.SECRET_REALM, "秘境", qi_density=0.9,
            parent_location_id=CANGWU, hidden=True, concealment=0.25,
        ),
    }
    routes = [
        Route(HEIFENG, CANGWU),
        Route(CANGWU, LUOYAN),
        Route(CANGWU, CANGJIAN),
        Route(CANGWU, CANGWU_MARKET, move_cost_shichen=0),
        Route(CANGWU, CANGWU_STREET, move_cost_shichen=0),
        Route(CANGWU, CANGWU_GATE, move_cost_shichen=0),
        Route(CANGWU, CANGWU_TAVERN, move_cost_shichen=0),
        Route(CANGWU, CANGWU_PAWNSHOP, move_cost_shichen=0),
        Route(LUOYAN, LUOYAN_MARKET, move_cost_shichen=0),
    ]
    return WorldState(locations=locations, routes=routes)


DEFAULT_SPAWN_LOCATION_ID = CANGWU_STREET
