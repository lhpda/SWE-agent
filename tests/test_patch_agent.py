"""
Tests for PatchGeneratorAgent
Task 5.4: PatchGeneratorAgent 实现与集成测试
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import time
from src.swe_agent.agents.patch.agent import PatchGeneratorAgent


class TestPatchGeneratorAgentInit:
    """测试 PatchGeneratorAgent 初始化"""

    def test_init_with_valid_inputs(self):
        """测试：使用有效输入初始化"""
        localization_result = {
            "status": "success",
            "candidates": [{"file_path": "/path/to/file.py", "confidence": 0.9}],
        }
        reproduction_result = {
            "status": "reproduced",
            "root_cause": {"description": "Bug in function"},
            "error_details": {"error_type": "AttributeError"},
        }
        repo_context = {"path": "/repo/path", "project_type": "python"}

        agent = PatchGeneratorAgent(localization_result, reproduction_result, repo_context)

        assert agent.localization_result == localization_result
        assert agent.reproduction_result == reproduction_result
        assert agent.repo_context == repo_context

    def test_init_stores_components(self):
        """测试：初始化时创建必要的组件"""
        agent = PatchGeneratorAgent({}, {}, {})

        # 验证组件已创建
        assert hasattr(agent, "context_builder")
        assert hasattr(agent, "patch_generator")
        assert hasattr(agent, "syntax_validator")


class TestPatchGeneratorAgentBuildContext:
    def test_build_context_calls_context_builder(self, tmp_path):
        source = tmp_path / "file.py"
        source.write_text("value = 1\n", encoding="utf-8")
        agent = PatchGeneratorAgent({}, {}, {"path": str(tmp_path)})
        result = agent._build_context("file.py", [1])
        assert result["original_code"] == "value = 1\n"
        assert result["file_path"] == str(source.resolve())

    def test_build_context_handles_empty_focus_lines(self, tmp_path):
        source = tmp_path / "file.py"
        source.write_text("value = 1\n", encoding="utf-8")
        agent = PatchGeneratorAgent({}, {}, {"path": str(tmp_path)})
        result = agent._build_context("file.py", [])
        assert result["original_code"] == "value = 1\n"
        assert result["focus_lines"] == [1]


class TestPatchGeneratorAgentGeneratePatches:
    """测试 _generate_patches 方法"""

    def test_generate_patches_calls_generator(self):
        """测试：调用 PatchGenerator.generate_multiple_patches"""
        reproduction_result = {
            "root_cause": {"description": "Bug"},
            "error_details": {"error_type": "ValueError"},
        }

        agent = PatchGeneratorAgent({}, reproduction_result, {})

        # Mock PatchGenerator
        mock_patches = [
            {"patch_id": "1", "confidence": 0.9},
            {"patch_id": "2", "confidence": 0.8},
            {"patch_id": "3", "confidence": 0.7},
        ]
        agent.patch_generator.generate_multiple_patches = Mock(return_value=mock_patches)

        context = {"file_path": "/path/to/file.py"}
        result = agent._generate_patches(context)

        agent.patch_generator.generate_multiple_patches.assert_called_once_with(
            context, {"description": "Bug"}, {"error_type": "ValueError"}, n=3
        )
        assert result == mock_patches

    def test_generate_patches_with_custom_count(self):
        """测试：生成自定义数量的补丁"""
        reproduction_result = {"root_cause": {}, "error_details": {}}

        agent = PatchGeneratorAgent({}, reproduction_result, {})
        agent.patch_generator.generate_multiple_patches = Mock(return_value=[])

        agent._generate_patches({}, n=5)

        agent.patch_generator.generate_multiple_patches.assert_called_once()
        call_args = agent.patch_generator.generate_multiple_patches.call_args
        assert call_args[1]["n"] == 5


class TestPatchGeneratorAgentValidatePatches:
    """测试 _validate_patches 方法"""

    def test_validate_patches_calls_validator(self):
        """测试：调用 SyntaxValidator 验证每个补丁"""
        agent = PatchGeneratorAgent({}, {}, {})

        patches = [
            {"patch_id": "1", "file_path": "/path/file.py", "unified_diff": "diff1"},
            {"patch_id": "2", "file_path": "/path/file.py", "unified_diff": "diff2"},
        ]

        # Mock validator
        agent.syntax_validator.validate_patch_application = Mock(
            return_value={"is_valid": True, "errors": []}
        )

        result = agent._validate_patches(patches)

        # 验证调用次数
        assert agent.syntax_validator.validate_patch_application.call_count == 2
        assert len(result) == 2
        assert result[0]["validation"] == {"is_valid": True, "errors": []}

    def test_validate_patches_filters_invalid(self):
        """测试：过滤掉无效的补丁"""
        agent = PatchGeneratorAgent({}, {}, {})

        patches = [
            {"patch_id": "1", "file_path": "/path/file.py", "unified_diff": "diff1"},
            {"patch_id": "2", "file_path": "/path/file.py", "unified_diff": "diff2"},
            {"patch_id": "3", "file_path": "/path/file.py", "unified_diff": "diff3"},
        ]

        # Mock validator: 第2个补丁无效
        def mock_validate(file_path, patch):
            if "diff2" in patch:
                return {"is_valid": False, "errors": ["Syntax error"]}
            return {"is_valid": True, "errors": []}

        agent.syntax_validator.validate_patch_application = Mock(side_effect=mock_validate)

        result = agent._validate_patches(patches)

        # 只返回有效的补丁
        assert len(result) == 2
        assert result[0]["patch_id"] == "1"
        assert result[1]["patch_id"] == "3"

    def test_validate_patches_handles_empty_list(self):
        """测试：处理空补丁列表"""
        agent = PatchGeneratorAgent({}, {}, {})

        result = agent._validate_patches([])

        assert result == []


class TestPatchGeneratorAgentRankPatches:
    """测试 _rank_patches 方法"""

    def test_rank_patches_sorts_by_confidence(self):
        """测试：按置信度降序排列"""
        agent = PatchGeneratorAgent({}, {}, {})

        patches = [
            {"patch_id": "1", "confidence": 0.7},
            {"patch_id": "2", "confidence": 0.9},
            {"patch_id": "3", "confidence": 0.5},
        ]

        result = agent._rank_patches(patches)

        assert len(result) == 3
        assert result[0]["patch_id"] == "2"  # 0.9
        assert result[1]["patch_id"] == "1"  # 0.7
        assert result[2]["patch_id"] == "3"  # 0.5

    def test_rank_patches_handles_equal_confidence(self):
        """测试：处理相同置信度的补丁"""
        agent = PatchGeneratorAgent({}, {}, {})

        patches = [
            {"patch_id": "1", "confidence": 0.8},
            {"patch_id": "2", "confidence": 0.8},
            {"patch_id": "3", "confidence": 0.8},
        ]

        result = agent._rank_patches(patches)

        # 相同置信度保持顺序
        assert len(result) == 3
        for patch in result:
            assert patch["confidence"] == 0.8


class TestPatchGeneratorAgentRun:
    """测试 run 方法（主流程）"""

    def test_run_success_single_candidate(self):
        """测试：成功生成补丁（单个候选文件）"""
        localization_result = {
            "candidates": [{"file_path": "/path/to/file.py", "lines": [10, 20], "confidence": 0.9}]
        }
        reproduction_result = {
            "root_cause": {"description": "Bug"},
            "error_details": {"error_type": "ValueError"},
        }

        agent = PatchGeneratorAgent(localization_result, reproduction_result, {})

        # Mock all components
        mock_context = {"file_path": "/path/to/file.py", "context": "code"}
        agent._build_context = Mock(return_value=mock_context)

        mock_patches = [
            {
                "patch_id": "1",
                "confidence": 0.9,
                "file_path": "/path/to/file.py",
                "unified_diff": "diff",
            },
            {
                "patch_id": "2",
                "confidence": 0.8,
                "file_path": "/path/to/file.py",
                "unified_diff": "diff",
            },
        ]
        agent._generate_patches = Mock(return_value=mock_patches)

        validated_patches = [
            {**mock_patches[0], "validation": {"is_valid": True}},
            {**mock_patches[1], "validation": {"is_valid": True}},
        ]
        agent._validate_patches = Mock(return_value=validated_patches)
        agent._rank_patches = Mock(return_value=validated_patches)

        result = agent.run()

        # 验证结果
        assert result["status"] == "generated"
        assert len(result["patches"]) == 2
        assert result["best_patch"] == validated_patches[0]
        assert result["generation_strategy"] == "beam_search"
        assert "execution_time" in result
        assert result["execution_time"] >= 0

    def test_run_success_multiple_candidates(self):
        """测试：成功生成补丁（多个候选文件）"""
        localization_result = {
            "candidates": [
                {"file_path": "/path/file1.py", "lines": [10], "confidence": 0.9},
                {"file_path": "/path/file2.py", "lines": [20], "confidence": 0.8},
            ]
        }
        reproduction_result = {"root_cause": {}, "error_details": {}}

        agent = PatchGeneratorAgent(localization_result, reproduction_result, {})

        # Mock components
        agent._build_context = Mock(return_value={})
        agent._generate_patches = Mock(return_value=[{"patch_id": "1", "confidence": 0.9}])
        agent._validate_patches = Mock(
            return_value=[{"patch_id": "1", "confidence": 0.9, "validation": {"is_valid": True}}]
        )
        agent._rank_patches = Mock(side_effect=lambda x: x)

        result = agent.run()

        # 验证为每个候选文件生成了补丁
        assert agent._build_context.call_count == 2
        assert agent._generate_patches.call_count == 2

    def test_run_partial_success(self):
        """测试：部分成功（有些补丁验证失败）"""
        localization_result = {"candidates": [{"file_path": "/path/file.py", "lines": [10]}]}
        reproduction_result = {"root_cause": {}, "error_details": {}}

        agent = PatchGeneratorAgent(localization_result, reproduction_result, {})

        agent._build_context = Mock(return_value={})
        agent._generate_patches = Mock(
            return_value=[
                {"patch_id": "1", "confidence": 0.9},
                {"patch_id": "2", "confidence": 0.8},
            ]
        )
        # 验证后只有1个有效
        agent._validate_patches = Mock(
            return_value=[{"patch_id": "1", "confidence": 0.9, "validation": {"is_valid": True}}]
        )
        agent._rank_patches = Mock(side_effect=lambda x: x)

        result = agent.run()

        assert result["status"] == "generated"
        assert len(result["patches"]) == 1

    def test_run_failed_no_valid_patches(self):
        """测试：失败（没有有效的补丁）"""
        localization_result = {"candidates": [{"file_path": "/path/file.py", "lines": [10]}]}
        reproduction_result = {"root_cause": {}, "error_details": {}}

        agent = PatchGeneratorAgent(localization_result, reproduction_result, {})

        agent._build_context = Mock(return_value={})
        agent._generate_patches = Mock(return_value=[])
        agent._validate_patches = Mock(return_value=[])
        agent._rank_patches = Mock(return_value=[])

        result = agent.run()

        assert result["status"] == "failed"
        assert result["patches"] == []
        assert result["best_patch"] is None

    def test_run_handles_exceptions(self):
        """测试：处理异常"""
        localization_result = {"candidates": [{"file_path": "/path/file.py", "lines": [10]}]}

        agent = PatchGeneratorAgent(localization_result, {}, {})

        # Mock 抛出异常
        agent._build_context = Mock(side_effect=Exception("Build failed"))

        result = agent.run()

        assert result["status"] == "failed"
        assert result["patches"] == []

    def test_run_tracks_execution_time(self):
        """测试：跟踪执行时间"""
        localization_result = {"candidates": [{"file_path": "/path/file.py", "lines": [10]}]}

        agent = PatchGeneratorAgent(localization_result, {}, {})

        def slow_build(*args, **kwargs):
            time.sleep(0.1)
            return {}

        agent._build_context = Mock(side_effect=slow_build)
        agent._generate_patches = Mock(return_value=[])
        agent._validate_patches = Mock(return_value=[])
        agent._rank_patches = Mock(return_value=[])

        result = agent.run()

        assert result["execution_time"] >= 0.1

    def test_run_returns_best_patch(self):
        """测试：返回最优补丁"""
        localization_result = {"candidates": [{"file_path": "/path/file.py", "lines": [10]}]}

        agent = PatchGeneratorAgent(localization_result, {}, {})

        agent._build_context = Mock(return_value={})
        patches = [{"patch_id": "1", "confidence": 0.9}, {"patch_id": "2", "confidence": 0.7}]
        agent._generate_patches = Mock(return_value=patches)
        agent._validate_patches = Mock(side_effect=lambda x: x)
        agent._rank_patches = Mock(
            side_effect=lambda x: sorted(x, key=lambda p: p["confidence"], reverse=True)
        )

        result = agent.run()

        assert result["best_patch"]["patch_id"] == "1"
        assert result["best_patch"]["confidence"] == 0.9


class TestPatchGeneratorAgentIntegration:
    """集成测试"""

    def test_full_workflow_integration(self):
        """测试：完整的工作流程集成"""
        localization_result = {
            "candidates": [{"file_path": "/path/file.py", "lines": [10], "confidence": 0.9}]
        }
        reproduction_result = {
            "root_cause": {"description": "AttributeError"},
            "error_details": {"error_type": "AttributeError", "message": "Error"},
        }
        repo_context = {"path": "/repo", "project_type": "python"}

        agent = PatchGeneratorAgent(localization_result, reproduction_result, repo_context)

        # Mock 所有外部依赖
        agent._build_context = Mock(
            return_value={"file_path": "/path/file.py", "context": "code here"}
        )
        agent._generate_patches = Mock(
            return_value=[
                {
                    "patch_id": "1",
                    "confidence": 0.9,
                    "file_path": "/path/file.py",
                    "unified_diff": "diff",
                },
                {
                    "patch_id": "2",
                    "confidence": 0.8,
                    "file_path": "/path/file.py",
                    "unified_diff": "diff",
                },
            ]
        )
        agent._validate_patches = Mock(side_effect=lambda x: x)
        agent._rank_patches = Mock(
            side_effect=lambda x: sorted(x, key=lambda p: p["confidence"], reverse=True)
        )

        result = agent.run()

        # 验证完整流程
        assert result["status"] == "generated"
        assert len(result["patches"]) == 2
        assert result["best_patch"]["patch_id"] == "1"
        assert result["generation_strategy"] == "beam_search"
        assert result["execution_time"] >= 0
