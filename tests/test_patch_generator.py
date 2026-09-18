"""
测试 Patch 生成器
Task 5.2: Patch Generator

测试用例覆盖：
1. 单个补丁生成
2. 多个候选补丁生成（Beam Search）
3. Unified diff 格式化
4. 补丁大小验证
5. 补丁应用后的语法验证
6. 边界情况和错误处理
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.swe_agent.agents.patch.generator import PatchGenerator


@pytest.fixture
def temp_python_file():
    """创建临时 Python 文件用于测试"""
    content = '''def calculate_sum(a, b):
    """计算两个数的和"""
    result = a + b
    return result

def calculate_product(a, b):
    """计算两个数的乘积"""
    result = a * b
    return result

class Calculator:
    """计算器类"""
    def __init__(self):
        self.history = []

    def add(self, a, b):
        """加法"""
        result = a + b
        self.history.append(result)
        return result
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # 清理
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def sample_context():
    """示例代码上下文"""
    return {
        "file_path": "/path/to/file.py",
        "focus_lines": [3, 4],
        "context": '''# Imports
import os

# Context
   1 | def calculate_sum(a, b):
   2 |     """计算两个数的和"""
   3 |     result = a + b
   4 |     return result
   5 |
   6 | def calculate_product(a, b):
   7 |     """计算两个数的乘积"""
''',
        "imports": ["import os"],
        "related_symbols": [
            {"name": "calculate_sum", "type": "function", "start_line": 1, "end_line": 4}
        ],
        "token_count": 100,
    }


@pytest.fixture
def sample_root_cause():
    """示例根因信息"""
    return {
        "file": "/path/to/file.py",
        "line": 3,
        "type": "logic_error",
        "description": "Missing validation for negative numbers",
    }


@pytest.fixture
def sample_error_info():
    """示例错误信息"""
    return {
        "error_type": "AssertionError",
        "message": "Expected positive result, got negative",
        "traceback": "Traceback...",
    }


# ============================================================================
# Test 1: 基本补丁生成
# ============================================================================


def test_generate_patch_basic(sample_context, sample_root_cause, sample_error_info):
    """测试基本的补丁生成功能"""
    generator = PatchGenerator()

    # Mock LLM 响应
    with patch.object(generator, "_call_llm") as mock_llm:
        mock_llm.return_value = '''def calculate_sum(a, b):
    """计算两个数的和"""
    if a < 0 or b < 0:
        raise ValueError("Numbers must be positive")
    result = a + b
    return result
'''

        patch_result = generator.generate_patch(
            sample_context, sample_root_cause, sample_error_info
        )

    # 验证返回结构
    assert "patch_id" in patch_result
    assert "file_path" in patch_result
    assert "unified_diff" in patch_result
    assert "modified_lines" in patch_result
    assert "description" in patch_result
    assert "confidence" in patch_result

    # 验证字段类型
    assert isinstance(patch_result["patch_id"], str)
    assert isinstance(patch_result["file_path"], str)
    assert isinstance(patch_result["unified_diff"], str)
    assert isinstance(patch_result["modified_lines"], list)
    assert isinstance(patch_result["description"], str)
    assert isinstance(patch_result["confidence"], float)

    # 验证置信度范围
    assert 0.0 <= patch_result["confidence"] <= 1.0

    # 验证 unified diff 不为空
    assert len(patch_result["unified_diff"]) > 0


# ============================================================================
# Test 2: 多个候选补丁生成（Beam Search）
# ============================================================================


def test_generate_multiple_patches(sample_context, sample_root_cause, sample_error_info):
    """测试生成多个候选补丁"""
    generator = PatchGenerator()

    # Mock LLM 响应返回多个候选
    from unittest.mock import patch as mock_patch

    with mock_patch.object(generator, "_call_llm_multiple") as mock_llm:
        mock_llm.return_value = [
            {
                "code": '''def calculate_sum(a, b):
    """计算两个数的和"""
    if a < 0 or b < 0:
        raise ValueError("Numbers must be positive")
    result = a + b
    return result
''',
                "confidence": 0.9,
            },
            {
                "code": '''def calculate_sum(a, b):
    """计算两个数的和"""
    assert a >= 0 and b >= 0, "Numbers must be positive"
    result = a + b
    return result
''',
                "confidence": 0.85,
            },
            {
                "code": '''def calculate_sum(a, b):
    """计算两个数的和"""
    if not (a >= 0 and b >= 0):
        return None
    result = a + b
    return result
''',
                "confidence": 0.75,
            },
        ]

        patches = generator.generate_multiple_patches(
            sample_context, sample_root_cause, sample_error_info, n=3
        )

    # 验证生成了 3 个补丁
    assert len(patches) == 3

    # 验证每个补丁都有必需字段
    for patch in patches:
        assert "patch_id" in patch
        assert "unified_diff" in patch
        assert "confidence" in patch

    # 验证补丁按置信度降序排列
    confidences = [p["confidence"] for p in patches]
    assert confidences == sorted(confidences, reverse=True)

    # 验证每个补丁的 patch_id 是唯一的
    patch_ids = [p["patch_id"] for p in patches]
    assert len(patch_ids) == len(set(patch_ids))


def test_generate_multiple_patches_custom_n(sample_context, sample_root_cause, sample_error_info):
    """测试生成自定义数量的候选补丁"""
    generator = PatchGenerator()

    with patch.object(generator, "_call_llm_multiple") as mock_llm:
        mock_llm.return_value = [
            {"code": "code1", "confidence": 0.9},
            {"code": "code2", "confidence": 0.8},
            {"code": "code3", "confidence": 0.7},
            {"code": "code4", "confidence": 0.6},
            {"code": "code5", "confidence": 0.5},
        ]

        patches = generator.generate_multiple_patches(
            sample_context, sample_root_cause, sample_error_info, n=5
        )

    assert len(patches) == 5


# ============================================================================
# Test 3: Unified Diff 格式化
# ============================================================================


def test_format_as_unified_diff():
    """测试 unified diff 格式化"""
    generator = PatchGenerator()

    original = """def hello():
    print("Hello")
    return "world"
"""

    modified = """def hello():
    print("Hello, World!")
    return "world"
"""

    diff = generator.format_as_unified_diff(original, modified, filename="test.py")

    # 验证 diff 包含标准头部
    assert "---" in diff
    assert "+++" in diff

    # 验证 diff 包含修改内容
    assert '-    print("Hello")' in diff
    assert '+    print("Hello, World!")' in diff


def test_format_unified_diff_with_context():
    """测试 unified diff 包含上下文行"""
    generator = PatchGenerator()

    original = """line 1
line 2
line 3
line 4
line 5
"""

    modified = """line 1
line 2
line 3 modified
line 4
line 5
"""

    diff = generator.format_as_unified_diff(original, modified, filename="test.py")

    # 验证包含上下文行
    assert " line 1" in diff or "line 1" in diff
    assert " line 2" in diff or "line 2" in diff
    assert "-line 3" in diff
    assert "+line 3 modified" in diff


def test_format_unified_diff_multiple_changes():
    """测试多处修改的 unified diff"""
    generator = PatchGenerator()

    original = """line 1
line 2
line 3
line 4
line 5
line 6
"""

    modified = """line 1 changed
line 2
line 3
line 4 changed
line 5
line 6
"""

    diff = generator.format_as_unified_diff(original, modified, filename="test.py")

    # 验证包含两处修改
    assert "-line 1" in diff
    assert "+line 1 changed" in diff
    assert "-line 4" in diff
    assert "+line 4 changed" in diff


# ============================================================================
# Test 4: 补丁大小验证
# ============================================================================


def test_validate_patch_size_within_limit():
    """测试补丁大小在限制范围内"""
    generator = PatchGenerator()

    # 创建一个小补丁（10 行修改）
    original = "\n".join([f"line {i}" for i in range(1, 51)])
    modified = "\n".join([f"line {i}" if i > 10 else f"modified {i}" for i in range(1, 51)])

    diff = generator.format_as_unified_diff(original, modified, filename="test.py")

    # 验证通过（默认限制 50 行）
    is_valid, modified_count = generator.validate_patch_size(diff, max_lines=50)

    assert is_valid is True
    assert modified_count == 10


def test_validate_patch_size_exceeds_limit():
    """测试补丁大小超过限制"""
    generator = PatchGenerator()

    # 创建一个大补丁（60 行修改）
    original = "\n".join([f"line {i}" for i in range(1, 101)])
    modified = "\n".join([f"modified {i}" if i <= 60 else f"line {i}" for i in range(1, 101)])

    diff = generator.format_as_unified_diff(original, modified, filename="test.py")

    # 验证失败（超过 50 行限制）
    is_valid, modified_count = generator.validate_patch_size(diff, max_lines=50)

    assert is_valid is False
    assert modified_count == 60


def test_validate_patch_size_custom_limit():
    """测试自定义补丁大小限制"""
    generator = PatchGenerator()

    original = "\n".join([f"line {i}" for i in range(1, 31)])
    modified = "\n".join([f"modified {i}" for i in range(1, 31)])

    diff = generator.format_as_unified_diff(original, modified, filename="test.py")

    # 使用自定义限制 20 行
    is_valid, modified_count = generator.validate_patch_size(diff, max_lines=20)

    assert is_valid is False
    assert modified_count == 30


# ============================================================================
# Test 5: 语法验证
# ============================================================================


def test_patch_syntax_valid(temp_python_file):
    """测试补丁应用后语法正确"""
    generator = PatchGenerator()

    # 读取原始文件
    with open(temp_python_file, "r", encoding="utf-8") as f:
        original = f.read()

    # 创建一个语法正确的修改
    modified = original.replace("result = a + b", "result = a + b  # 添加注释")

    # 验证语法
    is_valid, error = generator.validate_syntax(modified, language="python")

    assert is_valid is True
    assert error is None


def test_patch_syntax_invalid():
    """测试补丁应用后语法错误"""
    generator = PatchGenerator()

    # 创建语法错误的代码
    invalid_code = """def broken_function(
    # 缺少参数列表的右括号
    return "test"
"""

    # 验证语法
    is_valid, error = generator.validate_syntax(invalid_code, language="python")

    assert is_valid is False
    assert error is not None
    assert len(error) > 0


def test_patch_syntax_indentation_error():
    """测试缩进错误的检测"""
    generator = PatchGenerator()

    invalid_code = """def function():
    x = 1
  y = 2  # 错误的缩进
    return x + y
"""

    is_valid, error = generator.validate_syntax(invalid_code, language="python")

    assert is_valid is False
    assert error is not None


# ============================================================================
# Test 6: 边界情况和错误处理
# ============================================================================


def test_generate_patch_empty_context():
    """测试空上下文的处理"""
    generator = PatchGenerator()

    empty_context = {
        "file_path": "/path/to/file.py",
        "focus_lines": [],
        "context": "",
        "imports": [],
        "related_symbols": [],
        "token_count": 0,
    }

    with patch.object(generator, "_call_llm") as mock_llm:
        mock_llm.return_value = "def dummy(): pass"

        patch_result = generator.generate_patch(
            empty_context,
            {"file": "/path/to/file.py", "line": 1},
            {"error_type": "Error", "message": "test"},
        )

    # 应该仍然能生成补丁，但置信度可能较低
    assert "patch_id" in patch_result
    assert patch_result["confidence"] >= 0.0


def test_generate_patch_llm_failure():
    """测试 LLM 调用失败的处理"""
    generator = PatchGenerator()

    with patch.object(generator, "_call_llm") as mock_llm:
        mock_llm.side_effect = Exception("LLM API Error")

        # 应该抛出异常或返回错误标识
        with pytest.raises(Exception):
            generator.generate_patch(
                {"file_path": "test.py", "context": "", "focus_lines": []},
                {"file": "test.py", "line": 1},
                {"error_type": "Error"},
            )


def test_format_unified_diff_identical_content():
    """测试相同内容的 diff（无修改）"""
    generator = PatchGenerator()

    content = """line 1
line 2
line 3
"""

    diff = generator.format_as_unified_diff(content, content, filename="test.py")

    # 应该返回空 diff 或指示无变化
    assert diff == "" or "no changes" in diff.lower()


def test_validate_patch_size_empty_diff():
    """测试空 diff 的大小验证"""
    generator = PatchGenerator()

    is_valid, modified_count = generator.validate_patch_size("", max_lines=50)

    assert is_valid is True
    assert modified_count == 0


def test_generate_multiple_patches_with_failures():
    """测试部分候选生成失败的情况"""
    generator = PatchGenerator()

    # Mock 返回少于请求数量的候选
    with patch.object(generator, "_call_llm_multiple") as mock_llm:
        mock_llm.return_value = [
            {"code": "code1", "confidence": 0.9},
            {"code": "code2", "confidence": 0.8},
            # 只返回 2 个，而不是请求的 5 个
        ]

        patches = generator.generate_multiple_patches(
            {"file_path": "test.py", "context": "", "focus_lines": []},
            {"file": "test.py", "line": 1},
            {"error_type": "Error"},
            n=5,
        )

    # 应该返回实际生成的数量
    assert len(patches) == 2


# ============================================================================
# Test 7: 集成测试
# ============================================================================


def test_end_to_end_patch_generation(temp_python_file):
    """端到端的补丁生成测试"""
    generator = PatchGenerator()

    # 读取原始文件
    with open(temp_python_file, "r", encoding="utf-8") as f:
        original_content = f.read()

    context = {
        "file_path": temp_python_file,
        "focus_lines": [2, 3, 4],
        "context": original_content,
        "imports": [],
        "related_symbols": [],
        "token_count": 100,
    }

    root_cause = {
        "file": temp_python_file,
        "line": 3,
        "type": "logic_error",
        "description": "Missing validation",
    }

    error_info = {"error_type": "ValueError", "message": "Invalid input", "traceback": ""}

    with patch.object(generator, "_call_llm") as mock_llm:
        # 模拟生成修复后的代码
        mock_llm.return_value = original_content.replace(
            "result = a + b",
            'if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):\n        raise TypeError("Arguments must be numbers")\n    result = a + b',
        )

        patch_result = generator.generate_patch(context, root_cause, error_info)

    # 验证补丁结构完整
    assert patch_result["file_path"] == temp_python_file
    assert len(patch_result["unified_diff"]) > 0
    assert len(patch_result["modified_lines"]) > 0

    # 验证补丁大小在限制内
    is_valid, count = generator.validate_patch_size(patch_result["unified_diff"], max_lines=50)
    assert is_valid is True
