"""
Patch 生成器
Task 5.2: Patch Generator

功能：
1. 生成单个修复补丁
2. 生成多个候选补丁（Beam Search）
3. 格式化为 unified diff
4. 验证补丁大小
5. 验证语法正确性
"""
import ast
import difflib
import uuid
from typing import Dict, List, Tuple, Optional, Any


class PatchGenerator:
    """Patch 生成器"""

    def __init__(self):
        """初始化生成器"""
        pass

    def generate_patch(
        self,
        context: Dict[str, Any],
        root_cause: Dict[str, Any],
        error_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        生成单个修复补丁

        Args:
            context: 代码上下文（来自 ContextBuilder）
            root_cause: 根因信息
            error_info: 错误信息

        Returns:
            补丁信息字典，包含：
            - patch_id: 补丁唯一标识
            - file_path: 文件路径
            - unified_diff: unified diff 格式的补丁
            - modified_lines: 修改的行号列表
            - description: 补丁描述
            - confidence: 置信度（0.0-1.0）
        """
        # 调用 LLM 生成修复代码
        modified_code = self._call_llm(context, root_cause, error_info)

        # 提取原始代码
        original_code = self._extract_original_code(context)

        # 生成 unified diff
        file_path = context.get('file_path', 'unknown')
        unified_diff = self.format_as_unified_diff(
            original_code,
            modified_code,
            filename=file_path
        )

        # 提取修改的行号
        modified_lines = self._extract_modified_lines(unified_diff)

        # 生成描述
        description = self._generate_description(root_cause, error_info)

        # 计算置信度
        confidence = self._calculate_confidence(context, modified_code)

        return {
            'patch_id': str(uuid.uuid4()),
            'file_path': file_path,
            'unified_diff': unified_diff,
            'modified_lines': modified_lines,
            'description': description,
            'confidence': confidence
        }

    def generate_multiple_patches(
        self,
        context: Dict[str, Any],
        root_cause: Dict[str, Any],
        error_info: Dict[str, Any],
        n: int = 3
    ) -> List[Dict[str, Any]]:
        """
        生成多个候选补丁（Beam Search）

        Args:
            context: 代码上下文
            root_cause: 根因信息
            error_info: 错误信息
            n: 生成的候选数量

        Returns:
            补丁列表，按置信度降序排列
        """
        # 调用 LLM 生成多个候选
        candidates = self._call_llm_multiple(context, root_cause, error_info, n)

        # 提取原始代码
        original_code = self._extract_original_code(context)
        file_path = context.get('file_path', 'unknown')

        patches = []
        for candidate in candidates:
            modified_code = candidate['code']
            confidence = candidate['confidence']

            # 生成 unified diff
            unified_diff = self.format_as_unified_diff(
                original_code,
                modified_code,
                filename=file_path
            )

            # 提取修改的行号
            modified_lines = self._extract_modified_lines(unified_diff)

            # 生成描述
            description = self._generate_description(root_cause, error_info)

            patches.append({
                'patch_id': str(uuid.uuid4()),
                'file_path': file_path,
                'unified_diff': unified_diff,
                'modified_lines': modified_lines,
                'description': description,
                'confidence': confidence
            })

        # 按置信度降序排列
        patches.sort(key=lambda x: x['confidence'], reverse=True)

        return patches

    def format_as_unified_diff(
        self,
        original: str,
        modified: str,
        filename: str = 'file'
    ) -> str:
        """
        格式化为 unified diff

        Args:
            original: 原始代码
            modified: 修改后的代码
            filename: 文件名

        Returns:
            unified diff 格式的字符串
        """
        # 分割成行
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        # 生成 unified diff
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f'a/{filename}',
            tofile=f'b/{filename}',
            lineterm=''
        )

        diff_text = '\n'.join(diff)

        return diff_text

    def validate_patch_size(
        self,
        patch: str,
        max_lines: int = 50
    ) -> Tuple[bool, int]:
        """
        验证补丁大小

        Args:
            patch: unified diff 格式的补丁
            max_lines: 最大修改行数

        Returns:
            (是否有效, 修改行数)
        """
        if not patch:
            return True, 0

        # 统计修改的行数（只计算实际变化的行数，不重复计算替换）
        added_count = 0
        removed_count = 0

        for line in patch.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                added_count += 1
            elif line.startswith('-') and not line.startswith('---'):
                removed_count += 1

        # 修改行数 = max(添加的行数, 删除的行数)
        # 这代表实际修改的范围
        modified_count = max(added_count, removed_count)

        is_valid = modified_count <= max_lines

        return is_valid, modified_count

    def validate_syntax(
        self,
        code: str,
        language: str = 'python'
    ) -> Tuple[bool, Optional[str]]:
        """
        验证代码语法

        Args:
            code: 代码内容
            language: 编程语言

        Returns:
            (是否有效, 错误信息)
        """
        if language == 'python':
            try:
                ast.parse(code)
                return True, None
            except SyntaxError as e:
                return False, str(e)
            except Exception as e:
                return False, str(e)
        else:
            # 其他语言暂不支持
            return True, None

    # ========================================================================
    # 内部辅助方法
    # ========================================================================

    def _call_llm(
        self,
        context: Dict[str, Any],
        root_cause: Dict[str, Any],
        error_info: Dict[str, Any]
    ) -> str:
        """
        调用 LLM 生成修复代码

        这个方法在实际使用中会调用 Anthropic API，
        在测试中会被 mock

        Args:
            context: 代码上下文
            root_cause: 根因信息
            error_info: 错误信息

        Returns:
            修复后的代码
        """
        # 实际实现会调用 LLM API
        # 这里抛出异常，因为在测试中会被 mock
        raise NotImplementedError("This method should be mocked in tests")

    def _call_llm_multiple(
        self,
        context: Dict[str, Any],
        root_cause: Dict[str, Any],
        error_info: Dict[str, Any],
        n: int
    ) -> List[Dict[str, Any]]:
        """
        调用 LLM 生成多个候选修复

        Args:
            context: 代码上下文
            root_cause: 根因信息
            error_info: 错误信息
            n: 候选数量

        Returns:
            候选列表，每个候选包含 code 和 confidence
        """
        # 实际实现会调用 LLM API
        # 这里抛出异常，因为在测试中会被 mock
        raise NotImplementedError("This method should be mocked in tests")

    def _extract_original_code(self, context: Dict[str, Any]) -> str:
        """
        从上下文中提取原始代码

        Args:
            context: 代码上下文

        Returns:
            原始代码字符串
        """
        # 尝试从文件路径读取
        file_path = context.get('file_path', '')
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass

        # 否则从上下文字符串中提取
        context_str = context.get('context', '')
        if context_str:
            # 解析上下文格式（带行号的格式）
            lines = []
            for line in context_str.split('\n'):
                # 跳过注释行
                if line.strip().startswith('#'):
                    continue
                # 提取代码内容（去除行号）
                if '|' in line:
                    code_part = line.split('|', 1)[1] if '|' in line else line
                    lines.append(code_part)
                else:
                    lines.append(line)

            return '\n'.join(lines)

        return ''

    def _extract_modified_lines(self, unified_diff: str) -> List[int]:
        """
        从 unified diff 中提取修改的行号

        Args:
            unified_diff: unified diff 字符串

        Returns:
            修改的行号列表
        """
        modified_lines = []

        for line in unified_diff.split('\n'):
            # 查找 @@ -x,y +a,b @@ 格式的行
            if line.startswith('@@'):
                # 提取 +a,b 部分
                parts = line.split('@@')
                if len(parts) >= 2:
                    range_info = parts[1].strip()
                    # 解析 -x,y +a,b
                    if '+' in range_info:
                        plus_part = range_info.split('+')[1].strip()
                        if ',' in plus_part:
                            start_line = int(plus_part.split(',')[0])
                            count = int(plus_part.split(',')[1].split()[0])
                        else:
                            start_line = int(plus_part.split()[0])
                            count = 1

                        # 添加修改的行号范围
                        for i in range(start_line, start_line + count):
                            modified_lines.append(i)

        return sorted(list(set(modified_lines)))

    def _generate_description(
        self,
        root_cause: Dict[str, Any],
        error_info: Dict[str, Any]
    ) -> str:
        """
        生成补丁描述

        Args:
            root_cause: 根因信息
            error_info: 错误信息

        Returns:
            描述字符串
        """
        error_type = error_info.get('error_type', 'Error')
        root_cause_desc = root_cause.get('description', 'Unknown issue')

        return f"Fix {error_type}: {root_cause_desc}"

    def _calculate_confidence(
        self,
        context: Dict[str, Any],
        modified_code: str
    ) -> float:
        """
        计算补丁的置信度

        考虑因素：
        - 上下文的完整性
        - 修改后的代码是否语法正确
        - 修改的范围大小

        Args:
            context: 代码上下文
            modified_code: 修改后的代码

        Returns:
            置信度（0.0-1.0）
        """
        confidence = 0.5  # 基础置信度

        # 1. 检查上下文完整性
        if context.get('context'):
            confidence += 0.1
        if context.get('imports'):
            confidence += 0.05
        if context.get('related_symbols'):
            confidence += 0.05

        # 2. 检查语法正确性
        is_valid, _ = self.validate_syntax(modified_code)
        if is_valid:
            confidence += 0.2
        else:
            confidence -= 0.3

        # 3. 检查是否有修改（避免无效补丁）
        original = self._extract_original_code(context)
        if original and original != modified_code:
            confidence += 0.1

        # 确保在 0.0-1.0 范围内
        confidence = max(0.0, min(1.0, confidence))

        return confidence
