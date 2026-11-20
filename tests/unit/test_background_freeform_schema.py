"""Free-form Link parameters must survive SDK function-tool construction."""
from copy import deepcopy
import unittest
from typing import cast

from app.vault_runtime.background_agent.agent_brief import strict_compatible
from app.vault_runtime.background_agent.executor import ResumableBackgroundExecutor
from app.vault_runtime.background_agent.tool_supply import BackgroundToolSupply


class _ReadOnlyTools:
    def effect_class(self, _name):
        return "read"


class FreeformSchemaTests(unittest.TestCase):
    def test_link_setup_manifests_remain_freeform(self):
        for name in ("link_setup_validate", "setup_install"):
            with self.subTest(tool=name):
                schema = {
                    "type": "object",
                    "properties": {"manifest": {"type": "object"}},
                    "required": ["manifest"],
                }
                original = deepcopy(schema)
                self.assertFalse(strict_compatible(schema))
                never = lambda *_args, **_kwargs: None  # noqa: E731 - never invoked by this test
                tool = ResumableBackgroundExecutor()._build_sdk_tool(
                    {"name": name, "description": "Link setup", "inputSchema": schema},
                    scope=None, request=None, tools=cast(BackgroundToolSupply, _ReadOnlyTools()),
                    tool_context=never, cancel_requested=never, check_step_guards=never,
                    cached_results={}, interrupted_meta={}, resumed_call_id="", resumed_action_id="",
                    resumed_mode="", write_in_flight=[False], uncertain_effect=[False], record_and_raise=never,
                )
                self.assertFalse(tool.strict_json_schema)
                self.assertEqual(tool.params_json_schema, original)
                self.assertEqual(schema, original)

    def test_nested_freeform_objects_disable_strict_mode(self):
        freeform = {"type": "object", "properties": {}}
        schemas = [
            freeform,
            {"type": "array", "items": freeform},
            {"anyOf": [{"type": "string"}, freeform]},
            {"$defs": {"manifest": freeform}},
            {"definitions": {"manifest": freeform}},
            {"type": "object", "additionalProperties": True},
            {"type": "object", "additionalProperties": {"type": "string"}},
        ]
        for schema in schemas:
            with self.subTest(schema=schema):
                self.assertFalse(strict_compatible(schema))

    def test_explicitly_closed_empty_object_remains_strict(self):
        self.assertTrue(strict_compatible({
            "type": "object", "properties": {}, "additionalProperties": False,
        }))


if __name__ == "__main__":
    unittest.main()
