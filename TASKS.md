# SWE Agent 开发任务清单

**基于**: SYSTEM_DESIGN.md v1.0  
**更新日期**: 2026-09-16

---

## Phase 0: 项目基础设施搭建

### Task 0.1: 项目脚手架与依赖管理
**文件**: `pyproject.toml`, `README.md`, `.gitignore`

- [x] 初始化 Python 3.11+ 项目（使用 poetry）
- [x] 配置核心依赖：anthropic, docker, pydantic, gitpython, structlog
- [x] 配置开发依赖：pytest, pytest-docker, black, ruff, mypy
- [x] 创建基础目录结构：`src/`, `tests/`, `docs/`

**验收标准**:
- `poetry install` 成功安装所有依赖
- `poetry run python --version` 显示 Python 3.11+
- 目录结构符合 Python 包规范

---

### Task 0.2: 核心数据结构定义
**文件**: `src/swe_agent/types.py`

- [x] 实现所有 Pydantic 模型（第 4 章定义的 9 个核心类型）
- [x] IssueContext, RepositoryContext
- [x] LocalizationResult, ReproductionResult, PatchResult, ValidationResult
- [x] PipelineState, StageStatus, ErrorInfo
- [x] ToolCall, ToolResult, PipelineResult

**验收标准**:
- 所有模型通过 Pydantic 验证
- `mypy src/swe_agent/types.py` 无类型错误
- 单元测试覆盖所有字段的序列化/反序列化

---

### Task 0.3: 配置管理与日志系统
**文件**: `src/swe_agent/config.py`, `src/swe_agent/logging.py`

- [x] 实现结构化日志（使用 structlog）
- [x] 定义全局配置类（超时、重试、资源限制等）
- [x] 实现配置加载（环境变量 + 配置文件）

**验收标准**:
- 日志输出为 JSON Lines 格式
- 配置可通过环境变量覆盖默认值
- 测试验证日志包含必需字段（timestamp, level, session_id）

---

### Task 0.4: 状态存储层实现
**文件**: `src/swe_agent/storage.py`, `tests/test_storage.py`

- [x] 实现 StateStore 类
- [x] 实现 `save_stage_result()`, `load_stage_result()`, `append_log()`
- [x] 创建 `.swe-agent/sessions/{session_id}/` 目录结构
- [x] 实现 FIFO 清理策略（最多保留 100 个 session）

**验收标准**:
- 单元测试验证所有 CRUD 操作
- 测试验证磁盘配额限制（单个 session < 1GB）
- 测试验证 FIFO 清理逻辑
- 测试验证并发写入的线程安全性

---

## Phase 1: 工具层实现（Tool Layer）

### Task 1.1: 工具基础接口与注册机制
**文件**: `src/swe_agent/tools/base.py`, `src/swe_agent/tools/registry.py`

- [x] 定义 Tool 抽象基类
- [x] 实现参数验证（基于 JSON Schema）
- [x] 实现工具注册表（动态发现和注册工具）
- [x] 实现输出截断机制（10KB 限制）

**验收标准**:
- 测试验证参数验证逻辑（有效/无效输入）
- 测试验证输出截断（超过 10KB 时正确标记）
- 测试验证工具注册与发现

---

### Task 1.2: 搜索工具实现
**文件**: `src/swe_agent/tools/search.py`, `tests/test_tools_search.py`

- [x] 实现 `ripgrep_search` 工具
- [x] 实现 `symbol_search` 工具（基于 ctags）
- [x] 实现 `ast_query` 工具（基于 tree-sitter）
- [x] 实现搜索结果排序与截断（最多 100 条）

**验收标准**:
- 测试在示例仓库中搜索已知模式，验证返回正确文件和行号
- 测试验证符号搜索（函数/类名）
- 测试验证 AST 查询（查找特定语法结构）
- 测试验证超过 100 条结果时正确截断

---

### Task 1.3: 文件操作工具实现
**文件**: `src/swe_agent/tools/file_ops.py`, `tests/test_tools_file.py`

- [x] 实现 `read_file` 工具（支持 line_range）
- [x] 实现 `read_file_with_context` 工具（focus_lines + context_lines）
- [x] 实现 `apply_patch` 工具（Git apply）
- [x] 实现 `apply_patch_dry_run` 工具

**验收标准**:
- 测试验证读取文件的行范围功能
- 测试验证 context 读取（focus + 前后各 50 行）
- 测试验证 patch 应用（干净应用 + 冲突检测）
- 测试验证文件内容截断（最多 50,000 字符）

---

### Task 1.4: 代码分析工具实现
**文件**: `src/swe_agent/tools/analysis.py`, `tests/test_tools_analysis.py`

- [x] 实现 `syntax_check` 工具（支持 Python/JS/Java/Rust）
- [x] 实现 `parse_ast` 工具（tree-sitter）
- [x] 实现 `get_imports` 工具（提取依赖关系）
- [x] 实现 `detect_project_type` 工具

**验收标准**:
- 测试验证语法检查（有效/无效代码）
- 测试验证 AST 解析返回正确结构
- 测试验证导入提取（Python, JS, Java）
- 测试验证项目类型检测（基于 package.json, requirements.txt 等）

---

## Phase 2: 沙箱层实现（Sandbox Layer）

### Task 2.1: Docker 容器管理器
**文件**: `src/swe_agent/sandbox/docker.py`, `tests/test_sandbox_docker.py`

- [x] 实现 DockerSandbox 类
- [x] 实现 `create()`, `destroy()`, `execute()`, `copy_file()`
- [x] 实现资源限制（CPU 2 核、内存 4GB、磁盘 10GB）
- [x] 实现容器生命周期管理（最长 2 小时自动销毁）

**验收标准**:
- 测试验证容器创建与销毁
- 测试验证资源限制生效（尝试超过限制时被拒绝）
- 测试验证容器隔离（无法访问宿主机网络）
- 测试验证 orphan 容器自动清理

---

### Task 2.2: 网络隔离与白名单
**文件**: `src/swe_agent/sandbox/network.py`, `tests/test_sandbox_network.py`

- [x] 实现 Docker 自定义网络配置
- [x] 实现域名白名单（pypi.org, npmjs.com, maven.org 等）
- [x] 实现网络访问日志记录
- [x] 实现网络超时配置

**验收标准**:
- 测试验证白名单内域名可访问
- 测试验证白名单外域名被阻止
- 测试验证网络日志记录所有请求
- 测试验证网络超时机制

---

### Task 2.3: 沙箱执行工具
**文件**: `src/swe_agent/tools/sandbox_exec.py`, `tests/test_tools_sandbox.py`

- [x] 实现 `run_command` 工具（在沙箱内执行命令）
- [x] 实现 `run_test` 工具（自动检测测试框架）
- [x] 实现 `install_deps` 工具（pip/npm/maven）
- [x] 实现输出截断（测试日志最多 5KB）

**验收标准**:
- 测试验证简单命令执行（echo, ls）
- 测试验证超时机制（sleep 命令）
- 测试验证测试框架自动检测（pytest, jest, junit）
- 测试验证依赖安装（创建临时项目并安装依赖）

---

### Task 2.4: 快照与回滚机制
**文件**: `src/swe_agent/sandbox/snapshot.py`, `tests/test_sandbox_snapshot.py`

- [x] 实现容器快照创建
- [x] 实现快照恢复
- [x] 实现 Git stash 备份（宿主机文件系统）
- [x] 实现自动回滚触发器

**验收标准**:
- 测试验证快照创建与恢复
- 测试验证文件修改后回滚到快照状态
- 测试验证 Git stash 备份与恢复
- 测试验证快照存储空间限制

---

## Phase 3: Agent 层实现 - LocalizationAgent

### Task 3.1: Issue 解析器
**文件**: `src/swe_agent/agents/localization/parser.py`, `tests/test_issue_parser.py`

- [x] 实现 Issue Markdown 解析
- [x] 提取错误信息（error messages）
- [x] 提取堆栈追踪（stack traces）
- [x] 提取复现步骤（reproduction steps）

**验收标准**:
- 测试验证解析包含堆栈追踪的 Issue
- 测试验证解析模糊描述的 Issue
- 测试验证提取多个错误信息
- 测试验证解析失败时返回清晰错误

---

### Task 3.2: 代码搜索策略
**文件**: `src/swe_agent/agents/localization/strategy.py`, `tests/test_localization_strategy.py`

- [x] 实现基于堆栈追踪的搜索策略
- [x] 实现基于错误信息的关键词搜索
- [x] 实现基于符号名的精确定位
- [x] 实现搜索结果置信度评分

**验收标准**:
- 测试验证堆栈追踪匹配正确文件
- 测试验证关键词搜索排序（相关性）
- 测试验证符号搜索定位到具体函数
- 测试验证置信度评分合理（Top-3 总和 > 0.6）

---

### Task 3.3: LocalizationAgent 实现
**文件**: `src/swe_agent/agents/localization/agent.py`, `tests/test_localization_agent.py`

- [x] 实现 LocalizationAgent 类
- [x] 集成 LLM API（Claude）
- [x] 实现工具调用编排
- [x] 实现结果聚合与排序

**验收标准**:
- Mock LLM 测试验证工具调用序列
- 测试验证返回 LocalizationResult 格式正确
- 测试验证至少返回 1 个候选文件
- 测试验证执行时间 < 5 分钟

---

### Task 3.4: LocalizationAgent 集成测试
**文件**: `tests/integration/test_localization_e2e.py`

- [ ] 准备 3 个测试用例（简单/中等/复杂）
- [ ] 使用真实仓库和 Issue
- [ ] 验证定位准确率
- [ ] 性能基准测试

**验收标准**:
- 简单 Bug 定位准确率 > 90%
- 中等复杂度定位准确率 > 70%
- 平均执行时间 < 3 分钟
- 工具调用次数 < 20 次

---

## Phase 4: Agent 层实现 - ReproductionAgent

### Task 4.1: 项目类型与测试框架检测
**文件**: `src/swe_agent/agents/reproduction/detector.py`, `tests/test_detector.py`

- [x] 实现项目类型检测（Python/Node.js/Java/Rust）
- [x] 实现测试框架检测（pytest/jest/junit/cargo test）
- [x] 实现测试命令推断
- [x] 实现依赖安装检测

**验收标准**:
- 测试验证 Python 项目检测（requirements.txt/pyproject.toml）
- 测试验证 Node.js 项目检测（package.json）
- 测试验证测试框架自动发现
- 测试验证生成正确的测试命令

---

### Task 4.2: 错误日志分析器
**文件**: `src/swe_agent/agents/reproduction/log_analyzer.py`, `tests/test_log_analyzer.py`

- [x] 实现堆栈追踪解析
- [x] 实现错误类型识别（Exception, AssertionError 等）
- [x] 实现根因位置提取（文件 + 行号）
- [x] 实现日志截断（最后 200 行）

**验收标准**:
- 测试验证 Python 堆栈追踪解析
- 测试验证 JavaScript 错误堆栈解析
- 测试验证提取正确的文件和行号
- 测试验证日志截断逻辑

---

### Task 4.3: ReproductionAgent 实现
**文件**: `src/swe_agent/agents/reproduction/agent.py`, `tests/test_reproduction_agent.py`

- [x] 实现 ReproductionAgent 类
- [x] 集成沙箱执行
- [x] 实现测试运行与结果解析
- [x] 实现多次重试策略（最多 5 次）

**验收标准**:
- Mock 测试验证沙箱调用
- 测试验证成功复现错误
- 测试验证未复现时触发回退
- 测试验证执行时间 < 8 分钟

---

### Task 4.4: ReproductionAgent 集成测试
**文件**: `tests/integration/test_reproduction_e2e.py`

- [ ] 准备已知 Bug 的测试项目
- [ ] 验证错误复现成功率
- [ ] 验证根因定位准确性
- [ ] 性能基准测试

**验收标准**:
- 明确 Bug 复现成功率 > 85%
- 根因定位准确率 > 80%
- 平均执行时间 < 5 分钟
- 测试日志正确截断到 5KB

---

## Phase 5: Agent 层实现 - PatchGeneratorAgent

### Task 5.0: 代码编辑引擎（额外）
**文件**: `src/swe_agent/agents/patch/edit_engine.py`, `tests/test_edit_engine.py`

- [x] 实现代码编辑操作（insert/replace/delete）
- [x] 实现语法验证（Python）
- [x] 实现 diff 生成
- [x] 实现回滚机制

---

### Task 5.1: 代码上下文构建器
**文件**: `src/swe_agent/agents/patch/context_builder.py`, `tests/test_context_builder.py`

- [x] 实现焦点行上下文提取（focus_lines + context 50 行）
- [x] 实现相关函数/类提取
- [x] 实现导入语句收集
- [x] 实现上下文大小限制（15K tokens）

**验收标准**:
- 测试验证提取正确的上下文行
- 测试验证相关符号提取
- 测试验证上下文不超过 15K tokens
- 测试验证关键信息优先保留

---

### Task 5.2: Patch 生成器
**文件**: `src/swe_agent/agents/patch/generator.py`, `tests/test_patch_generator.py`

- [x] 实现单一修复生成
- [x] 实现 Beam Search（生成多个候选）
- [x] 实现 diff 格式化（unified diff）
- [x] 实现 patch 大小限制（< 50 行）

**验收标准**:
- 测试验证生成有效的 unified diff
- 测试验证 Beam Search 生成多个不同候选
- 测试验证 patch 不超过 50 行
- 测试验证 diff 可被 git apply

---

### Task 5.3: 语法验证器
**文件**: `src/swe_agent/agents/patch/validator.py`, `tests/test_patch_validator.py`

- [x] 实现语法检查（调用 syntax_check 工具）
- [x] 实现 dry-run 应用检查
- [x] 实现 AST 完整性检查
- [x] 实现关键符号可访问性检查

**验收标准**:
- 测试验证有效 patch 通过所有检查
- 测试验证语法错误 patch 被拒绝
- 测试验证冲突 patch 被拒绝
- 测试验证检查失败时返回清晰错误信息

---

### Task 5.4: PatchGeneratorAgent 实现与集成测试
**文件**: `src/swe_agent/agents/patch/agent.py`, `tests/test_patch_agent.py`

- [x] 实现 PatchGeneratorAgent 类
- [x] 集成 ContextBuilder, PatchGenerator, SyntaxValidator
- [x] 实现补丁生成、验证与排序流程
- [x] 实现多候选补丁生成
- [ ] 集成上下文构建、生成、验证
- [ ] 实现多候选排序（按置信度）
- [ ] 端到端测试

**验收标准**:
- 测试验证生成的 patch 通过语法检查
- 测试验证 Beam Search 模式生成 3-5 个候选
- 测试验证候选按置信度排序
- 平均执行时间 < 6 分钟

---

## Phase 6: Agent 层实现 - ValidationAgent

### Task 6.0: 测试执行器（额外）
**文件**: `src/swe_agent/agents/verification/test_executor.py`, `tests/test_test_executor.py`

- [x] 实现沙箱中测试执行
- [x] 实现多框架测试输出解析（pytest/jest/junit）
- [x] 实现测试统计提取
- [x] 实现结果比较逻辑

---

### Task 6.1: Patch 应用器
**文件**: `src/swe_agent/agents/validation/applicator.py`, `tests/test_patch_applicator.py`

- [x] 实现 patch 应用到沙箱
- [x] 实现应用前快照创建
- [x] 实现应用失败回滚
- [x] 实现文件权限处理

**验收标准**:
- 测试验证 patch 成功应用到干净仓库
- 测试验证应用失败时自动回滚
- 测试验证快照状态正确恢复
- 测试验证文件权限保持一致

---

### Task 6.2: 测试套件运行器
**文件**: `src/swe_agent/agents/validation/test_runner.py`, `tests/test_test_runner.py`

- [x] 实现完整测试套件运行
- [x] 实现测试结果解析（passed/failed/skipped）
- [x] 实现测试输出截断（10KB）
- [x] 实现超时控制（600 秒）

**验收标准**:
- 测试验证运行 pytest 测试套件
- 测试验证运行 jest 测试套件
- 测试验证结果统计正确
- 测试验证超时后正确终止

---

### Task 6.3: 回归检测器
**文件**: `src/swe_agent/agents/validation/regression.py`, `tests/test_regression.py`

- [x] 实现测试结果对比（before/after）
- [x] 实现新增失败检测
- [x] 实现修复测试识别
- [x] 实现回归判定逻辑

**验收标准**:
- 测试验证识别新增的测试失败
- 测试验证识别被修复的测试
- 测试验证正确判定是否回归
- 测试验证边界情况（所有测试都通过/都失败）

---

### Task 6.4: ValidationAgent 实现与集成测试
**文件**: `src/swe_agent/agents/validation/agent.py`, `tests/test_validation_agent.py`

- [x] 实现 ValidationAgent 类
- [x] 集成应用、测试、回归检测
- [x] 实现验证报告生成
- [x] 端到端测试

**验收标准**:
- 测试验证有效 patch 通过验证
- 测试验证回归 patch 被拒绝
- 测试验证目标测试状态正确识别
- 平均执行时间 < 10 分钟

---

## Phase 7: Orchestrator 实现（状态调度层）

### Task 7.1: 状态机实现
**文件**: `src/swe_agent/orchestrator/state_machine.py`, `tests/test_state_machine.py`

- [x] 实现状态定义（IDLE/LOCALIZING/REPRODUCING/PATCHING/VALIDATING/DONE/FAILED）
- [x] 实现状态转换规则
- [x] 实现状态持久化（到 StateStore）
- [x] 实现状态恢复（断点续传）

**验收标准**:
- 测试验证所有状态转换路径
- 测试验证非法转换被拒绝
- 测试验证状态正确持久化
- 测试验证从任意阶段恢复

---

### Task 7.2: 重试与回退策略
**文件**: `src/swe_agent/orchestrator/retry.py`, `tests/test_retry.py`

- [x] 实现阶段重试逻辑（根据 2.2 容错矩阵）
- [x] 实现回退触发器
- [x] 实现死循环检测（滑动窗口）
- [x] 实现熔断机制

**验收标准**:
- 测试验证重试次数限制
- 测试验证回退逻辑正确触发
- 测试验证死循环检测（5 次窗口内 3 次重复）
- 测试验证连续失败熔断

---

### Task 7.3: 错误聚合与报告
**文件**: `src/swe_agent/orchestrator/error_handler.py`, `tests/test_error_handler.py`

- [x] 实现错误分类（可恢复/不可恢复）
- [x] 实现错误聚合
- [x] 实现错误报告生成
- [x] 实现错误上下文保留

**验收标准**:
- 测试验证错误正确分类
- 测试验证多个错误聚合为摘要
- 测试验证错误报告包含必要上下文
- 测试验证可恢复错误触发重试

---

### Task 7.4: PipelineOrchestrator 实现
**文件**: `src/swe_agent/orchestrator/pipeline.py`, `tests/test_pipeline.py`

- [x] 实现 PipelineOrchestrator 类
- [x] 实现 `run()`, `resume()`, `get_state()` 接口
- [x] 实现阶段协调与数据传递
- [x] 实现全局超时（30 分钟）

**验收标准**:
- [x] 测试验证 Happy Path（所有阶段成功）
- [x] 测试验证回退场景（Validation 失败 → Patch）
- [x] 测试验证重试场景（Localization 失败重试）
- [x] 测试验证全局超时终止

---

## Phase 8: 端到端集成与测试

### Task 8.1: CLI 接口实现
**文件**: `src/swe_agent/cli.py`, `tests/test_cli.py`

- [x] 实现命令行参数解析（issue_url, repo_path）
- [x] 实现进度显示（实时阶段状态）
- [x] 实现日志输出控制（--verbose, --quiet）
- [x] 实现 session 恢复（--resume SESSION_ID）

**验收标准**:
- 测试验证命令行参数解析
- 测试验证帮助信息显示
- 测试验证进度条正确更新
- 手动测试：`swe-agent --issue https://... --repo /path/to/repo`

---

### Task 8.2: E2E 测试数据集准备
**文件**: `tests/fixtures/`, `tests/e2e/test_e2e_simple.py`

- [x] 准备 3 个简单 Bug 测试用例
- [x] 准备 4 个中等复杂度测试用例
- [x] 准备 2 个复杂场景测试用例
- [x] 准备 1 个负面案例（应该失败）

**验收标准**:
- 所有测试仓库为 Git 子模块或固定 commit
- 所有 Issue JSON 存储在 `tests/fixtures/issues/`
- 每个测试用例包含预期 patch
- 测试用例覆盖多种编程语言

---

### Task 8.3: E2E 测试套件实现
**文件**: `tests/e2e/test_e2e_suite.py`

- [x] 实现 E2E 测试框架
- [x] 运行所有 10 个测试用例
- [x] 收集成功率和性能指标
- [x] 生成测试报告

**验收标准**:
- 简单 Bug 成功率 > 80%
- 中等复杂度成功率 > 60%
- 复杂场景至少 1 个成功
- 负面案例正确失败
- 生成 HTML 测试报告

---

### Task 8.4: 性能优化与压力测试
**文件**: `tests/performance/test_performance.py`

- [x] 实现性能基准测试
- [x] 实现并发 session 测试（5 个并发）
- [x] 实现内存泄漏检测
- [x] 实现资源清理验证

**验收标准**:
- 简单 Bug 平均时间 < 5 分钟
- 中等复杂度平均时间 < 15 分钟
- 5 个并发 session 无相互干扰
- 测试结束后无 orphan 容器
- 内存增长 < 500MB per session

---

## Phase 9: 文档与部署

### Task 9.1: 用户文档编写
**文件**: `docs/USER_GUIDE.md`, `docs/EXAMPLES.md`

- [x] 编写安装指南
- [x] 编写快速开始教程
- [x] 编写配置说明
- [x] 编写故障排查指南

**验收标准**:
- 新用户按文档 10 分钟内完成安装
- 示例代码可直接运行
- 配置项有清晰说明
- 常见错误有解决方案

---

### Task 9.2: 开发者文档编写
**文件**: `docs/DEVELOPER.md`, `docs/CONTRIBUTING.md`

- [x] 编写架构概览
- [x] 编写添加新工具的指南
- [x] 编写添加新语言支持的指南
- [x] 编写贡献者指南

**验收标准**:
- 新开发者能理解系统架构
- 添加新工具的步骤清晰
- 添加新语言的步骤清晰
- 贡献流程明确

---

### Task 9.3: CI/CD 配置
**文件**: `.github/workflows/test.yml`, `.github/workflows/release.yml`

- [x] 配置单元测试 CI
- [x] 配置集成测试 CI
- [x] 配置代码质量检查（black, ruff, mypy）
- [x] 配置自动发布流程

**验收标准**:
- 每次 push 自动运行单元测试
- PR 需要通过所有检查
- 代码覆盖率报告自动生成
- Tag 推送自动发布到 PyPI

---

### Task 9.4: Docker 镜像构建与发布
**文件**: `Dockerfile`, `.dockerignore`, `docker-compose.yml`

- [x] 编写多阶段 Dockerfile
- [x] 配置基础镜像缓存
- [x] 编写 docker-compose 配置（本地开发）
- [x] 配置镜像自动构建与推送

**验收标准**:
- `docker build` 成功构建镜像
- 镜像大小 < 1GB
- `docker-compose up` 启动完整环境
- CI 自动推送镜像到 Docker Hub

---

## Phase 10: 优化与增强（可选）

### Task 10.1: 缓存机制实现
**文件**: `src/swe_agent/cache.py`, `tests/test_cache.py`

- [ ] 实现代码索引缓存
- [ ] 实现搜索结果缓存
- [ ] 实现 LLM 响应缓存（可选）
- [ ] 实现缓存失效策略

**验收标准**:
- 测试验证缓存命中率 > 50%
- 测试验证缓存大小限制
- 测试验证缓存失效逻辑
- 重复运行同一 Issue 时间减少 > 30%

---

### Task 10.2: 监控与指标收集
**文件**: `src/swe_agent/metrics.py`, `docs/MONITORING.md`

- [ ] 实现业务指标收集（成功率、执行时间）
- [ ] 实现技术指标收集（工具调用时间、LLM 延迟）
- [ ] 实现 Prometheus exporter（可选）
- [ ] 编写监控仪表盘配置

**验收标准**:
- 指标正确记录到日志
- Prometheus 可抓取指标
- Grafana 仪表盘显示核心指标
- 文档说明监控配置

---

### Task 10.3: Web UI 实现（可选）
**文件**: `src/swe_agent/web/`, `frontend/`

- [ ] 实现 FastAPI 后端
- [ ] 实现 React 前端
- [ ] 实现实时进度显示（WebSocket）
- [ ] 实现历史 session 查看

**验收标准**:
- Web UI 可提交 Issue
- 实时显示执行进度
- 显示生成的 patch
- 显示执行日志

---

### Task 10.4: 多语言支持扩展
**文件**: `src/swe_agent/languages/`, `tests/test_languages.py`

- [ ] 添加 Go 语言支持
- [ ] 添加 C/C++ 语言支持
- [ ] 添加 Ruby 语言支持
- [ ] 添加 PHP 语言支持

**验收标准**:
- 每种语言的项目类型检测
- 每种语言的语法检查
- 每种语言的测试框架支持
- E2E 测试验证至少 1 个成功案例

---

## 进度追踪

**当前阶段**: Phase 0  
**已完成任务**: 0 / 44  
**预计总工时**: 8-12 周

**里程碑**:
- [ ] Phase 0-2 完成：基础设施 + 工具层 + 沙箱层（2 周）
- [ ] Phase 3-6 完成：4 个 Agent 实现（4 周）
- [ ] Phase 7 完成：Orchestrator 实现（1 周）
- [ ] Phase 8 完成：E2E 集成与测试（1 周）
- [ ] Phase 9 完成：文档与部署（1 周）
- [ ] Phase 10 完成：优化与增强（2 周，可选）

---

**注意事项**:
1. 每个任务完成后，运行相关测试确保通过
2. 每个 Phase 完成后，进行集成测试
3. 代码提交前运行 `black`, `ruff`, `mypy` 检查
4. 所有公共 API 必须有文档字符串
5. 单元测试覆盖率保持 > 80%
