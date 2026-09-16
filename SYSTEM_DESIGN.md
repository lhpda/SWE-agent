# SWE Agent 系统设计说明书

**版本**: 1.0  
**日期**: 2026-09-15  
**架构模式**: 多阶段流水线（Multi-Stage Pipeline）

---

## 目录

1. [系统概述](#1-系统概述)
2. [系统拓扑与数据流](#2-系统拓扑与数据流)
3. [模块边界与职责划分](#3-模块边界与职责划分)
4. [核心数据结构定义](#4-核心数据结构定义)
5. [容错与防御策略](#5-容错与防御策略)
6. [测试策略](#6-测试策略)
7. [技术栈选型](#7-技术栈选型)
8. [部署与运维](#8-部署与运维)

---

## 1. 系统概述

### 1.1 目标

构建一个自动化的软件工程智能体（SWE Agent），能够：
- 输入：GitHub Issue URL + 本地代码仓库路径
- 输出：经过验证的最小化 patch
- 核心能力：问题定位、错误复现、代码修复、测试验证

### 1.2 核心设计原则

1. **阶段隔离**：每个阶段独立的上下文和工具集，避免累积性上下文污染
2. **结构化传递**：阶段间通过 JSON Schema 定义的结构化数据传递，而非自然语言
3. **早期失败**：在每个阶段边界进行验证，快速失败而非传播错误
4. **可观测性**：每个阶段输出可审计的中间结果和决策依据
5. **资源受限**：每个阶段有明确的超时、重试和资源限制

### 1.3 非目标

- **不支持**：需要修改多个独立模块的架构级重构
- **不支持**：需要人工判断的设计决策（如 API 设计变更）
- **不保证**：100% 的测试通过率（只保证不破坏现有通过的测试）

---

## 2. 系统拓扑与数据流

### 2.1 系统架构与数据流

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                                  │
│  GitHub Issue + Repository Path                                      │
└────────────────────────────┬────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR LAYER                                │
│  • Pipeline state machine                                            │
│  • Stage transition logic                                            │
│  • Error aggregation & retry policy                                  │
└────┬──────────┬──────────┬──────────┬──────────────────────────────┘
     │          │          │          │
     ↓          ↓          ↓          ↓
┌─────────┐ ┌──────────┐ ┌─────────┐ ┌────────────┐
│ Stage 1 │ │ Stage 2  │ │ Stage 3 │ │  Stage 4   │
│Localiza-│ │Reproduc- │ │  Patch  │ │ Validation │
│  tion   │ │  tion    │ │   Gen   │ │            │
└────┬────┘ └────┬─────┘ └────┬────┘ └─────┬──────┘
     │           │            │            │
     ↓           ↓            ↓            ↓
   JSON        JSON         JSON         JSON
  Result      Result       Result       Result
     │           │            │            │
     └───────────┴────────────┴────────────┘
                     ↓
          ┌──────────────────┐
          │  State Storage   │
          │  (Persistence)   │
          └──────────────────┘
                     ↓
          ┌──────────────────┐
          │  Final Output    │
          │  • patch file    │
          │  • test results  │
          │  • execution log │
          └──────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     CROSS-CUTTING LAYERS                             │
│                                                                       │
│  TOOL LAYER:     ripgrep | tree-sitter | file-io | git              │
│  SANDBOX LAYER:  Docker Container (Stage 2 & 4 only)                │
│  LLM LAYER:      Claude API (one per stage agent)                   │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 阶段流转与容错矩阵

| 源阶段 | 目标阶段 | 触发条件 | 最大重试 | 回退策略 | 超时限制 |
|--------|---------|---------|---------|---------|---------|
| **Input → Localization** | Localization | Issue 解析成功 | 3 次 | 第 3 次扩大搜索范围 | 5 分钟 |
| **Localization → Reproduction** | Reproduction | 置信度 ≥ 0.3 | 5 次 | 尝试不同测试命令 | 8 分钟 |
| **Localization ← Reproduction** | Localization | 未能复现错误 | 最多回退 2 次 | 扩大候选文件范围 | - |
| **Reproduction → Patch** | Patch Generation | 成功复现根因 | 5 次（beam search） | 生成多个候选 patch | 6 分钟 |
| **Patch → Validation** | Validation | 语法检查通过 | 1 次/patch | 语法错误则拒绝该 patch | 10 分钟 |
| **Patch ← Validation** | Patch Generation | 测试失败（非回归） | 最多回退 3 次 | 生成新候选 | - |
| **Validation → Output** | Final Output | 目标测试通过且无回归 | - | - | - |
| **全局终止** | - | 总执行时间 > 30 分钟 | - | 保存当前状态并终止 | 30 分钟 |

**连续失败熔断规则**：
- 连续 3 次工具调用失败 → 终止当前阶段
- 连续 5 次工具返回空结果 → 终止当前阶段
- 滑动窗口（size=5）内同一操作签名出现 ≥3 次 → 判定为死循环并熔断

---

## 3. 模块边界与职责划分

### 3.1 Orchestrator Layer（状态调度层）

**模块**: `PipelineOrchestrator`

**职责**:
- 管理流水线状态机（IDLE → LOCALIZING → REPRODUCING → PATCHING → VALIDATING → DONE/FAILED）
- 执行阶段转换逻辑（前进、回退、终止）
- 聚合错误并应用重试策略
- 维护全局上下文（Issue 信息、仓库元数据、已尝试的方案）

**关键接口**:
```
run(issue: Issue, repo_path: str) -> PipelineResult
resume(session_id: str) -> PipelineResult
get_state(session_id: str) -> PipelineState
```

### 3.2 LocalizationAgent

**职责**:
- 解析 Issue 提取关键信息（错误信息、堆栈追踪、受影响的功能）
- 使用代码搜索工具定位候选文件
- 使用符号索引缩小范围到具体函数/类
- 输出排序后的候选列表（带置信度评分）

**工具集**:
- `ripgrep_search(pattern, file_types)`
- `symbol_search(symbol_name, symbol_type)`
- `read_file(path, line_range)`
- `get_git_blame(file, line_range)`

**输入**: `IssueContext`  
**输出**: `LocalizationResult`

**成功标准**:
- 至少返回 1 个候选文件
- Top-3 候选的置信度总和 > 0.6

**运行环境**: 宿主机

### 3.3 ReproductionAgent

**职责**:
- 检测项目类型和测试框架
- 复现 Issue 中描述的错误
- 分析错误日志和堆栈追踪
- 确认根因位置

**工具集**:
- `detect_project_type()` - 返回 python/nodejs/java/rust 等
- `detect_test_command()` - 自动发现测试命令
- `run_test_in_sandbox(test_path, timeout)`
- `parse_error_log(log_content)`

**输入**: `LocalizationResult`  
**输出**: `ReproductionResult`

**成功标准**:
- 成功触发错误（测试失败或异常抛出）
- 错误堆栈与 Issue 描述匹配

**运行环境**: Docker 沙箱

### 3.4 PatchGeneratorAgent

**职责**:
- 基于根因分析生成修复代码
- 生成最小化 patch（只修改必要的行）
- 进行语法校验
- 可生成多个候选 patch（beam search）

**工具集**:
- `read_file_with_context(path, focus_lines, context_lines=50)`
- `generate_diff(original, modified)`
- `syntax_check(file_path, language)`
- `apply_patch_dry_run(patch)`

**输入**: `ReproductionResult`  
**输出**: `PatchResult` (可包含多个候选)

**成功标准**:
- Patch 能够干净应用（无冲突）
- 修改后的代码通过语法检查
- Patch 行数 < 50（防止过度修改）

**运行环境**: 宿主机

### 3.5 ValidationAgent

**职责**:
- 应用 patch 到干净的仓库副本
- 运行完整测试套件
- 检查回归（确保未破坏其他测试）
- 生成验证报告

**工具集**:
- `apply_patch(patch, target_dir)`
- `run_full_test_suite(timeout=600)`
- `compare_test_results(before, after)`
- `check_code_coverage()`

**输入**: `PatchResult`  
**输出**: `ValidationResult`

**成功标准**:
- 目标测试从失败变为通过
- 无新增的测试失败（回归检查）
- 代码覆盖率未显著下降

**运行环境**: Docker 沙箱

### 3.6 Tool Layer（工具层）

所有工具实现统一接口：

```
interface Tool {
  name: string
  description: string
  parameters: JSONSchema
  
  execute(params: dict) -> ToolResult
  validate_params(params: dict) -> bool
}
```

**工具分类**:

| 类别 | 工具 | 是否需要沙箱 |
|-----|------|-------------|
| **搜索** | ripgrep_search, symbol_search, ast_query | 否 |
| **文件操作** | read_file, write_file, apply_patch | 否（读） / 是（写） |
| **代码分析** | syntax_check, parse_ast, get_imports | 否 |
| **执行** | run_command, run_test, install_deps | 是 |
| **Git** | git_diff, git_blame, git_log | 否 |

**工具设计原则**:
1. **幂等性**: 同样输入多次调用产生同样结果
2. **快速失败**: 参数验证在执行前完成
3. **输出截断**: 所有工具输出限制在 10KB（防止上下文爆炸）
4. **超时保护**: 每个工具有默认超时（可配置）

### 3.7 Sandbox Layer（沙箱层）

**模块**: `DockerSandbox`

**职责**:
- 创建隔离的 Docker 容器
- 管理容器生命周期（创建、暂停、恢复、销毁）
- 文件系统映射（宿主机代码 → 容器工作区）
- 资源限制（CPU、内存、磁盘、网络）

**容器配置**:

```
每个 Issue 使用独立的容器：
  - 基础镜像：根据项目类型选择（python:3.11, node:20, openjdk:17）
  - 只读挂载：原始仓库代码
  - 读写挂载：工作区目录
  - 生命周期：Reproduction 阶段创建 → Validation 阶段复用 → 完成后销毁
```

**资源限制**:
```
Docker 参数：
  --cpus=2
  --memory=4g
  --memory-swap=4g (禁用 swap)
  --pids-limit=1000
  --network=custom (受限网络)
  --read-only (根文件系统只读)
  --tmpfs /tmp:rw,size=1g
  
执行限制：
  - 单次执行最长 10 分钟
  - 容器最长生命周期：2 小时
```

**网络白名单**:
```
允许的域名：
  - pypi.org, files.pythonhosted.org  (Python)
  - npmjs.com, registry.npmjs.org     (Node.js)
  - maven.org, repo.maven.apache.org  (Java)
  - crates.io, static.crates.io       (Rust)
  - github.com (仅用于 git clone 依赖)
  
禁止：
  - 所有其他外部网络访问
  - 访问宿主机网络
  - 容器间通信
```

**安全策略**:
- 使用非 root 用户运行
- 禁用特权模式
- 使用 seccomp 配置限制系统调用
- 启用 AppArmor / SELinux
- Orphan 容器由后台守护进程清理

**关键接口**:
```
create(image: str, volumes: dict) -> ContainerID
execute(container_id: str, command: str, timeout: int) -> ExecResult
copy_file(container_id: str, src: str, dst: str)
destroy(container_id: str)
```

### 3.8 Storage Layer（存储层）

**模块**: `StateStore`

**职责**:
- 持久化每个阶段的中间结果
- 记录完整的执行轨迹（用于调试和审计）
- 支持断点续传（从失败的阶段恢复）

**存储结构**:
```
.swe-agent/
├── sessions/
│   ├── {session_id}/
│   │   ├── metadata.json          # Issue 信息、仓库路径、时间戳
│   │   ├── stage_1_localization.json
│   │   ├── stage_2_reproduction.json
│   │   ├── stage_3_patch.json
│   │   ├── stage_4_validation.json
│   │   ├── execution_log.jsonl    # 每行一个工具调用记录
│   │   └── final_patch.diff
├── cache/
│   ├── repo_indexes/              # 符号索引缓存
│   └── docker_images/             # Docker 镜像缓存
```

**关键接口**:
```
save_stage_result(session_id: str, stage: str, result: dict)
load_stage_result(session_id: str, stage: str) -> dict
append_log(session_id: str, log_entry: dict)
list_sessions(filter: dict) -> List[SessionMetadata]
```

---

## 4. 核心数据结构定义

### 4.1 基础类型

#### IssueContext

```typescript
{
  "issue_id": string,              // GitHub Issue ID
  "title": string,
  "body": string,                  // 原始 Markdown 内容
  "parsed": {
    "error_message": string | null,      // 提取的错误信息
    "stack_trace": string[] | null,      // 提取的堆栈追踪
    "reproduction_steps": string[] | null,
    "expected_behavior": string | null,
    "actual_behavior": string | null,
    "affected_versions": string[] | null
  },
  "metadata": {
    "created_at": string,          // ISO 8601
    "labels": string[],
    "author": string
  }
}
```

#### RepositoryContext

```typescript
{
  "path": string,                  // 绝对路径
  "git": {
    "remote_url": string | null,
    "current_branch": string,
    "commit_sha": string,          // 工作基准点
    "is_dirty": boolean
  },
  "project_type": string,          // "python" | "nodejs" | "java" | "rust" | "unknown"
  "test_framework": string | null, // "pytest" | "jest" | "junit" | null
  "dependencies": {
    "files": string[],             // package.json, requirements.txt, pom.xml
    "installed": boolean
  }
}
```

### 4.2 阶段结果类型

#### LocalizationResult

```typescript
{
  "status": "success" | "partial" | "failed",
  "candidates": [
    {
      "file_path": string,         // 相对仓库根目录
      "confidence": float,         // 0.0 - 1.0
      "reason": string,            // 为什么选择这个文件
      "relevant_symbols": [
        {
          "name": string,
          "type": "function" | "class" | "method",
          "line_start": int,
          "line_end": int
        }
      ],
      "code_snippet": string       // 关键代码片段（最多 50 行）
    }
  ],
  "search_strategy": string,       // 使用的搜索策略描述
  "execution_time": float,         // 秒
  "tool_calls": int                // 调用工具的次数
}
```

#### ReproductionResult

```typescript
{
  "status": "reproduced" | "not_reproduced" | "error",
  "root_cause": {
    "file_path": string,
    "line_number": int | null,
    "function_name": string | null,
    "explanation": string          // 根因的自然语言解释
  } | null,
  "error_details": {
    "error_type": string,          // Exception 类型
    "error_message": string,
    "stack_trace": string[],
    "relevant_logs": string        // 截断到最后 200 行
  } | null,
  "test_command": string,          // 用于复现的命令
  "test_output": string,           // 截断到 5KB
  "execution_time": float,
  "attempts": int                  // 重试次数
}
```

#### PatchResult

```typescript
{
  "status": "generated" | "failed",
  "patches": [                     // 可能有多个候选
    {
      "id": string,                // UUID
      "diff": string,              // Unified diff 格式
      "description": string,       // 修复说明
      "files_changed": string[],
      "lines_added": int,
      "lines_removed": int,
      "confidence": float,         // 生成器对该 patch 的置信度
      "syntax_valid": boolean
    }
  ],
  "generation_strategy": string,   // "single_fix" | "beam_search"
  "execution_time": float
}
```

#### ValidationResult

```typescript
{
  "status": "passed" | "failed" | "error",
  "patch_id": string,              // 验证的 patch ID
  "test_results": {
    "total": int,
    "passed": int,
    "failed": int,
    "skipped": int,
    "error": int
  },
  "target_test_status": "passed" | "failed" | "not_found",  // Issue 相关的测试
  "regression_check": {
    "new_failures": string[],      // 新失败的测试名称
    "fixed_tests": string[],       // 修复的测试名称
    "is_regression": boolean
  },
  "test_output": string,           // 截断到 10KB
  "execution_time": float
}
```

### 4.3 执行状态类型

#### PipelineState

```typescript
{
  "session_id": string,
  "status": "idle" | "running" | "success" | "failed" | "cancelled",
  "current_stage": "localization" | "reproduction" | "patch_generation" | "validation" | null,
  "stages": {
    "localization": StageStatus,
    "reproduction": StageStatus,
    "patch_generation": StageStatus,
    "validation": StageStatus
  },
  "retry_count": int,
  "max_retries": int,
  "started_at": string,            // ISO 8601
  "updated_at": string,
  "completed_at": string | null,
  "error": ErrorInfo | null
}
```

#### StageStatus

```typescript
{
  "status": "pending" | "running" | "success" | "failed" | "skipped",
  "started_at": string | null,
  "completed_at": string | null,
  "duration": float | null,        // 秒
  "result": object | null,         // 阶段对应的 Result 类型
  "error": ErrorInfo | null,
  "retries": int
}
```

#### ErrorInfo

```typescript
{
  "type": "tool_error" | "agent_error" | "validation_error" | "timeout" | "resource_limit",
  "message": string,
  "details": object,               // 结构化的错误详情
  "recoverable": boolean,          // 是否可重试
  "timestamp": string
}
```

### 4.4 工具调用类型

#### ToolCall

```typescript
{
  "id": string,                    // UUID
  "tool_name": string,
  "parameters": object,            // 符合工具的 JSON Schema
  "timestamp": string,
  "caller": string                 // "localization_agent" | "reproduction_agent" 等
}
```

#### ToolResult

```typescript
{
  "call_id": string,               // 对应的 ToolCall.id
  "status": "success" | "error",
  "output": string | object,       // 工具的返回值
  "error": string | null,
  "execution_time": float,         // 毫秒
  "truncated": boolean,            // 输出是否被截断
  "metadata": {
    "sandbox_used": boolean,
    "cache_hit": boolean
  }
}
```

### 4.5 最终输出类型

#### PipelineResult

```typescript
{
  "session_id": string,
  "status": "success" | "failed",
  "issue": IssueContext,
  "repository": RepositoryContext,
  "final_patch": {
    "diff": string,
    "description": string,
    "files_changed": string[],
    "validation_passed": boolean
  } | null,
  "execution_summary": {
    "total_time": float,
    "stages_completed": string[],
    "tool_calls_total": int,
    "llm_calls_total": int,
    "tokens_used": int
  },
  "audit_log": string,             // 指向 execution_log.jsonl 的路径
  "error": ErrorInfo | null
}
```

---

## 5. 容错与防御策略

### 5.1 输出截断与上下文管理

#### 工具输出截断规则

```
文本输出：最多 10KB（约 10,000 字符）
测试日志：最多 5KB，保留最后的内容（错误通常在末尾）
文件内容：最多 50,000 字符（约 2000 行）
搜索结果：最多 100 条匹配
目录列表：最多 500 个文件
```

**截断策略**：
- 对于日志：保留最后 N 行 + 标记 `[truncated, showing last N lines]`
- 对于代码：保留关键部分（函数定义、类定义）+ 标记省略位置
- 对于搜索：按相关性排序后截断

#### LLM 上下文管理

```
每个 Agent 的最大上下文：
  - System Prompt: 2K tokens
  - Tools Definition: 1K tokens
  - Input Data: 4K tokens
  - Previous Tool Results: 8K tokens
  - 总计：约 15K tokens（安全边界，远低于 200K 限制）

上下文压缩策略：
  - 只传递上一阶段的结构化结果，不传递原始日志
  - Tool Results 超过限制时，使用摘要而非完整输出
  - 保留最近 5 次工具调用的完整结果，更早的只保留摘要
```

### 5.2 语法破坏回滚

#### Patch 应用前验证

```
验证流程：
  1. 语法检查（syntax_check）
  2. Dry-run 应用（git apply --check）
  3. 解析修改后的 AST（确保结构完整）
  4. 检查关键符号是否仍然可访问

失败处理：
  - 语法错误 → 回退到 Patch Generation，附加错误信息
  - 应用冲突 → 检查是否是基准版本问题，如果是则更新基准
  - AST 损坏 → 拒绝该 patch，尝试下一个候选
```

#### 自动回滚机制

```
应用 Patch 的安全流程：
  1. 创建 Git stash（保存当前状态）
  2. 应用 patch
  3. 运行语法检查
  4. 如果失败，执行 git stash pop（恢复原状态）
  5. 如果成功，继续验证流程

容器内的回滚：
  - 使用 Docker snapshot 功能
  - 在应用 patch 前创建快照
  - 验证失败后恢复到快照状态
```

### 5.3 资源限制

#### 文件系统保护

```
限制：
  - 单个 session 最多创建 1GB 临时文件
  - 最多保留最近 100 个 session 的数据（FIFO 清理）
  - patch 文件最大 1MB

监控：
  - 每次文件写入前检查磁盘配额
  - 超过限制时拒绝写入并返回错误
```

### 5.4 错误恢复策略

| 错误类型 | 重试策略 | 回退策略 |
|---------|---------|---------|
| **工具超时** | 重试 3 次，每次增加 50% 超时时间 | 无 |
| **LLM API 限流** | 指数退避重试（1s, 2s, 4s, 8s） | 无 |
| **语法错误 Patch** | 不重试，尝试下一个候选 | 回退到 Patch Generation |
| **测试失败（非回归）** | 不重试当前 patch | 回退到 Patch Generation |
| **依赖安装失败** | 重试 2 次，不同的包管理器策略 | 终止（记录错误） |
| **仓库路径不存在** | 不重试 | 立即终止，返回配置错误 |
| **Issue 解析失败** | 不重试 | 立即终止，返回输入错误 |
| **Docker daemon 不可用** | 重试 1 次 | 仍失败则终止 |
| **磁盘空间不足** | 不重试 | 立即终止，返回资源错误 |

#### 断点续传

**支持的恢复场景**：
- 进程崩溃后从最后完成的阶段恢复
- 用户手动取消后可选择从当前阶段继续
- 网络中断后自动重连并继续

**不支持的场景**：
- 阶段内部的部分完成（每个阶段是原子的）
- 跨不同代码版本的恢复（commit SHA 变化）

---

## 6. 测试策略

### 6.1 测试金字塔

```
        ┌──────────────┐
        │   E2E Tests  │  10% - 完整流水线
        └──────────────┘
            ▲
    ┌────────────────────┐
    │  Integration Tests │  30% - 阶段间集成
    └────────────────────┘
            ▲
┌──────────────────────────────┐
│      Unit Tests              │  60% - 工具/Agent/Orchestrator
└──────────────────────────────┘
```

### 6.2 单元测试原则

**Tool Layer**：
- 每个工具独立测试，不依赖真实 LLM
- 使用 mock 文件系统和命令执行
- 验证输入验证、输出格式、错误处理、超时机制、截断逻辑

**Agent Layer**：
- Mock LLM API 返回预定义的响应
- 使用真实的工具（但在隔离环境）
- 验证 Agent 的决策逻辑和工具编排
- 测试边界条件（无候选、模糊输入、错误传播）

**Orchestrator Layer**：
- Mock 所有 Agent 返回预定义结果
- 专注测试状态转换逻辑
- 验证重试、回退、错误聚合
- 测试状态持久化与恢复

### 6.3 集成测试原则

**阶段间数据传递**：
- 使用真实的 Agent 和工具
- Mock LLM 返回可控的决策
- 验证数据格式转换和阶段协作

**端到端工具链**：
- 执行搜索 → 读取文件 → 分析 AST 的完整流程
- 生成 patch → 应用 → 运行测试的完整流程
- 验证回滚机制

### 6.4 E2E 测试数据集

准备 10 个精心挑选的测试用例：
- 3 个简单 Bug（单行修复）
- 4 个中等复杂度（需要理解多个文件）
- 2 个复杂场景（需要多次回退）
- 1 个负面案例（应该失败的 Issue）

每个测试用例包含：
- Issue 描述（JSON）
- 干净的仓库副本（Git 仓库，固定 commit SHA）
- 预期的 patch（用于验证）
- 预期的测试结果

### 6.5 可重复性保证

**确定性措施**：
- 所有时间戳使用固定值（mock datetime）
- 所有随机数使用固定种子
- Docker 容器使用固定标签（不使用 :latest）
- 网络请求全部 mock（除了真实的 E2E）
- 文件系统操作使用临时目录（自动清理）

**测试隔离**：
- 每个测试创建临时工作目录
- 每个测试创建独立的 Docker 网络
- 每个测试重置状态存储
- teardown 时清理所有容器、网络、临时目录

### 6.6 CI 准入标准

```yaml
准入要求：
  - 单元测试覆盖率 > 80%
  - 所有集成测试通过
  - E2E 快速子集（3 个用例）通过
  - 无容器泄漏（自动检测 orphan 容器）
  - 完整 E2E 只在 release 分支运行
```

---

## 7. 技术栈选型

| 组件 | 技术选型 | 理由 |
|------|---------|------|
| **编程语言** | Python 3.11+ | 丰富的 AI/工具生态，易于原型开发 |
| **LLM SDK** | Anthropic SDK | 官方支持，流式输出，函数调用 |
| **容器化** | Docker SDK for Python | 成熟的容器管理，跨平台支持 |
| **代码搜索** | ripgrep (subprocess) | 极快的全文搜索 |
| **AST 解析** | tree-sitter | 多语言支持，准确的语法分析 |
| **符号索引** | ctags / Language Server Protocol | 快速符号定位 |
| **Git 操作** | 原生 subprocess 封装 | 零第三方依赖，精确支持 apply/stash/diff 等底层命令，透明且便于超时控制 |
| **数据验证** | Pydantic v2 | 强类型数据结构，自动验证 |
| **状态存储** | SQLite + JSON | 轻量级，无需外部数据库 |
| **日志** | structlog | 结构化日志，易于解析 |
| **测试框架** | pytest + pytest-docker | 丰富的插件，容器测试支持 |

**开发工具**:
- black (代码格式化)
- ruff (超快的 linter)
- mypy (类型检查)
- poetry (依赖管理)
- mkdocs-material (文档生成)
- GitHub Actions (CI/CD)

---

## 8. 部署与运维

### 8.1 部署模式

#### 本地单机模式

```
适用场景：开发、调试、小规模使用

架构：
  - 所有组件运行在同一台机器
  - 使用本地 Docker daemon
  - 状态存储在本地文件系统

资源需求：
  - CPU: 4 核+
  - 内存: 16GB+
  - 磁盘: 100GB+（用于 Docker 镜像和工作区）
```

#### 服务器模式

```
适用场景：团队共享、批量处理

架构：
  - Orchestrator 作为长期运行的服务
  - 提供 REST API 接收 Issue
  - 使用队列管理多个并发 session
  - 集中式状态存储（PostgreSQL）

资源需求：
  - 服务器：8 核 32GB 内存
  - 每个并发 session 需要额外 4GB 内存
  - 建议最大并发：4-8 个 session
```

### 8.2 监控指标

**业务指标**：
- success_rate: 成功修复的 Issue 比例
- avg_execution_time: 平均执行时间
- stage_completion_rate: 各阶段完成率
- patch_acceptance_rate: 生成的 patch 被接受的比例

**技术指标**：
- llm_api_latency: LLM API 响应延迟
- tool_execution_time: 各工具平均执行时间
- container_startup_time: 容器启动耗时
- disk_usage: 磁盘空间使用情况
- active_sessions: 当前活跃的 session 数

**错误指标**：
- error_rate_by_stage: 各阶段错误率
- timeout_rate: 超时发生率
- oom_events: 内存溢出事件

### 8.3 日志策略

**结构化日志格式（JSON Lines）**：
```json
{
  "timestamp": "2026-09-15T10:30:00Z",
  "level": "INFO",
  "session_id": "abc123",
  "stage": "localization",
  "event": "tool_call",
  "tool": "ripgrep_search",
  "duration_ms": 150,
  "result": "success"
}
```

**日志级别**：
- ERROR: 影响 session 执行的错误
- WARNING: 非致命问题（如重试、降级）
- INFO: 阶段转换、关键决策
- DEBUG: 详细的工具调用和 LLM 交互

### 8.4 成本估算

| Issue 复杂度 | LLM Tokens | Claude Sonnet 成本 | 容器运行时间 | 总成本 |
|-------------|-----------|-------------------|-------------|--------|
| **简单** | ~50K | ~$0.15 | 2-3 分钟 | ~$0.15 |
| **中等** | ~150K | ~$0.45 | 5-8 分钟 | ~$0.45 |
| **复杂** | ~300K | ~$0.90 | 15-20 分钟 | ~$0.90 |

**成本优化策略**：
- 使用更便宜的模型进行 Localization（如 Claude Haiku）
- 缓存重复的代码索引和搜索结果
- 批量处理多个 Issue 时共享容器环境
- 对简单 Issue 使用快速路径（跳过 Reproduction）

### 8.5 安全考虑

**输入验证**：
- Issue 内容限制大小（最大 100KB）
- 过滤恶意 Markdown（XSS 防护）
- 验证 URL 格式（防止 SSRF）
- 仓库路径必须在白名单根目录下
- 禁止符号链接（防止路径遍历）

**代码执行安全**（详见 3.7 Sandbox Layer）：
- 容器资源限制与网络隔离
- 使用非 root 用户运行
- seccomp / AppArmor / SELinux 加固

**敏感信息保护**：
- 在所有日志中屏蔽 API keys、密码模式
- LLM 请求中排除 .env、secrets.json 等文件
- 审计日志访问控制（仅管理员可见）
- 支持使用自托管的 LLM（如 vLLM）
- 可配置数据保留策略（GDPR 合规）

---

## 附录

### A. 参考资料

- SWE-bench: https://www.swebench.com/
- ReAct: Reasoning and Acting in Language Models
- Docker Security: https://docs.docker.com/engine/security/
- Tree-sitter: https://tree-sitter.github.io/
- Anthropic Claude API: https://docs.anthropic.com/

### B. 演进路线

**Phase 1 (MVP)**: 4 阶段 | 单机部署 | Python/Node.js | 基础工具集  
**Phase 2 (+3 月)**: 多语言 | 调用图分析 | Beam search | Web UI  
**Phase 3 (+6 月)**: K8s | 分布式 | 持续学习 | CI/CD 集成  
**Phase 4 (+12 月)**: 多 Issue 分析 | 主动检测 | 代码审查 | 人机协作

---

**文档版本**: 1.0  
**最后更新**: 2026-09-15  
**维护者**: SWE Agent 开发团队
