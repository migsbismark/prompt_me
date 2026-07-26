import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


class OllamaAgentTests(unittest.TestCase):
    def test_ollama_agent_can_run_when_parent_shell_has_log_helpers(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            fake_bin = temp_dir / "bin"
            fake_bin.mkdir()

            fake_jq = fake_bin / "jq"
            fake_jq.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env bash
                    if [[ "$1" == "-nc" ]]; then
                      printf '{"response":"ok"}'
                      exit 0
                    fi
                    if [[ "$1" == "-e" ]]; then
                      exit 0
                    fi
                    if [[ "$1" == "-r" ]]; then
                      cat
                      exit 0
                    fi
                    cat
                    """
                ).strip()
                + "\n"
            )
            fake_jq.chmod(fake_jq.stat().st_mode | stat.S_IEXEC)

            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env bash
                    printf '{"response":"ok"}'
                    """
                ).strip()
                + "\n"
            )
            fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IEXEC)

            script = textwrap.dedent(
                f"""
                set -e
                function log_entry {{ :; }}
                function sanitize_for_log {{ :; }}
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
            self.assertIn("ok", completed.stdout)

    def test_ollama_agent_prefers_environment_host_over_config_file(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            fake_bin = temp_dir / "bin"
            fake_bin.mkdir()

            config_path = temp_dir / "ollama.json"
            config_path.write_text('{"model": "dummy-model", "host": "http://ollama:11434"}\n')

            fake_jq = fake_bin / "jq"
            fake_jq.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env bash
                    if [[ "$1" == "-r" ]]; then
                      if [[ "$2" == ".model // empty" ]]; then
                        printf 'dummy-model'
                      elif [[ "$2" == ".host // empty" ]]; then
                        printf 'http://ollama:11434'
                      else
                        cat
                      fi
                    else
                      cat
                    fi
                    """
                ).strip()
                + "\n"
            )
            fake_jq.chmod(fake_jq.stat().st_mode | stat.S_IEXEC)

            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                textwrap.dedent(
                    """
                    #!/usr/bin/env bash
                    printf '%s\n' "$4" > "$TMPDIR/curl_target"
                    printf '{"response":"ok"}'
                    """
                ).strip()
                + "\n"
            )
            fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IEXEC)

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
                env={**os.environ, "TMPDIR": str(temp_dir)},
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((temp_dir / "curl_target").read_text().strip(), "http://127.0.0.1:11434/api/generate")


if __name__ == "__main__":
    unittest.main()
