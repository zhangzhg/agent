"""让 `python -m unittest discover` 和 `pytest` 都能找到 model/view/controller/
bootstrap：把 eventhorizon/（源码根，类似 src 布局）插进 sys.path。"""
import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parent.parent / "eventhorizon"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
