"""EventHorizon 核心底座：事件驱动的文字修仙游戏引擎。

分层：controller（薄入口）→ model.services（用例编排）→ model.domain（纯业务模型）。
model.repositories 实现 model.services.ports 里的 Protocol，反向注入（依赖倒置）。
view 只消费 model.services 的用例产出（TurnResult 等），不依赖 PipelineContext。

详见仓库根目录 ARCHITECTURE.md。
"""
