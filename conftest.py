"""让 `model` / `view` / `controller` / `bootstrap` 可以直接被 import：
eventhorizon/ 是源码根（类似 src 布局），不是一个叫 eventhorizon 的包前缀。
"""
import sys
from pathlib import Path

_SRC_ROOT = Path(__file__).parent / "eventhorizon"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))
