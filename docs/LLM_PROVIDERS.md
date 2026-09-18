# 多 LLM 提供商支持

SWE Agent 现在支持多个 LLM 提供商，包括 Anthropic Claude、DeepSeek 和 OpenAI。

## 支持的提供商

| 提供商 | 模型示例 | API Key 环境变量 |
|--------|----------|-----------------|
| Anthropic | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| DeepSeek | `deepseek-chat`, `deepseek-coder` | `DEEPSEEK_API_KEY` |
| OpenAI | `gpt-4`, `gpt-4-turbo` | `OPENAI_API_KEY` |

## 配置方法

### 使用 DeepSeek

```bash
# 设置 DeepSeek API Key
export DEEPSEEK_API_KEY="your-deepseek-api-key"

# 配置使用 DeepSeek
export SWE_AGENT_LLM_PROVIDER="deepseek"
export SWE_AGENT_LLM_MODEL="deepseek-chat"

# 运行项目
poetry run python -m swe_agent.cli run examples/average-issue.json --verbose
```

### 使用 OpenAI

```bash
# 设置 OpenAI API Key
export OPENAI_API_KEY="your-openai-api-key"

# 配置使用 OpenAI
export SWE_AGENT_LLM_PROVIDER="openai"
export SWE_AGENT_LLM_MODEL="gpt-4"

# 运行项目
poetry run python -m swe_agent.cli run examples/average-issue.json --verbose
```

### 使用 Anthropic Claude（默认）

```bash
# 设置 Anthropic API Key
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# 使用默认配置（或显式指定）
export SWE_AGENT_LLM_PROVIDER="anthropic"
export SWE_AGENT_LLM_MODEL="claude-sonnet-4-20250514"

# 运行项目
poetry run python -m swe_agent.cli run examples/average-issue.json --verbose
```

## 配置文件方式

创建 `swe-agent.toml` 文件：

```toml
[swe_agent]
# DeepSeek 配置示例
llm_provider = "deepseek"
llm_model = "deepseek-chat"
llm_max_tokens = 4096
llm_temperature = 0.0

# 其他配置...
localization_timeout = 300
reproduction_timeout = 480
```

使用配置文件运行：
```bash
export DEEPSEEK_API_KEY="your-api-key"
poetry run python -m swe_agent.cli run examples/average-issue.json --config swe-agent.toml
```

## DeepSeek 推荐模型

- **deepseek-chat**: 通用对话模型，适合大多数场景
- **deepseek-coder**: 专门优化的代码生成模型（推荐用于 SWE Agent）

## 安装依赖

DeepSeek 和 OpenAI 使用 OpenAI SDK：

```bash
# 如果使用 DeepSeek 或 OpenAI
poetry add openai
```

Anthropic 使用专用 SDK（已在 pyproject.toml 中）：
```bash
poetry install  # anthropic 已包含
```

## 程序化使用

```python
from swe_agent.llm import LLMClient

# 使用 DeepSeek
client = LLMClient(
    provider="deepseek",
    model="deepseek-chat",
    api_key="your-api-key"  # 或从环境变量读取
)

# 生成单个补丁
result = client.generate(
    prompt="Fix this bug: ...",
    max_tokens=4096,
    temperature=0.0
)

# 生成多个候选
candidates = client.generate_multiple(
    prompt="Generate multiple fixes: ...",
    n=3,
    temperature=0.7
)
```

## 成本对比

| 提供商 | 模型 | 输入价格 (per 1M tokens) | 输出价格 (per 1M tokens) |
|--------|------|--------------------------|-------------------------|
| DeepSeek | deepseek-chat | $0.27 | $1.10 |
| DeepSeek | deepseek-coder | $0.27 | $1.10 |
| Anthropic | claude-sonnet-4 | $3.00 | $15.00 |
| OpenAI | gpt-4 | $30.00 | $60.00 |

**DeepSeek 具有显著的成本优势**，特别适合大规模使用。

## 性能建议

- **代码生成任务**: 推荐 `deepseek-coder` 或 `claude-sonnet-4`
- **成本敏感场景**: 推荐 `deepseek-chat`
- **最高质量要求**: 推荐 `claude-sonnet-4` 或 `gpt-4`

## 故障排除

### DeepSeek API 连接问题

```bash
# 测试连接
curl https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### API Key 未设置

```bash
# 检查环境变量
echo $DEEPSEEK_API_KEY

# 如果为空，设置它
export DEEPSEEK_API_KEY="your-key-here"
```
