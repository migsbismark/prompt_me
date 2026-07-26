# Prompt Optimizer

This application is a lightweight prompt engineering workflow that uses a local Ollama model to improve an initial prompt before sending it to a configurable frontier LLM.

## Main intention

The main goal is to make prompt writing more reliable and more effective. The system first checks whether a prompt is already clear. If it is not, it asks follow-up questions one at a time (up to 5), stopping as soon as it has enough information, uses the answers to rewrite the prompt, and then forwards the improved version to a frontier model.

This is useful when you want better results from large language models without manually rewriting every prompt from scratch.

## What it does

- Uses a local Ollama model for prompt analysis and prompt improvement
- Asks clarifying questions one at a time and stops as soon as it has enough information, rather than always asking a fixed batch
- Adds guardrails against fabricated facts: the rewritten prompt is instructed not to invent details, and the final prompt sent to the frontier model carries explicit accuracy constraints
- Compresses the final prompt with [Headroom](https://github.com/headroomlabs-ai/headroom) right before it is sent to the frontier model, cutting token usage without touching what is sent to the local Ollama model
- Supports multiple frontier LLM backends through configuration
- Reads API credentials from a local .env file
- Keeps secrets out of version control via .gitignore

## Requirements

- Ollama installed and running locally
- A model available in Ollama, for example `llama3.2:3b`
- `curl`, `jq`, and Python 3 installed
- Python dependencies from [requirements.txt](requirements.txt) (installs [`headroom-ai`](https://github.com/headroomlabs-ai/headroom), used to compress the prompt sent to the frontier model). In the devcontainer this installs automatically every time the app container starts (see [.devcontainer/entrypoint.sh](.devcontainer/entrypoint.sh)); otherwise run `pip install -r requirements.txt` yourself.

## Configuration

- Local Ollama settings: [config/ollama.json](config/ollama.json)
- Frontier LLM settings: [config/frontier_llm.json](config/frontier_llm.json)
- API keys: copy [.env.example](.env.example) to `.env` and fill in the values you need

Supported frontier providers:
- `openai`
- `anthropic`
- `azure_openai`
- `gemini`
- `openai_compatible`

## Run it

### Logging

Each run creates a separate session log file in the logs folder. The filename includes a timestamp, and the file header contains session information such as the creation time, hostname, IP address, current user, working directory, the selected Ollama model, and the frontier config path.

Example:

```bash
./prompt_optimizer.sh "Summarize this article in three bullet points"
```

If you want to choose a specific log file name, you can override it:

```bash
./prompt_optimizer.sh --log-file logs/my_session.log "Summarize this article in three bullet points"
```

### 1. Start Ollama

If you are using the devcontainer, Ollama is started automatically by the container setup and is available at `http://ollama:11434`.

If you are running outside the devcontainer, start the Ollama container with:

```bash
docker compose up -d ollama
```

Do not run `ollama serve` manually inside the app container; the app connects to the service endpoint instead.

### 2. Set up credentials

```bash
cp .env.example .env
```

Then edit `.env` and add the API key for the provider you want to use.

### 3. Run the optimizer

Basic example:

```bash
./prompt_optimizer.sh "Summarize this article in three bullet points"
```

Example with a different local Ollama model:

```bash
./prompt_optimizer.sh --model phi3:mini "Explain this error clearly"
```

Example that writes the final optimized prompt to a file:

```bash
./prompt_optimizer.sh --output optimized_prompt.txt "Draft a release note for this change"
```

### 4. Switch frontier providers

Edit [config/frontier_llm.json](config/frontier_llm.json) and change the provider/model values. For example, to use Anthropic:

```json
{
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-latest",
  "api_base": "https://api.anthropic.com/v1",
  "api_key_env": "ANTHROPIC_API_KEY"
}
```

## Example behavior

If your prompt is already clear, the application will return it as-is. If it is vague, it will ask up to 5 follow-up questions one at a time -- stopping early as soon as it decides it has enough to work with -- and generate a refined version before sending it to the frontier model.

Before the refined prompt is sent to the frontier model, the tool appends an accuracy-constraints block that tells the model to rely only on the information provided, call out anything missing or ambiguous instead of guessing, and clearly separate assumptions from stated facts. This is meant to reduce hallucinated details flowing from either the local enhancement step or the frontier model's response.

Immediately before that final prompt goes out over the network, [agents/frontier_llm_agent.py](agents/frontier_llm_agent.py) runs it through Headroom's `compress()` to shrink token usage. This only applies to the request sent to the frontier model -- the local Ollama calls (clarity check, clarifying questions, enhancement rewrite) are left untouched.
