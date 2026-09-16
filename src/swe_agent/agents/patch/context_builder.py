"""
代码上下文构建器
Task 5.1: Code Context Builder

用于从源代码文件中提取和构建代码上下文，包括：
- 焦点行周围的代码
- 相关的函数/类定义
- 导入语句
- Token 数量限制
"""
import ast
from typing import List, Dict, Tuple, Optional
from pathlib import Path


class ContextBuilder:
    """代码上下文构建器"""

    def __init__(self):
        """初始化构建器"""
        pass

    def collect_imports(self, file_path: str) -> List[str]:
        """
        收集文件中的导入语句

        Args:
            file_path: Python 文件路径

        Returns:
            导入语句列表
        """
        imports = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=file_path)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.asname:
                            imports.append(f"import {alias.name} as {alias.asname}")
                        else:
                            imports.append(f"import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    names = ', '.join([
                        f"{alias.name} as {alias.asname}" if alias.asname else alias.name
                        for alias in node.names
                    ])
                    imports.append(f"from {module} import {names}")

        except Exception:
            # 文件解析失败时返回空列表
            return []

        return imports

    def extract_related_symbols(self, file_path: str, focus_lines: List[int]) -> List[Dict]:
        """
        提取焦点行相关的符号（函数/类定义）

        Args:
            file_path: Python 文件路径
            focus_lines: 焦点行号列表

        Returns:
            符号信息列表，每个符号包含 name, type, start_line, end_line
        """
        if not focus_lines:
            return []

        symbols = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content, filename=file_path)

            # 递归查找包含焦点行的符号
            self._find_symbols_recursive(tree.body, focus_lines, symbols, in_class=False)

        except Exception:
            # 解析失败时返回空列表
            return []

        # 去重（同一个符号可能被多个焦点行匹配到）
        unique_symbols = []
        seen = set()
        for symbol in symbols:
            key = (symbol['name'], symbol['start_line'], symbol['end_line'])
            if key not in seen:
                seen.add(key)
                unique_symbols.append(symbol)

        return unique_symbols

    def _find_symbols_recursive(
        self,
        nodes: List[ast.AST],
        focus_lines: List[int],
        symbols: List[Dict],
        in_class: bool = False
    ):
        """
        递归查找包含焦点行的符号

        Args:
            nodes: AST 节点列表
            focus_lines: 焦点行号列表
            symbols: 用于收集符号的列表
            in_class: 是否在类内部
        """
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                start_line = node.lineno
                end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line

                # 检查是否有焦点行在这个类的范围内
                for focus_line in focus_lines:
                    if start_line <= focus_line <= end_line:
                        symbols.append({
                            'name': node.name,
                            'type': 'class',
                            'start_line': start_line,
                            'end_line': end_line
                        })
                        break

                # 递归处理类的内容
                self._find_symbols_recursive(node.body, focus_lines, symbols, in_class=True)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start_line = node.lineno
                end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line

                # 检查是否有焦点行在这个函数的范围内
                for focus_line in focus_lines:
                    if start_line <= focus_line <= end_line:
                        symbol_type = 'method' if in_class else 'function'
                        symbols.append({
                            'name': node.name,
                            'type': symbol_type,
                            'start_line': start_line,
                            'end_line': end_line
                        })
                        break

    def extract_surrounding_context(
        self,
        lines: List[str],
        focus_lines: List[int],
        context_size: int = 50
    ) -> List[Tuple[int, str]]:
        """
        提取焦点行周围的上下文

        Args:
            lines: 文件的所有行
            focus_lines: 焦点行号列表（1-based）
            context_size: 每个焦点行前后的行数

        Returns:
            (行号, 行内容) 的列表
        """
        if not focus_lines:
            return []

        context_lines = set()

        for focus_line in focus_lines:
            # 计算范围
            start = max(1, focus_line - context_size)
            end = min(len(lines), focus_line + context_size)

            # 添加范围内的所有行号
            for line_num in range(start, end + 1):
                context_lines.add(line_num)

        # 转换为 (行号, 行内容) 并排序
        result = []
        for line_num in sorted(context_lines):
            if 1 <= line_num <= len(lines):
                result.append((line_num, lines[line_num - 1]))

        return result

    def build_context(self, file_path: str, focus_lines: List[int]) -> Dict:
        """
        构建完整的代码上下文

        Args:
            file_path: 文件路径
            focus_lines: 焦点行号列表

        Returns:
            包含完整上下文信息的字典
        """
        # 读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 收集导入语句
        imports = self.collect_imports(file_path)

        # 提取相关符号
        related_symbols = self.extract_related_symbols(file_path, focus_lines)

        # 提取周围上下文
        surrounding = self.extract_surrounding_context(lines, focus_lines, context_size=50)

        # 构建上下文字符串
        context_parts = []

        # 添加导入语句（如果有）
        if imports:
            context_parts.append("# Imports")
            for imp in imports:
                context_parts.append(imp)
            context_parts.append("")

        # 添加周围上下文
        if surrounding:
            context_parts.append("# Context")
            for line_num, line_content in surrounding:
                context_parts.append(f"{line_num:4d} | {line_content.rstrip()}")

        context_str = '\n'.join(context_parts)

        # 估算 token 数量
        token_count = self._estimate_tokens(context_str)

        return {
            'file_path': file_path,
            'focus_lines': focus_lines,
            'context': context_str,
            'imports': imports,
            'related_symbols': related_symbols,
            'token_count': token_count
        }

    def limit_context_size(self, context_data: Dict, max_tokens: int = 15000) -> Dict:
        """
        限制上下文大小，确保不超过 token 限制

        优先级顺序：
        1. 焦点行及其所在函数/类（必需）
        2. 导入语句（高优先级）
        3. 周围上下文（按距离优先）

        Args:
            context_data: build_context 返回的上下文数据
            max_tokens: 最大 token 数量

        Returns:
            限制后的上下文数据
        """
        current_tokens = context_data['token_count']

        if current_tokens <= max_tokens:
            # 不需要截断
            return {**context_data, 'truncated': False}

        # 需要截断
        # 策略：保留核心部分，逐步添加次要部分直到达到 token 限制

        focus_lines = context_data['focus_lines']
        imports = context_data['imports']
        related_symbols = context_data['related_symbols']
        file_path = context_data['file_path']

        # 读取原始文件
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 1. 必需部分：焦点行和相关符号
        essential_lines = set(focus_lines)

        # 添加相关符号的所有行
        for symbol in related_symbols:
            for line_num in range(symbol['start_line'], symbol['end_line'] + 1):
                essential_lines.add(line_num)

        # 2. 高优先级：导入语句
        import_str = '\n'.join(imports) if imports else ''

        # 3. 构建截断后的上下文
        context_parts = []

        # 添加导入
        if import_str:
            context_parts.append("# Imports")
            context_parts.append(import_str)
            context_parts.append("")

        # 添加必需行
        context_parts.append("# Context (truncated)")
        for line_num in sorted(essential_lines):
            if 1 <= line_num <= len(lines):
                context_parts.append(f"{line_num:4d} | {lines[line_num - 1].rstrip()}")

        # 计算当前 token 数
        truncated_context = '\n'.join(context_parts)
        truncated_tokens = self._estimate_tokens(truncated_context)

        # 如果还是超过限制，进一步截断（保留最核心的焦点行）
        if truncated_tokens > max_tokens:
            # 只保留焦点行和最小上下文
            context_parts = ["# Context (heavily truncated)"]
            for line_num in sorted(focus_lines):
                if 1 <= line_num <= len(lines):
                    context_parts.append(f"{line_num:4d} | {lines[line_num - 1].rstrip()}")

            truncated_context = '\n'.join(context_parts)
            truncated_tokens = self._estimate_tokens(truncated_context)

        return {
            'file_path': file_path,
            'focus_lines': focus_lines,
            'context': truncated_context,
            'imports': imports,
            'related_symbols': related_symbols,
            'token_count': truncated_tokens,
            'truncated': True
        }

    def _estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数量

        使用简单估算：单词数 * 1.3

        Args:
            text: 文本内容

        Returns:
            估算的 token 数量
        """
        return int(len(text.split()) * 1.3)
