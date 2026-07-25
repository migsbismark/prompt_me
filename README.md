# Prompt Optimizer

This application is a lightweight prompt engineering workflow that uses a local Ollama model to improve an initial prompt before sending it to a configurable frontier LLM.

## Main intention

The main goal is to make prompt writing more reliable and more effective. The system first checks whether a prompt is already clear. If it is not, it asks three focused follow-up questions, uses the answers to rewrite the prompt, and then forwards the improved version to a frontier model.

This is useful when you want better results from large language models without manually rewriting every prompt from scratch.

## What it does

- Uses a local Ollama model for prompt analysis and prompt improvement
- Supports multiple frontier LLM backends through configuration
- Reads API credentials from a local .env file
- Keeps secrets out of version control via .gitignore

## Requirements

- Ollama installed and running locally
- A model available in Ollama, for example `llama3.2:3b`
- `curl`, `jq`, and Python 3 installed

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

### 1. Start Ollama

Make sure your local Ollama server is running, for example:

```bash
ollama serve
```

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

If your prompt is already clear, the application will return it as-is. If it is vague, it will ask three follow-up questions and generate a refined version before sending it to the frontier model.
