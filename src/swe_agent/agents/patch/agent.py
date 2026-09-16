"""
PatchGeneratorAgent - 补丁生成代理
Task 5.4: PatchGeneratorAgent 实现与集成测试

集成所有 patch 模块，完成补丁生成的完整流程：
1. 构建代码上下文（ContextBuilder）
2. 生成多个候选补丁（PatchGenerator）
3. 验证补丁语法（SyntaxValidator）
4. 排序并返回最优补丁
"""
import time
from typing import Dict, List, Any, Optional

from .context_builder import ContextBuilder
from .generator import PatchGenerator
from .validator import SyntaxValidator


class PatchGeneratorAgent:
    """补丁生成代理，协调所有补丁生成流程"""

    def __init__(
        self,
        localization_result: Dict[str, Any],
        reproduction_result: Dict[str, Any],
        repo_context: Dict[str, Any]
    ):
        """
        初始化 PatchGeneratorAgent

        Args:
            localization_result: 定位阶段的结果，包含候选文件列表
            reproduction_result: 复现阶段的结果，包含根因和错误信息
            repo_context: 仓库上下文信息
        """
        self.localization_result = localization_result
        self.reproduction_result = reproduction_result
        self.repo_context = repo_context

        # 初始化组件
        self.context_builder = ContextBuilder()
        self.patch_generator = PatchGenerator()
        self.syntax_validator = SyntaxValidator()

    def run(self) -> Dict[str, Any]:
        """
        执行补丁生成流程

        Returns:
            PatchResult 字典，包含：
            - status: "generated" | "failed"
            - patches: 补丁列表（按置信度排序）
            - best_patch: 最优补丁（第一个）
            - generation_strategy: "beam_search"
            - execution_time: 执行时间（秒）
        """
        start_time = time.time()

        try:
            # 获取候选文件列表
            candidates = self.localization_result.get('candidates', [])

            if not candidates:
                return self._create_failed_result(start_time, "No candidates found")

            # 为每个候选文件生成补丁
            all_patches = []

            for candidate in candidates:
                file_path = candidate.get('file_path')
                focus_lines = candidate.get('lines', [])

                if not file_path:
                    continue

                try:
                    # 1. 构建代码上下文
                    context = self._build_context(file_path, focus_lines)

                    # 2. 生成多个候选补丁
                    patches = self._generate_patches(context)

                    # 3. 验证补丁
                    valid_patches = self._validate_patches(patches)

                    # 收集所有有效补丁
                    all_patches.extend(valid_patches)

                except Exception as e:
                    # 单个候选文件失败不影响其他候选
                    continue

            # 4. 排序所有补丁
            ranked_patches = self._rank_patches(all_patches)

            # 5. 构建结果
            if ranked_patches:
                execution_time = time.time() - start_time
                return {
                    'status': 'generated',
                    'patches': ranked_patches,
                    'best_patch': ranked_patches[0],
                    'generation_strategy': 'beam_search',
                    'execution_time': execution_time
                }
            else:
                return self._create_failed_result(start_time, "No valid patches generated")

        except Exception as e:
            return self._create_failed_result(start_time, str(e))

    def _build_context(self, file_path: str, focus_lines: List[int]) -> Dict[str, Any]:
        """
        构建代码上下文

        Args:
            file_path: 文件路径
            focus_lines: 焦点行号列表

        Returns:
            上下文字典
        """
        return self.context_builder.build_context(file_path, focus_lines)

    def _generate_patches(self, context: Dict[str, Any], n: int = 3) -> List[Dict[str, Any]]:
        """
        生成多个候选补丁

        Args:
            context: 代码上下文
            n: 生成的补丁数量

        Returns:
            补丁列表
        """
        root_cause = self.reproduction_result.get('root_cause', {})
        error_info = self.reproduction_result.get('error_details', {})

        return self.patch_generator.generate_multiple_patches(
            context,
            root_cause,
            error_info,
            n=n
        )

    def _validate_patches(self, patches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        验证补丁语法

        Args:
            patches: 补丁列表

        Returns:
            有效的补丁列表（添加了 validation 字段）
        """
        if not patches:
            return []

        valid_patches = []

        for patch in patches:
            file_path = patch.get('file_path')
            unified_diff = patch.get('unified_diff', '')

            # 调用 SyntaxValidator 验证
            validation_result = self.syntax_validator.validate_patch_application(
                file_path,
                unified_diff
            )

            # 添加验证结果到补丁
            patch_with_validation = {
                **patch,
                'validation': validation_result
            }

            # 只保留有效的补丁
            if validation_result.get('is_valid', False):
                valid_patches.append(patch_with_validation)

        return valid_patches

    def _rank_patches(self, patches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        按置信度排序补丁

        Args:
            patches: 补丁列表

        Returns:
            排序后的补丁列表（置信度降序）
        """
        return sorted(patches, key=lambda p: p.get('confidence', 0.0), reverse=True)

    def _create_failed_result(self, start_time: float, reason: str) -> Dict[str, Any]:
        """
        创建失败结果

        Args:
            start_time: 开始时间
            reason: 失败原因

        Returns:
            失败的 PatchResult
        """
        execution_time = time.time() - start_time
        return {
            'status': 'failed',
            'patches': [],
            'best_patch': None,
            'generation_strategy': 'beam_search',
            'execution_time': execution_time
        }
