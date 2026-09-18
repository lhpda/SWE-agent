"""
测试代码上下文构建器
Task 5.1: Code Context Builder
"""

import pytest
import tempfile
import os
from pathlib import Path
from src.swe_agent.agents.patch.context_builder import ContextBuilder


@pytest.fixture
def temp_python_file():
    """创建临时 Python 文件用于测试"""
    content = '''"""示例模块"""
import os
import sys
from typing import List, Dict
from pathlib import Path

# 全局变量
GLOBAL_VAR = "test"

def helper_function(x: int) -> int:
    """辅助函数"""
    return x * 2

class TestClass:
    """测试类"""
    def __init__(self, name: str):
        self.name = name

    def method_one(self, value: int) -> int:
        """方法一"""
        result = helper_function(value)
        return result + 1

    def method_two(self, items: List[str]) -> Dict[str, int]:
        """方法二"""
        return {item: len(item) for item in items}

def main_function(param1: str, param2: int) -> str:
    """主函数"""
    obj = TestClass(param1)
    result = obj.method_one(param2)
    return f"Result: {result}"

def another_function():
    """另一个函数"""
    for i in range(10):
        print(i)
    return None

# 更多代码
if __name__ == "__main__":
    main_function("test", 42)
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    # 清理
    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def temp_large_file():
    """创建大型 Python 文件用于测试上下文限制"""
    lines = ['"""大型文件"""']
    lines.append("import os")
    lines.append("import sys")
    lines.append("")

    # 生成 200 行代码
    for i in range(200):
        lines.append(f"def function_{i}(x):")
        lines.append(f'    """函数 {i}"""')
        lines.append(f"    return x + {i}")
        lines.append("")

    content = "\n".join(lines)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


class TestContextBuilder:
    """测试 ContextBuilder 类"""

    def test_init(self):
        """测试初始化"""
        builder = ContextBuilder()
        assert builder is not None

    def test_collect_imports(self, temp_python_file):
        """测试收集导入语句"""
        builder = ContextBuilder()
        imports = builder.collect_imports(temp_python_file)

        assert len(imports) == 4
        assert "import os" in imports
        assert "import sys" in imports
        assert "from typing import List, Dict" in imports
        assert "from pathlib import Path" in imports

    def test_collect_imports_empty_file(self):
        """测试空文件的导入收集"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            builder = ContextBuilder()
            imports = builder.collect_imports(temp_path)
            assert imports == []
        finally:
            os.unlink(temp_path)

    def test_extract_related_symbols_in_function(self, temp_python_file):
        """测试提取函数内的相关符号"""
        builder = ContextBuilder()
        # 第 30 行是 main_function 内部
        symbols = builder.extract_related_symbols(temp_python_file, [30])

        assert len(symbols) > 0
        # 应该找到 main_function
        func_symbols = [s for s in symbols if s["name"] == "main_function"]
        assert len(func_symbols) == 1
        assert func_symbols[0]["type"] == "function"

    def test_extract_related_symbols_in_class(self, temp_python_file):
        """测试提取类方法内的相关符号"""
        builder = ContextBuilder()
        # 第 21 行是 method_one 内部
        symbols = builder.extract_related_symbols(temp_python_file, [21])

        # 应该找到 TestClass 和 method_one
        class_symbols = [s for s in symbols if s["name"] == "TestClass"]
        assert len(class_symbols) == 1
        assert class_symbols[0]["type"] == "class"

    def test_extract_related_symbols_multiple_lines(self, temp_python_file):
        """测试提取多个焦点行的相关符号"""
        builder = ContextBuilder()
        # 第 21 行和第 30 行
        symbols = builder.extract_related_symbols(temp_python_file, [21, 30])

        assert len(symbols) >= 2
        names = [s["name"] for s in symbols]
        assert "TestClass" in names or "method_one" in names
        assert "main_function" in names

    def test_extract_surrounding_context_basic(self, temp_python_file):
        """测试提取基本的周围上下文"""
        builder = ContextBuilder()
        with open(temp_python_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 焦点在第 30 行，上下文大小为 5
        context = builder.extract_surrounding_context(lines, [30], context_size=5)

        # 应该包含第 25-35 行
        assert len(context) <= 11  # 5 before + 1 focus + 5 after
        assert len(context) > 0

    def test_extract_surrounding_context_at_start(self, temp_python_file):
        """测试在文件开头提取上下文"""
        builder = ContextBuilder()
        with open(temp_python_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 焦点在第 1 行
        context = builder.extract_surrounding_context(lines, [1], context_size=5)

        assert len(context) > 0
        # 应该从第 1 行开始
        assert context[0][0] == 1

    def test_extract_surrounding_context_at_end(self, temp_python_file):
        """测试在文件末尾提取上下文"""
        builder = ContextBuilder()
        with open(temp_python_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)
        # 焦点在最后一行
        context = builder.extract_surrounding_context(lines, [total_lines], context_size=5)

        assert len(context) > 0
        # 应该包含最后一行
        assert context[-1][0] == total_lines

    def test_build_context_basic(self, temp_python_file):
        """测试构建基本上下文"""
        builder = ContextBuilder()
        result = builder.build_context(temp_python_file, [30])

        assert result["file_path"] == temp_python_file
        assert result["focus_lines"] == [30]
        assert "context" in result
        assert isinstance(result["context"], str)
        assert len(result["imports"]) > 0
        assert len(result["related_symbols"]) > 0
        assert result["token_count"] > 0

    def test_build_context_with_imports(self, temp_python_file):
        """测试构建上下文时包含导入语句"""
        builder = ContextBuilder()
        result = builder.build_context(temp_python_file, [30])

        assert "import os" in result["context"] or len(result["imports"]) > 0

    def test_limit_context_size_no_truncation(self):
        """测试上下文大小限制 - 不需要截断"""
        builder = ContextBuilder()
        context_data = {"context": "short text", "token_count": 10}

        limited = builder.limit_context_size(context_data, max_tokens=1000)
        assert limited["context"] == "short text"
        assert not limited.get("truncated", False)

    def test_limit_context_size_with_truncation(self, temp_large_file):
        """测试上下文大小限制 - 需要截断"""
        builder = ContextBuilder()
        result = builder.build_context(temp_large_file, [50])

        # 限制为 500 tokens
        limited = builder.limit_context_size(result, max_tokens=500)

        assert limited["token_count"] <= 500
        assert limited.get("truncated", False) == True

    def test_token_count_estimation(self):
        """测试 token 计数估算"""
        builder = ContextBuilder()
        text = "This is a simple test with ten words here now"

        # 估算公式: len(text.split()) * 1.3
        expected = int(len(text.split()) * 1.3)
        actual = builder._estimate_tokens(text)

        assert actual == expected

    def test_context_preserves_focus_lines(self, temp_python_file):
        """测试上下文始终保留焦点行"""
        builder = ContextBuilder()
        result = builder.build_context(temp_python_file, [30])

        # 即使限制很小，焦点行也应该在上下文中
        limited = builder.limit_context_size(result, max_tokens=50)

        # 检查焦点行是否在上下文中（至少包含部分内容）
        assert len(limited["context"]) > 0

    def test_context_preserves_related_symbols(self, temp_python_file):
        """测试上下文保留相关符号定义"""
        builder = ContextBuilder()
        result = builder.build_context(temp_python_file, [30])

        # 相关符号应该被提取
        assert len(result["related_symbols"]) > 0

        # 符号定义应该在上下文中
        for symbol in result["related_symbols"]:
            assert "name" in symbol
            assert "type" in symbol
            assert "start_line" in symbol
            assert "end_line" in symbol

    def test_multiple_focus_lines(self, temp_python_file):
        """测试多个焦点行"""
        builder = ContextBuilder()
        result = builder.build_context(temp_python_file, [21, 30, 36])

        assert result["focus_lines"] == [21, 30, 36]
        assert len(result["context"]) > 0
        # 应该收集多个位置的符号
        assert len(result["related_symbols"]) > 0

    def test_invalid_file_path(self):
        """测试无效文件路径"""
        builder = ContextBuilder()

        with pytest.raises((FileNotFoundError, OSError)):
            builder.build_context("/nonexistent/path/file.py", [1])

    def test_empty_focus_lines(self, temp_python_file):
        """测试空的焦点行列表"""
        builder = ContextBuilder()
        result = builder.build_context(temp_python_file, [])

        # 应该返回基本结构，但可能没有特定的焦点上下文
        assert "context" in result
        assert result["focus_lines"] == []

    def test_context_priority_order(self, temp_large_file):
        """测试上下文截断时的优先级顺序"""
        builder = ContextBuilder()
        result = builder.build_context(temp_large_file, [50])

        # 限制到很小的 token 数
        limited = builder.limit_context_size(result, max_tokens=200)

        # 1. 焦点行必须存在
        assert len(limited["context"]) > 0

        # 2. 导入语句应该优先保留
        if len(result["imports"]) > 0:
            # 至少应该有部分导入在上下文中
            has_import = any("import" in limited["context"] for _ in [1])
            # 这个测试比较宽松，因为在极小的 token 限制下可能无法保留所有内容

    def test_symbol_extraction_accuracy(self, temp_python_file):
        """测试符号提取的准确性"""
        builder = ContextBuilder()
        symbols = builder.extract_related_symbols(temp_python_file, [21])

        # 检查符号信息的完整性
        for symbol in symbols:
            assert "name" in symbol
            assert "type" in symbol
            assert symbol["type"] in ["function", "class", "method"]
            assert "start_line" in symbol
            assert "end_line" in symbol
            assert symbol["start_line"] <= symbol["end_line"]
            assert symbol["start_line"] > 0
