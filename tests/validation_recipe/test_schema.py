"""Tests for the Validation Recipe schema — Issue #18.

Covers:
    1. Valid recipes (minimal, multi-scope, multi-step, JSON roundtrip)
    2. Required field validation (missing ID/name/version/scope/steps)
    3. Forbidden field detection (recursive, nested, case-insensitive)
    4. Target safety (localhost OK, public IP → FAIL, domain → FAIL)
    5. Scope reference rules (format, wildcard, step in recipe)
    6. Non-destructive classification (destructive=true, missing safety)
    7. Fail-closed behavior (unknown step types, unknown fields)
    8. Step-type-specific semantics (HTTP methods, TCP data, evidence URLs)
    9. Deterministic behavior (same input → same output)
    10. Safety imports check (no network/shell/execution imports)
"""

from __future__ import annotations

import ast
import json

import pytest

from neutrino.validation_recipe import (
    ValidationReasonCode,
    ValidationRecipe,
    ValidationStep,
    ValidationStepType,
    export_json_schema,
    validate_recipe,
)
from neutrino.validation_recipe.models import MAX_STEPS


# ==================================================================
# Test Fixtures
# ==================================================================


def _valid_recipe_dict() -> dict:
    """Minimal valid recipe as a dict."""
    return {
        "id": "recipe-001",
        "name": "Basic Lab Check",
        "version": "1.0",
        "description": "A minimal safe validation recipe.",
        "scope_references": ["scope:local-lab/demo-app"],
        "steps": [
            {
                "id": "step-001",
                "name": "Check HTTP endpoint",
                "step_type": "http_check",
                "target": "http://localhost:8080",
                "scope_reference": "scope:local-lab/demo-app",
                "requires_approval": True,
                "expected_evidence": ["ev-http-001"],
            }
        ],
        "created_at": "2026-07-09T00:00:00Z",
    }


def _valid_multi_step_recipe() -> dict:
    """Valid recipe with multiple steps and multiple scope references."""
    return {
        "id": "recipe-002",
        "name": "Multi-Step Lab Check",
        "version": "1.0",
        "description": "Multiple validation steps.",
        "scope_references": [
            "scope:local-lab/demo-app",
            "program:demo#target:api-local",
        ],
        "steps": [
            {
                "id": "step-001",
                "name": "HTTP Check",
                "step_type": "http_check",
                "target": "http://localhost:8080",
                "scope_reference": "scope:local-lab/demo-app",
                "requires_approval": True,
                "expected_evidence": ["ev-http-001"],
            },
            {
                "id": "step-002",
                "name": "TCP Check",
                "step_type": "tcp_check",
                "target": "127.0.0.1",
                "scope_reference": "scope:local-lab/demo-app",
                "requires_approval": True,
                "expected_evidence": ["ev-tcp-001"],
            },
            {
                "id": "step-003",
                "name": "Evidence Check",
                "step_type": "evidence_check",
                "target": "fixture:ev-bundle-1",
                "scope_reference": "scope:local-lab/demo-app",
                "requires_approval": False,
                "expected_evidence": ["ev-check-001"],
            },
        ],
        "created_at": "2026-07-09T00:00:00Z",
    }


# ==================================================================
# 1. Valid Recipes
# ==================================================================


class TestValidRecipes:
    """Test cases for valid (should pass) recipes."""

    def test_minimal_valid_recipe(self):
        """Minimal valid recipe passes validation."""
        result = validate_recipe(_valid_recipe_dict())
        assert result.valid is True
        assert len(result.errors) == 0
        assert ValidationReasonCode.VALID_RECIPE in result.reasons

    def test_recipe_with_multiple_scope_references(self):
        """Recipe with multiple scope references is valid."""
        result = validate_recipe(_valid_multi_step_recipe())
        assert result.valid is True

    def test_recipe_with_multiple_structured_steps(self):
        """Recipe with multiple structured steps is valid."""
        result = validate_recipe(_valid_multi_step_recipe())
        assert result.valid is True

    def test_step_http_check_declaratively_valid(self):
        """Step with http_check is declaratively valid."""
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["step_type"] = "http_check"
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_step_manual_observation_valid(self):
        """Step with manual_observation is valid."""
        recipe = _valid_recipe_dict()
        recipe["steps"][0] = {
            "id": "step-obs",
            "name": "Manual observation",
            "step_type": "manual_observation",
            "target": "fixture:obs-target",
            "scope_reference": "scope:local-lab/demo-app",
            "requires_approval": False,
            "expected_evidence": ["ev-obs-001"],
        }
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_step_local_fixture_check_valid(self):
        """Step with local_fixture_check is valid."""
        recipe = _valid_recipe_dict()
        recipe["steps"][0] = {
            "id": "step-fix",
            "name": "Fixture check",
            "step_type": "local_fixture_check",
            "target": "fixture:demo-fixture",
            "scope_reference": "scope:local-lab/demo-app",
            "requires_approval": False,
            "expected_evidence": ["ev-fix-001"],
        }
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_javascript_roundtrip_works(self):
        """JSON serialization roundtrip preserves validity."""
        recipe = _valid_recipe_dict()
        dumped = json.dumps(recipe)
        loaded = json.loads(dumped)
        result = validate_recipe(loaded)
        assert result.valid is True

    def test_json_schema_export_works(self):
        """export_json_schema returns a valid dict."""
        schema = export_json_schema()
        assert isinstance(schema, dict)
        assert "$schema" in schema
        assert "properties" in schema
        assert "required" in schema

    def test_validation_recipe_model_construction(self):
        """ValidationRecipe can be constructed directly from dict."""
        recipe = ValidationRecipe(**_valid_recipe_dict())
        assert recipe.id == "recipe-001"
        assert len(recipe.steps) == 1

    def test_validation_step_model_construction(self):
        """ValidationStep can be constructed directly."""
        step = ValidationStep(
            id="s1",
            name="test",
            step_type=ValidationStepType.MANUAL_OBSERVATION,
            target="fixture:test",
            scope_reference="scope:lab/test",
            requires_approval=False,
            expected_evidence=["ev1"],
        )
        assert step.id == "s1"

    def test_recipe_with_optional_fields(self):
        """Recipe with all optional fields populated is valid."""
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["description"] = "Optional description"
        recipe["steps"][0]["parameters"] = {"method": "GET"}
        recipe["steps"][0]["timeout_seconds"] = 30
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_validation_result_id_extracted(self):
        """ValidationResult contains the recipe_id."""
        result = validate_recipe(_valid_recipe_dict())
        assert result.recipe_id == "recipe-001"


# ==================================================================
# 2. Required Field Validation
# ==================================================================


class TestRequiredFields:
    """Test cases for missing required fields."""

    def test_missing_recipe_id_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["id"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_missing_name_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["name"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_missing_version_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["version"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_missing_scope_references_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["scope_references"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_empty_steps_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"] = []
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_step_without_id_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["steps"][0]["id"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_step_without_target_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["steps"][0]["target"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_step_without_scope_reference_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["steps"][0]["scope_reference"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_step_without_expected_evidence_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["steps"][0]["expected_evidence"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_empty_recipe_id_fails(self):
        recipe = _valid_recipe_dict()
        recipe["id"] = ""
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_empty_recipe_name_fails(self):
        recipe = _valid_recipe_dict()
        recipe["name"] = ""
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_empty_scope_references_list_fails(self):
        recipe = _valid_recipe_dict()
        recipe["scope_references"] = []
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_empty_step_name_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["name"] = ""
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_empty_expected_evidence_list_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["expected_evidence"] = []
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_empty_evidence_entry_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["expected_evidence"] = ["ok", ""]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_missing_description_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["description"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_missing_created_at_fails(self):
        recipe = _valid_recipe_dict()
        del recipe["created_at"]
        result = validate_recipe(recipe)
        assert result.valid is False


# ==================================================================
# 3. Forbidden Fields (Recursive, Nested)
# ==================================================================


class TestForbiddenFields:
    """Test cases for forbidden field detection."""

    # --- Top-level forbidden fields ---

    @pytest.mark.parametrize(
        "field",
        [
            "command",
            "shell",
            "cmd",
            "bash",
            "powershell",
            "exec",
            "subprocess",
            "script",
            "exploit",
            "scanner",
            "raw_request",
        ],
    )
    def test_top_level_forbidden_field_fails(self, field):
        recipe = _valid_recipe_dict()
        recipe[field] = "dangerous"
        result = validate_recipe(recipe)
        assert result.valid is False
        assert ValidationReasonCode.INVALID_FORBIDDEN_FIELD in result.reasons

    # --- Nested forbidden fields in parameters ---

    def test_nested_command_in_parameters_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"command": "rm -rf /"}
        result = validate_recipe(recipe)
        assert result.valid is False
        assert ValidationReasonCode.INVALID_FORBIDDEN_FIELD in result.reasons

    def test_nested_shell_in_parameters_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"shell": "/bin/sh"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_nested_payload_in_parameters_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"payload": "<script>alert(1)</script>"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_deeply_nested_script_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"metadata": {"inner": {"script": "dangerous.sh"}}}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_forbidden_field_in_step_parameters_list(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"items": [{"exec": "bad"}]}
        result = validate_recipe(recipe)
        assert result.valid is False

    # --- Case-insensitive detection ---

    def test_mixed_case_command_fails(self):
        recipe = _valid_recipe_dict()
        recipe["CoMmAnD"] = "bad"
        result = validate_recipe(recipe)
        assert result.valid is False

    # --- Additional forbidden aliases ---

    def test_execute_field_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"execute": "bad"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_pickle_field_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"pickle": "data"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_eval_field_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"eval": "1+1"}
        result = validate_recipe(recipe)
        assert result.valid is False


# ==================================================================
# 4. Target Safety
# ==================================================================


class TestTargetSafety:
    """Test cases for target validation."""

    def test_localhost_target_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "localhost"
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_127_0_0_1_target_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "127.0.0.1"
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_ipv6_localhost_target_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "::1"
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_http_localhost_target_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "http://localhost:8080"
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_https_loopback_target_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "https://127.0.0.1:8443"
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_fixture_target_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "fixture:my-fixture"
        assert validate_recipe(recipe).valid is True

    def test_lab_target_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "lab:demo-app"
        assert validate_recipe(recipe).valid is True

    def test_scope_placeholder_target_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "{scope:local-lab/demo-app#target:api}"
        assert validate_recipe(recipe).valid is True

    def test_lab_hostname_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "lab-demo.local"
        # Note: lab- prefix hostnames are valid
        recipe["steps"][0]["target"] = "lab-demo-app"
        assert validate_recipe(recipe).valid is True

    # --- Invalid targets ---

    def test_public_domain_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "https://example.com"
        result = validate_recipe(recipe)
        assert result.valid is False
        assert ValidationReasonCode.INVALID_EXTERNAL_TARGET in result.reasons

    def test_public_ip_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "8.8.8.8"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_private_ip_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "192.168.1.1"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_private_ip_10_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "10.0.0.1"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_wildcard_target_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "*.example.com"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_zero_ip_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "0.0.0.0"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_unsafe_scheme_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "ftp://localhost"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_unknown_target_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = "some-random-string"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_empty_target_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["target"] = ""
        result = validate_recipe(recipe)
        assert result.valid is False


# ==================================================================
# 5. Scope Reference Rules
# ==================================================================


class TestScopeRules:
    """Test cases for scope reference validation."""

    def test_step_scope_in_recipe_scope_valid(self):
        result = validate_recipe(_valid_recipe_dict())
        assert result.valid is True

    def test_step_scope_not_in_recipe_scope_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["scope_reference"] = "scope:other/program"
        result = validate_recipe(recipe)
        assert result.valid is False
        assert ValidationReasonCode.INVALID_STEP_SCOPE_NOT_IN_RECIPE in result.reasons

    def test_empty_scope_reference_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["scope_reference"] = ""
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_wildcard_scope_star_fails(self):
        recipe = _valid_recipe_dict()
        recipe["scope_references"] = ["*"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_wildcard_scope_all_fails(self):
        recipe = _valid_recipe_dict()
        recipe["scope_references"] = ["all"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_unknown_scope_format_fails(self):
        recipe = _valid_recipe_dict()
        recipe["scope_references"] = ["random-string-not-a-scope"]
        result = validate_recipe(recipe)
        assert result.valid is False
        assert ValidationReasonCode.INVALID_SCOPE_FORMAT in result.reasons

    def test_multiple_valid_scopes_work(self):
        recipe = _valid_multi_step_recipe()
        recipe["steps"][0]["scope_reference"] = "scope:local-lab/demo-app"
        recipe["steps"][1]["scope_reference"] = "scope:local-lab/demo-app"
        recipe["steps"][2]["scope_reference"] = "scope:local-lab/demo-app"
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_broad_scope_star_in_scope_fails(self):
        recipe = _valid_recipe_dict()
        recipe["scope_references"] = ["scope:*"]
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_default_scope_fails(self):
        recipe = _valid_recipe_dict()
        recipe["scope_references"] = ["default"]
        result = validate_recipe(recipe)
        assert result.valid is False


# ==================================================================
# 6. Non-Destructive Classification
# ==================================================================


class TestNonDestructive:
    """Test cases for non-destructive enforcement."""

    def test_destructive_true_fails(self):
        recipe = _valid_recipe_dict()
        recipe["destructive"] = True
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_step_destructive_true_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["destructive"] = True
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_non_destructive_safety_class_valid(self):
        recipe = _valid_recipe_dict()
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_unknown_safety_class_fails(self):
        recipe = _valid_recipe_dict()
        recipe["safety_class"] = "unknown"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_missing_safety_class_defaults_non_destructive(self):
        """safety_class defaults to non_destructive — recipe should pass."""
        recipe = _valid_recipe_dict()
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_explicit_non_destructive_passes(self):
        recipe = _valid_recipe_dict()
        recipe["safety_class"] = "non_destructive"
        result = validate_recipe(recipe)
        assert result.valid is True


# ==================================================================
# 7. Fail-Closed / Safety
# ==================================================================


class TestFailClosed:
    """Test cases for fail-closed behavior."""

    def test_unknown_step_type_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["step_type"] = "sql_injection"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_unknown_top_level_field_fails(self):
        recipe = _valid_recipe_dict()
        recipe["unknown_risky_field"] = "dangerous"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_unknown_step_field_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["unknown_param"] = "bad"
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_validator_does_not_silently_ignore_risky_fields(self):
        recipe = _valid_recipe_dict()
        recipe["command"] = "ls"
        result = validate_recipe(recipe)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_deterministic_same_input_same_output(self):
        recipe = _valid_recipe_dict()
        r1 = validate_recipe(recipe)
        r2 = validate_recipe(recipe)
        assert r1.valid == r2.valid
        assert r1.errors == r2.errors
        assert r1.reasons == r2.reasons

    def test_validation_recipe_with_direct_model_also_validates(self):
        """Passing a ValidationRecipe object directly works."""
        parsed = ValidationRecipe(**_valid_recipe_dict())
        result = validate_recipe(parsed)
        assert result.valid is True

    def test_empty_dict_fails_gracefully(self):
        result = validate_recipe({})
        assert result.valid is False
        assert len(result.errors) > 0


# ==================================================================
# 8. Step-Type-Specific Semantics
# ==================================================================


class TestStepTypeSemantics:
    """Test cases for step-type-specific validation."""

    def test_http_check_destructive_method_post_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["step_type"] = "http_check"
        recipe["steps"][0]["parameters"] = {"method": "POST"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_http_check_destructive_method_put_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"method": "PUT"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_http_check_destructive_method_delete_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"method": "DELETE"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_http_check_get_method_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"method": "GET"}
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_http_check_head_method_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"method": "HEAD"}
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_http_check_body_parameter_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"method": "GET", "body": "data"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_http_check_data_parameter_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"method": "GET", "data": "x"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_http_check_auth_parameter_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {"method": "GET", "auth": "basic"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_http_check_unsafe_custom_header_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {
            "method": "GET",
            "headers": {"X-Custom": "value"},
        }
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_http_check_safe_header_accept_valid(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["parameters"] = {
            "method": "GET",
            "headers": {"Accept": "application/json"},
        }
        result = validate_recipe(recipe)
        assert result.valid is True

    def test_tcp_check_data_parameter_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["step_type"] = "tcp_check"
        recipe["steps"][0]["target"] = "127.0.0.1"
        recipe["steps"][0]["parameters"] = {"data": "payload"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_tcp_check_payload_parameter_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["step_type"] = "tcp_check"
        recipe["steps"][0]["target"] = "127.0.0.1"
        recipe["steps"][0]["parameters"] = {"payload": "x"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_evidence_check_external_url_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["step_type"] = "evidence_check"
        recipe["steps"][0]["target"] = "fixture:ev-bundle"
        recipe["steps"][0]["parameters"] = {"url": "https://example.com"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_local_fixture_check_path_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["step_type"] = "local_fixture_check"
        recipe["steps"][0]["target"] = "fixture:demo"
        recipe["steps"][0]["parameters"] = {"filepath": "/etc/passwd"}
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_http_check_requires_approval_false_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["requires_approval"] = False
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_tcp_check_requires_approval_false_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["step_type"] = "tcp_check"
        recipe["steps"][0]["target"] = "127.0.0.1"
        recipe["steps"][0]["requires_approval"] = False
        result = validate_recipe(recipe)
        assert result.valid is False


# ==================================================================
# 9. Safety Imports Check
# ==================================================================


class TestSafetyImports:
    """Verify that the module does not import dangerous libraries."""

    DANGEROUS_TOP_LEVEL_MODULES = {
        "requests",
        "httpx",
        "urllib3",
        "socket",
        "subprocess",
        "shlex",
        "dns",
        "nmap",
        "scapy",
        "impacket",
    }

    def _check_module_imports(self, module) -> None:
        """Use AST to check for dangerous imports (avoids docstring false positives)."""
        with open(module.__file__) as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    base = alias.name.split(".")[0]
                    assert base not in self.DANGEROUS_TOP_LEVEL_MODULES, (
                        f"Found dangerous import: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                base = module_name.split(".")[0]
                assert base not in self.DANGEROUS_TOP_LEVEL_MODULES, (
                    f"Found dangerous import: {module_name}"
                )

    def test_no_dangerous_imports_in_models(self):
        import neutrino.validation_recipe.models as m

        self._check_module_imports(m)

    def test_no_dangerous_imports_in_validators(self):
        import neutrino.validation_recipe.validators as v

        self._check_module_imports(v)

    def test_no_dangerous_imports_in_schema(self):
        import neutrino.validation_recipe.schema as s

        self._check_module_imports(s)

    def test_no_shell_execution_in_module(self):
        import neutrino.validation_recipe.validators as v

        with open(v.__file__) as f:
            tree = ast.parse(f.read())

        # Also check for dangerous function calls (not just imports)
        dangerous_calls = {"os.system", "os.popen", "exec", "eval", "compile"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    full_name = f"{self._get_name(node.func.value)}.{node.func.attr}"
                    assert full_name not in dangerous_calls, f"Found forbidden call: {full_name}"
                elif isinstance(node.func, ast.Name):
                    assert node.func.id not in dangerous_calls, (
                        f"Found forbidden call: {node.func.id}"
                    )

    @staticmethod
    def _get_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return TestSafetyImports._get_name(node.value)
        return ""


# ==================================================================
# 10. Bounds / Limits
# ==================================================================


class TestBoundsLimits:
    """Test cases for input bounds and limits."""

    def test_too_many_steps_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"] = [
            {
                "id": f"step-{i}",
                "name": f"Step {i}",
                "step_type": "manual_observation",
                "target": "fixture:test",
                "scope_reference": "scope:local-lab/demo-app",
                "requires_approval": False,
                "expected_evidence": ["ev"],
            }
            for i in range(MAX_STEPS + 1)
        ]
        result = validate_recipe(recipe)
        assert result.valid is False
        assert ValidationReasonCode.INVALID_TOO_MANY_STEPS in result.reasons

    def test_timeout_too_low_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["timeout_seconds"] = 0
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_timeout_too_high_fails(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["timeout_seconds"] = 999
        result = validate_recipe(recipe)
        assert result.valid is False

    def test_timeout_in_valid_range_passes(self):
        recipe = _valid_recipe_dict()
        recipe["steps"][0]["timeout_seconds"] = 60
        result = validate_recipe(recipe)
        assert result.valid is True
