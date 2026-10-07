"""
Unit tests for Grounded Prompt Builder (Phase 3).
Verifies strict grounding rules, hallucination prevention instructions, and prompt formatting.
"""

import pytest
from svant.core.rag.prompt import GroundedPromptBuilder


def test_system_prompt_contains_grounding_rules():
    builder = GroundedPromptBuilder()
    sys_prompt = builder.build_system_prompt(project_name="MyProject")

    assert "SVANT" in sys_prompt
    assert "CRITICAL RULES" in sys_prompt
    assert "ONLY answer using facts" in sys_prompt
    assert "DO NOT invent" in sys_prompt
    assert "MyProject" in sys_prompt


def test_user_prompt_formatting():
    builder = GroundedPromptBuilder()
    evidence = "--- [Source 1: config.py (Lines 1-5)] ---\nPORT = 8080"
    user_prompt = builder.build_user_prompt("What port is configured?", evidence)

    assert "PROJECT EVIDENCE:" in user_prompt
    assert "PORT = 8080" in user_prompt
    assert "DEVELOPER QUESTION:" in user_prompt
    assert "What port is configured?" in user_prompt
