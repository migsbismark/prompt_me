import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "frontier_llm_agent",
    Path(__file__).resolve().parents[1] / "agents" / "frontier_llm_agent.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrontierLlmAgentTests(unittest.TestCase):
    def test_openai_provider_builds_openai_request(self):
        config = {"provider": "openai", "model": "gpt-4.1-mini", "api_base": "https://api.openai.com/v1"}
        request = module.build_request(config, "hello", "token")
        self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer token")

    def test_anthropic_provider_builds_anthropic_request(self):
        config = {"provider": "anthropic", "model": "claude-3-5-sonnet-latest", "api_base": "https://api.anthropic.com/v1"}
        request = module.build_request(config, "hello", "token")
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(request.headers["x-api-key"], "token")
        self.assertEqual(request.headers["anthropic-version"], "2023-06-01")

    def test_azure_openai_provider_builds_azure_request(self):
        config = {
            "provider": "azure_openai",
            "deployment": "gpt-4o",
            "api_base": "https://example.openai.azure.com",
            "api_version": "2024-02-01",
        }
        request = module.build_request(config, "hello", "token")
        self.assertIn("https://example.openai.azure.com/openai/deployments/gpt-4o/chat/completions", request.full_url)
        self.assertIn("api-version=2024-02-01", request.full_url)
        self.assertEqual(request.headers["api-key"], "token")

    def test_gemini_provider_builds_gemini_request(self):
        config = {"provider": "gemini", "model": "gemini-2.0-flash", "api_base": "https://generativelanguage.googleapis.com/v1beta"}
        request = module.build_request(config, "hello", "token")
        self.assertIn("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent", request.full_url)
        self.assertIn("key=token", request.full_url)

    def test_openai_compatible_provider_builds_compatible_request(self):
        config = {"provider": "openai_compatible", "model": "local-model", "api_base": "http://localhost:8080/v1"}
        request = module.build_request(config, "hello", "token")
        self.assertEqual(request.full_url, "http://localhost:8080/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer token")


if __name__ == "__main__":
    unittest.main()
