"""配置加载与校验"""
import json
from pathlib import Path

CONFIG_FILE = Path("config.json")
_CONFIG: dict = {}


def load_config() -> dict:
    global _CONFIG
    if _CONFIG:
        return _CONFIG

    if not CONFIG_FILE.exists():
        raise RuntimeError(f"配置文件不存在：{CONFIG_FILE}，请参考文档创建")

    try:
        _CONFIG = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"config.json 格式错误：{e}")

    provider = _CONFIG.get("provider", "")
    if provider == "ollama":
        ollama = _CONFIG.get("ollama", {})
        if not ollama.get("url") or not ollama.get("model"):
            raise RuntimeError("provider=ollama 时，ollama.url 和 ollama.model 不能为空")
    elif provider == "deepseek":
        deepseek = _CONFIG.get("deepseek", {})
        if not deepseek.get("api_key"):
            raise RuntimeError("provider=deepseek 时，deepseek.api_key 不能为空")
        if not deepseek.get("model"):
            raise RuntimeError("provider=deepseek 时，deepseek.model 不能为空")
    else:
        raise RuntimeError(f"provider 只能是 ollama 或 deepseek，当前值：{provider}")

    return _CONFIG


def get_provider() -> str:
    return load_config()["provider"]


def get_ollama_config() -> dict:
    return load_config().get("ollama", {})


def get_deepseek_config() -> dict:
    return load_config().get("deepseek", {})


def get_srs_config() -> dict:
    return load_config().get("srs", {"daily_new_limit": 20})