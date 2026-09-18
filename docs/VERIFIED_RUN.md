# 本地运行验证记录

验证日期：2026-09-18。项目目录：`D:\SWE agent`。

## 真实模型与 Docker 验证

- 模型服务：DeepSeek，模型：`deepseek-chat`。使用用户新增的本地配置，密钥不记录在报告中。
- 沙箱镜像：`swe-agent-sandbox:local`，Python 3.12，pytest 8.3.5。
- 会话：`6d9dad22-096c-4749-8181-ca76402ebb28`。
- 输入：`examples/average-issue.json`。
- 修复前：`test_empty_list` 因除零失败，另外 2 个测试通过。
- 模型生成补丁：空列表返回 0，保留普通平均值计算。
- 修复后：3 passed，0 failed，未产生新失败。
- 导出：`.swe-agent/demo-output/final_patch.diff`，已通过 `git apply --check`。
- 原始示例仓库没有被修改，容器和会话网络已清理。
- `list`、`status` 和已完成会话的 `resume` 已验证。

## 修复范围

- Poetry 绑定到本机可用 Python，修复包内错误的 `src.swe_agent` 导入。
- CLI 读取环境配置并传递到补丁生成器；模型客户端延迟初始化，无密钥也能运行离线工具及测试。
- Issue 正文解析与显式代码文件提示合并，补全无打包配置的简单 Python 项目检测。
- 创建实际 Docker 容器，在仓库副本验证；默认隔离外网，依赖安装期间临时开放连接。
- 接通生成器、语法校验、验证器的补丁数据格式；导出使用 LF，避免 Windows 下补丁不可应用。
- 未执行测试、超时、命令失败或测试仍失败时，不再返回修复成功。
- 保存完整会话上下文和阶段结果；修复查询与恢复接口。
- 修复 Windows/容器文件复制、命令超时、快照遗漏挂载目录和 tmpfs 内容的问题。
- 将明文示例密钥移出文档，加入本地 `.env`、`agent.env` 忽略规则。

## 自动化与构建

- 新增离线回归测试和真实 Docker 集成测试；集成测试仅替换远程模型响应。
- Python 源码编译检查及 Poetry wheel/sdist 构建通过。
- 最终全量测试：`893 passed, 205 warnings in 447.97s`，无失败、无跳过。告警主要为旧 datetime API 和 pytest 收集提示。
- 启动命令：`powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 run examples/average-issue.json --output .swe-agent/demo-output`。

## 清理后复验（2026-09-18）

- 删除本地 13 个过时说明、重复 Issue 示例及临时脚本；保留正式源码、测试、配置和 `examples/average`。
- 模型文档统一引用 `examples/average-issue.json`，补充 Ruff 缓存忽略规则。
- 全量测试再次通过：`893 passed, 205 warnings in 448.51s`。
- `run.ps1 --help`、Poetry wheel/sdist 构建通过；待提交文件及构建包未发现本地密钥或私有环境文件。
- 真实 DeepSeek + Docker 流程再次成功，会话 `6ce3be40-063d-41bd-97c1-ec9e4f5262b5`；生成空列表返回 0 的补丁，`git apply --check` 通过，容器已清理。

## 已知边界

这次验证证明 Python 示例修复流程可用，不代表任意 Issue 都能自动修好。
默认镜像面向 Python/pytest；复杂依赖或其他语言需配置相应镜像。
恢复会话时重新创建执行环境，重新复现与验证；修复前缺少完整元数据的旧会话需重新运行。
全局超时在阶段之间检查，模型单次请求另有超时；不是整个任务的硬实时终止保证。

项目的静态质量门禁仍未全部通过：本次 `ruff check src tests` 报 145 项，`mypy src` 报 146 项（31 个文件），主要包括未使用导入/变量和类型标注问题。它们与运行测试分别报告，本次不宣称生产发布或 CI 全绿。
