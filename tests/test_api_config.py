from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from agents.agent import Agent
from agents.main import _resolve_api_config


class ResolveApiConfigTests(unittest.TestCase):
    def resolve(self, cli_api_base: str | None = None, **env: str):
        with patch.dict(os.environ, env, clear=True):
            return _resolve_api_config(cli_api_base)

    def test_openai_key_without_base_uses_openai_default(self):
        self.assertEqual(
            self.resolve(OPENAI_API_KEY="openai-key"),
            (None, "openai-key", True),
        )

    def test_anthropic_key_without_base_uses_anthropic_default(self):
        self.assertEqual(
            self.resolve(ANTHROPIC_API_KEY="anthropic-key"),
            (None, "anthropic-key", False),
        )

    def test_dedicated_openai_base_determines_protocol_and_key(self):
        self.assertEqual(
            self.resolve(
                OPENAI_BASE_URL="https://gateway.example/v1",
                OPENAI_API_KEY="openai-key",
                APIKEY="generic-key",
            ),
            ("https://gateway.example/v1", "openai-key", True),
        )

    def test_dedicated_anthropic_base_determines_protocol_and_key(self):
        self.assertEqual(
            self.resolve(
                ANTHROPIC_BASE_URL="https://api.anthropic.com",
                ANTHROPIC_API_KEY="anthropic-key",
                APIKEY="generic-key",
            ),
            ("https://api.anthropic.com", "anthropic-key", False),
        )

    def test_generic_base_prefers_generic_key(self):
        self.assertEqual(
            self.resolve(
                API="https://gateway.example/v1",
                APIKEY="generic-key",
                OPENAI_API_KEY="openai-key",
            ),
            ("https://gateway.example/v1", "generic-key", True),
        )

    def test_generic_official_anthropic_url_is_detected(self):
        self.assertEqual(
            self.resolve(API="https://api.anthropic.com", APIKEY="generic-key"),
            ("https://api.anthropic.com", "generic-key", False),
        )

    def test_dedicated_base_does_not_use_other_protocol_key(self):
        self.assertEqual(
            self.resolve(
                OPENAI_BASE_URL="https://gateway.example/v1",
                ANTHROPIC_API_KEY="anthropic-key",
            ),
            ("https://gateway.example/v1", None, True),
        )

    def test_cli_base_overrides_env_and_prefers_matching_protocol_key(self):
        self.assertEqual(
            self.resolve(
                "https://cli.example/anthropic/v1",
                API="https://gateway.example/v1",
                APIKEY="generic-key",
                ANTHROPIC_API_KEY="anthropic-key",
            ),
            ("https://cli.example/anthropic/v1", "anthropic-key", False),
        )


class AgentClientSelectionTests(unittest.TestCase):
    def test_explicit_openai_protocol_does_not_require_custom_base(self):
        with (
            patch("agents.agent.openai.AsyncOpenAI") as openai_client,
            patch("agents.agent.anthropic.AsyncAnthropic") as anthropic_client,
        ):
            agent = Agent(use_openai=True, api_base=None, api_key="openai-key")

        self.assertTrue(agent.use_openai)
        openai_client.assert_called_once_with(base_url=None, api_key="openai-key")
        anthropic_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
