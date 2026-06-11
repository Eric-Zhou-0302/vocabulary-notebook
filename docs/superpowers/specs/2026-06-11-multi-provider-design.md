# 多 Provider 支持设计（Ollama / DeepSeek）

## 概述

通过 `config.json` 支持在 Ollama 和 DeepSeek 之间切换，用于单词音标、释义、例句的补全。

## 配置

**文件：** `config.json`（项目根目录）

```json
{
  "provider": "ollama",
  "ollama": {
    "url": "http://localhost:11434/api/generate",
    "model": "gemma4:26b"
  },
  "deepseek": {
    "api_key": "",
    "model": ""
  }
}
```

**启动校验规则：**
- `provider == "deepseek"` 且 `deepseek.api_key` 或 `deepseek.model` 为空 → 抛异常退出
- `provider == "ollama"` 时，Ollama 配置缺失也抛异常；DeepSeek 配置不校验

## 代码改动

### 1. 配置加载

新建 `config.py`，解析 `config.json`，启动时校验并抛出明确错误。

### 2. `enrich_word` 函数分支

现有 `enrich_word`（`app.py` 第 109-144 行）扩展为：

```python
async def enrich_word(word: str) -> tuple[str, str, str]:
    if config["provider"] == "ollama":
        # 现有逻辑：POST http://localhost:11434/api/generate
        # prompt 格式不变
    elif config["provider"] == "deepseek":
        # POST https://api.deepseek.com/chat/completions
        # body: {"model": config["deepseek"]["model"],
        #        "messages": [{"role": "user", "content": prompt}],
        #        "stream": false}
        # 从 response["choices"][0]["message"]["content"] 解析 JSON
```

DeepSeek prompt 格式与 Ollama 一致，复用现有 prompt 模板。

### 3. 错误处理

两套 provider 共用同一错误处理——请求失败（超时、API 报错等）返回空字符串，不阻断其他单词补全。后端记日志含 provider 名称方便排查。

## 健康检查

`/api/health` 端点检测当前 provider 的可达性：
- Ollama：`GET http://localhost:11434/api/tags`
- DeepSeek：`GET https://api.deepseek.com/chat/completions`（发一个 minimal 请求测连通性）

## 不变更

- `frontend/` 前端代码不变
- `words.json` 数据格式不变
- API 路由不变
- 串行 enrichment 逻辑不变