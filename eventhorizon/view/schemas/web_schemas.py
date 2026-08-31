"""view/schemas/web_schemas.py — Web API 的请求/响应模型（controller/web_controller.py
用它）。

这里用 Pydantic 而不是 chat_schemas.py 那套裸 dataclass：ARCHITECTURE §10 的技术
选型说明允许"如果用 Pydantic 定义请求/响应模型，放在 view/schemas/，并在
controller 层完成 Pydantic 模型 ↔ model.domain dataclass 的转换，model 包本身不
import pydantic"——FastAPI 路由本来就要用 Pydantic 做请求校验，没必要额外包一层
dataclass，但转换逻辑仍然全部留在 controller，这两份 schema 不共用、不互相依赖。
"""
from __future__ import annotations

from pydantic import BaseModel


class ChatApiRequest(BaseModel):
    agent_id: str = "player"
    text: str


class CalendarPanelDTO(BaseModel):
    text: str
    is_tidal_day: bool


class LocationPanelDTO(BaseModel):
    name: str
    location_type: str
    qi_density_icons: str
    weather: str


class CharacterPanelDTO(BaseModel):
    realm: str
    cultivation_progress_text: str
    lifespan_label: str
    satiety_icons: str
    money: float
    inventory_count: int


class SidebarDTO(BaseModel):
    calendar: CalendarPanelDTO
    location: LocationPanelDTO
    character: CharacterPanelDTO


class ChatApiResponse(BaseModel):
    narrative: str
    state_diff_lines: list[str] = []
    agent_state: str
    parse_error: str | None = None
    reject_reason: str | None = None
    sidebar: SidebarDTO
