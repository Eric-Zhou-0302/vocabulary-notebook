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


def _section(data: dict, name: str) -> dict:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} 必须是 JSON 对象")
    return value


def _validate_model_config(data: dict) -> None:
    if not isinstance(data, dict):
        raise RuntimeError("config.json 顶层必须是 JSON 对象")
    for name in ("ollama", "deepseek", "srs", "sync"):
        _section(data, name)
    provider = data.get("provider", "")
    if provider == "ollama":
        ollama = _section(data, "ollama")
        if any(not isinstance(ollama.get(key), str) or not ollama[key].strip() for key in ("url", "model")):
            raise RuntimeError("provider=ollama 时，ollama.url 和 ollama.model 不能为空")
    elif provider == "deepseek":
        deepseek = _section(data, "deepseek")
        if not isinstance(deepseek.get("api_key"), str) or not deepseek["api_key"].strip():
            raise RuntimeError("provider=deepseek 时，deepseek.api_key 不能为空")
        if not isinstance(deepseek.get("model"), str) or not deepseek["model"].strip():
            raise RuntimeError("provider=deepseek 时，deepseek.model 不能为空")
    else:
        raise RuntimeError(f"provider 只能是 ollama 或 deepseek，当前值：{provider}")


def load_config() -> dict:
    global _CONFIG
    with _CONFIG_LOCK:
        if _CONFIG:
            return _CONFIG
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(f"配置文件不存在：{CONFIG_FILE}，请参考文档创建") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"config.json 格式错误：{exc}") from exc
        # 校验通过后才发布缓存；失败后修正文件可直接重试。
        _validate_model_config(data)
        _CONFIG = data
        return _CONFIG


def get_provider() -> str:
    return load_config()["provider"]


def get_ollama_config() -> dict:
    return load_config().get("ollama", {})


def get_deepseek_config() -> dict:
    return load_config().get("deepseek", {})


def get_srs_config() -> dict:
    """返回间隔复习配置，并为旧版 config.json 提供安全默认值。"""
    srs = _section(load_config(), "srs")
    daily_new_limit = srs.get("daily_new_limit", 20)
    if not isinstance(daily_new_limit, int) or isinstance(daily_new_limit, bool):
        raise RuntimeError("srs.daily_new_limit 必须是整数")
    if not 0 <= daily_new_limit <= 100:
        raise RuntimeError("srs.daily_new_limit 必须在 0 到 100 之间")
    return {"daily_new_limit": daily_new_limit}


def get_sync_config() -> dict:
    sync = _section(load_config(), "sync")
    interval = sync.get("interval_seconds", 30)
    if type(interval) is not int or not 10 <= interval <= 3600:
        raise RuntimeError("sync.interval_seconds 必须是 10 到 3600 之间的整数")
    return {"interval_seconds": interval,
            "credentials_dir": sync.get("credentials_dir", ".secrets")}


def public_config() -> dict:
    data = copy.deepcopy(load_config())
    ds = data.setdefault("deepseek", {})
    ds["api_key_configured"] = bool(ds.pop("api_key", ""))
    return {key: data.get(key, {}) for key in ("provider", "ollama", "deepseek")}


def save_model_config(provider, ollama, deepseek) -> dict:
    """原子落盘成功后才替换内存配置，保留其他业务设置。"""
    global _CONFIG
    with _CONFIG_LOCK:
        if provider not in ("ollama", "deepseek"):
            raise ValueError("provider 只能是 ollama 或 deepseek")
        if not isinstance(ollama, dict) or not isinstance(deepseek, dict):
            raise ValueError("模型配置必须是 JSON 对象")
        data = copy.deepcopy(load_config())
        ds = {**data.get("deepseek", {}), **deepseek}
        if not deepseek.get("api_key"):
            ds["api_key"] = data.get("deepseek", {}).get("api_key", "")
        if provider == "deepseek" and (not ds.get("api_key") or not ds.get("model")):
            raise ValueError("请填写 DeepSeek API Key 并选择模型")
        if provider == "ollama" and (not ollama.get("url") or not ollama.get("model")):
            raise ValueError("请填写 Ollama 地址和模型名称")
        data.update(provider=provider, ollama=ollama, deepseek=ds)
        try:
            _validate_model_config(data)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
        fd, name = tempfile.mkstemp(dir=CONFIG_FILE.resolve().parent, prefix=".config-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, CONFIG_FILE)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        _CONFIG = data
        return public_config()
