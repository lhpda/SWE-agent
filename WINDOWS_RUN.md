# Windows 运行说明

本项目是命令行工具，没有网页服务。当前默认沙箱面向 Python/pytest 项目。

## 1. 环境

启动 Docker Desktop，等待 `docker version` 能显示 Server。

首次安装（在项目目录执行）：

```powershell
poetry env use E:\pyt\python.exe
poetry install
docker build -f Dockerfile.sandbox -t swe-agent-sandbox:local .
```

`E:\pyt\python.exe` 是本机 Python 路径；其他机器请替换为实际路径。

## 2. 模型配置

将 `.env.example` 复制为 `.env`，填写有效的服务密钥，例如：

```dotenv
DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY
SWE_AGENT_LLM_PROVIDER=deepseek
SWE_AGENT_LLM_MODEL=deepseek-chat
```

也支持 `openai` 和 `anthropic`，分别使用 `OPENAI_API_KEY` 和 `ANTHROPIC_API_KEY`，并指定对应模型。
`.env` 已加入 Git 忽略。`run.ps1` 会读取该文件；直接使用 `poetry run` 时需要自行设置进程环境变量。
不要将密钥写入文档、Issue JSON 或提交到仓库。克隆本项目后需要自行创建 `.env` 并填写有效密钥；仓库仅提供占位模板。

## 3. 运行示例

```powershell
cd 'D:\SWE agent'
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 --help
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 run examples/average-issue.json --timeout 180 --output .swe-agent/demo-output
```

示例仓库包含空列表平均值错误和 3 个测试。成功后补丁位于 `.swe-agent/demo-output/final_patch.diff`。
系统复制目标仓库到会话工作目录，在副本内验证补丁，最后清理容器；不会自动修改目标仓库。
运行需要调用远程模型服务。401/403 表示密钥无效或无访问权限，不能通过安装依赖解决。

自己的 Issue 文件需包含 `repo_path`、`title`、`body`，可在 `code_context.files` 提供仓库内相对文件路径。
`repo_path` 相对于执行命令的工作目录；`run.ps1` 固定在本项目目录执行，也可填写绝对路径。
项目必须具备可运行的测试；没有测试、命令失败、超时或仍有失败用例，不会判定修复成功。

## 4. 会话查询与恢复

```powershell
.\run.ps1 list
.\run.ps1 status <session-id>
.\run.ps1 resume <session-id>
```

恢复时复用已保存的定位结果，重建隔离环境并重新复现和验证；已完成的会话直接返回保存结果。
修复前产生、未保存完整 Issue/仓库上下文的旧会话不能恢复，需要重新 `run`。
默认会话资料在 `.swe-agent/sessions/<session-id>`，包含各阶段 JSON。

## 5. 验证

```powershell
poetry run pytest tests/test_runtime_regressions.py --no-cov -q
poetry run pytest tests/test_docker_pipeline_integration.py --no-cov -q
poetry run pytest tests --no-cov -q
```

Docker 集成测试使用真实容器和真实 pytest，只替换远程模型响应，因此无需密钥。
它验证完整内部流程，但不代表远程模型鉴权或生成能力验证通过。
全量测试含容器、网络和快照测试，可能需要数分钟。

沙箱默认禁止外网；依赖安装期间临时开放出站网络，安装结束关闭。
较复杂项目可能需要自定义预装依赖的镜像，通过 `SWE_AGENT_DOCKER_IMAGE` 指定。
