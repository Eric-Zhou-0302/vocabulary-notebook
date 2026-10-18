"""配置加载与校验"""
import json
import copy
import os
import tempfile
import threading
from pathlib import Path

CONFIG_FILE = Path("config.json")
_CONFIG: dict = {}
_CONFIG_LOCK = threading.RLock()


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
    """返回间隔复习配置，并为旧版 config.json 提供安全默认值。"""
    srs = load_config().get("srs", {})
    daily_new_limit = srs.get("daily_new_limit", 20)
    if not isinstance(daily_new_limit, int) or isinstance(daily_new_limit, bool):
        raise RuntimeError("srs.daily_new_limit 必须是整数")
    if not 0 <= daily_new_limit <= 100:
        raise RuntimeError("srs.daily_new_limit 必须在 0 到 100 之间")
    return {"daily_new_limit": daily_new_limit}


def public_config() -> dict:
    data = copy.deepcopy(load_config())
    ds = data.setdefault("deepseek", {})
    ds["api_key_configured"] = bool(ds.pop("api_key", ""))
    return {key: data.get(key, {}) for key in ("provider", "ollama", "deepseek")}


def save_model_config(provider, ollama, deepseek) -> dict:
    """原子落盘成功后才替换内存配置，保留其他业务设置。"""
    global _CONFIG
    with _CONFIG_LOCK:
        data = copy.deepcopy(load_config())
        ds = {**data.get("deepseek", {}), **deepseek}
        if not deepseek.get("api_key"):
            ds["api_key"] = data.get("deepseek", {}).get("api_key", "")
        if provider == "deepseek" and (not ds.get("api_key") or not ds.get("model")):
            raise ValueError("请填写 DeepSeek API Key 并选择模型")
        if provider == "ollama" and (not ollama.get("url") or not ollama.get("model")):
            raise ValueError("请填写 Ollama 地址和模型名称")
        data.update(provider=provider, ollama=ollama, deepseek=ds)
        fd, name = tempfile.mkstemp(dir=CONFIG_FILE.resolve().parent, prefix=".config-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(name, CONFIG_FILE)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        _CONFIG = data
        return public_config()
