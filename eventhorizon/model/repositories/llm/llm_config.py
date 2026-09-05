"""model/repositories/llm/llm_config.py — 读取 llm_config.json：录入侧 AI 生成
用的连接信息（不参与对局，README 5.3 对局隔离）。

密钥不写死在提交到 git 的配置文件里，两条路任选：
  1. api_key 留空、用 api_key_env 指定的环境变量传密钥；
  2. 在 llm_config.local.json（.gitignore 已排除）里整份覆盖，装真实 api_key——
     本地开发图省事、不想每次开终端都设环境变量时用这个。
两个都没有就是"未配置"，调用方（LlmLocationAuthor 的构造处）据此决定要不要接线
真实客户端。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "llm_config.json"
LOCAL_OVERRIDE_PATH = Path(__file__).resolve().parents[3] / "llm_config.local.json"


@dataclass(frozen=True)
class LlmConnectionConfig:
    provider: str = ""
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout_seconds: float = 30.0
    embedding_model: str = ""
    # 文本向量化用的模型名（跟 chat completions 的 model 不是同一个，比如智谱是
    # "embedding-3"）——只有事件"触发条件"改用向量相似度判定这一个用途在用
    # （model/services/matching.py），其它 AI 生成功能不需要。

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    @property
    def embedding_configured(self) -> bool:
        return bool(self.base_url and self.embedding_model and self.api_key)


def load_llm_config(path: Path | None = None) -> LlmConnectionConfig:
    """path 为 None 时按优先级找配置文件：EVENTHORIZON_LLM_CONFIG_PATH 环境变量 >
    llm_config.local.json（本地覆盖，.gitignore 已排除，存在就整份用它，不跟
    llm_config.json 合并）> 仓库自带的 eventhorizon/llm_config.json。文件不存在或
    解析失败都返回"未配置"的空配置，不抛异常——录入侧 AI 生成本来就该是可选功能，
    配置缺失不该让整个 Web 服务起不来。
    """
    if path is None:
        env_path = os.environ.get("EVENTHORIZON_LLM_CONFIG_PATH")
        if env_path:
            path = Path(env_path)
        elif LOCAL_OVERRIDE_PATH.exists():
            path = LOCAL_OVERRIDE_PATH
        else:
            path = DEFAULT_CONFIG_PATH
    if not path.exists():
        return LlmConnectionConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return LlmConnectionConfig()

    api_key = str(data.get("api_key") or "").strip()
    if not api_key:
        api_key_env = str(data.get("api_key_env") or "").strip()
        if api_key_env:
            api_key = os.environ.get(api_key_env, "")

    return LlmConnectionConfig(
        provider=str(data.get("provider") or ""),
        base_url=str(data.get("base_url") or ""),
        model=str(data.get("model") or ""),
        api_key=api_key,
        timeout_seconds=float(data.get("timeout_seconds") or 30.0),
        embedding_model=str(data.get("embedding_model") or ""),
    )
