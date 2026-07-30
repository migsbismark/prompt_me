import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


class OllamaAgentTests(unittest.TestCase):
    def _make_fake_curl(self, fake_bin: Path, capture_dir: Path, response_text: str) -> None:
        fake_curl = fake_bin / "curl"
        fake_curl.write_text(
            textwrap.dedent(
                f"""
                #!/usr/bin/env bash
                # Args: -sS -X POST <url> -H 'Content-Type: application/json' -d <body>
                printf '%s' "$4" > "{capture_dir}/curl_url"
                printf '%s' "$8" > "{capture_dir}/curl_body"
                printf '%s' {json.dumps(response_text)}
                """
            ).strip()
            + "\n"
        )
        fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IEXEC)

    def test_ollama_agent_calls_chat_endpoint_and_returns_reply(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            fake_bin = temp_dir / "bin"
            fake_bin.mkdir()
            self._make_fake_curl(fake_bin, temp_dir, '{"message":{"content":"ok"}}')

            script = textwrap.dedent(
                f"""
                set -e
                export PATH={fake_bin}:$PATH
                bash {repo_root / 'agents' / 'ollama_agent.sh'} 'hello world'
                """
            ).strip()

            completed = subprocess.run(
                ["bash", "-lc", script],
                cwd=repo_root,
                capture_output=True,
                text=True,
                env={**os.environ, "OLLAMA_MODEL": "dummy-model"},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "ok")
            self.assertTrue((temp_dir / "curl_url").read_text().endswith("/api/chat"))
            body = json.loads((temp_dir / "curl_body").read_text())
            self.assertEqual(body["messages"], [{"role": "user", "content": "hello world"}])

    def test_ollama_agent_prefers_environment_host_over_config_file(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            fake_bin = temp_dir / "bin"
            fake_bin.mkdir()

            config_path = temp_dir / "ollama.json"
            config_path.write_text('{"model": "dummy-model", "host": "http://ollama:11434"}\n')

            self._make_fake_curl(fake_bin, temp_dir, '{"message":{"content":"ok"}}')

            script = textwrap.dedent(
                f"""
                set -e
                export PATH={fake_bin}:$PATH
                export OLLAMA_CONFIG_FILE={config_path}
                export OLLAMA_HOST=http://127.0.0.1:11434
                bash {repo_root / 'agents' / 'ollama_agent.sh'} 'hello world'
                """
            ).strip()

            completed = subprocess.run(
                ["bash", "-lc", script],
                cwd=repo_root,
                capture_output=True,
                text=True,
                env={**os.environ},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((temp_dir / "curl_url").read_text().strip(), "http://127.0.0.1:11434/api/chat")

    def test_ollama_agent_appends_to_existing_session_history(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            fake_bin = temp_dir / "bin"
            fake_bin.mkdir()
            self._make_fake_curl(fake_bin, temp_dir, '{"message":{"content":"second reply"}}')

            session_file = temp_dir / "session.json"
            session_file.write_text(json.dumps([
                {"role": "user", "content": "first prompt"},
                {"role": "assistant", "content": "first reply"},
            ]))

            script = textwrap.dedent(
                f"""
                set -e
                export PATH={fake_bin}:$PATH
                bash {repo_root / 'agents' / 'ollama_agent.sh'} 'second prompt' {session_file}
                """
            ).strip()

            completed = subprocess.run(
                ["bash", "-lc", script],
                cwd=repo_root,
                capture_output=True,
                text=True,
                env={**os.environ, "OLLAMA_MODEL": "dummy-model"},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "second reply")

            sent_body = json.loads((temp_dir / "curl_body").read_text())
            self.assertEqual(
                sent_body["messages"],
                [
                    {"role": "user", "content": "first prompt"},
                    {"role": "assistant", "content": "first reply"},
                    {"role": "user", "content": "second prompt"},
                ],
            )

            saved_history = json.loads(session_file.read_text())
            self.assertEqual(
                saved_history,
                [
                    {"role": "user", "content": "first prompt"},
                    {"role": "assistant", "content": "first reply"},
                    {"role": "user", "content": "second prompt"},
                    {"role": "assistant", "content": "second reply"},
                ],
            )


if __name__ == "__main__":
    unittest.main()
