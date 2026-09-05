"""view/templating.py — 共享的 Jinja2 模板 / 静态资源接线。

chat 页和 admin 页都从这里拿同一个 Jinja2Templates 实例（指向 view/templates/）
和同一份静态资源目录（view/static/，装 theme.css 这类两个页面共用的样式），不用
各自拼一份路径逻辑，也保证两边引用的是同一套模板/资源。
"""
from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

_VIEW_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = _VIEW_ROOT / "templates"
STATIC_DIR = _VIEW_ROOT / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
