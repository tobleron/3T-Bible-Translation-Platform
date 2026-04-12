import os
import requests
import json
from openai import OpenAI
from ttt_core.config import load_config

class LlamaCppClient:
    """Handles communication with the local llama.cpp server."""
    def __init__(self, config=None):
        if config is None:
            config = load_config()
        
        # Default endpoint as requested by user
        self.base_url = "http://192.168.1.186:8081/v1"
        self.api_key = None
        
        if 'llama_cpp' in config:
            self.base_url = config['llama_cpp'].get('base_url', self.base_url).rstrip("/")
            self.api_key = config['llama_cpp'].get('api_key')

    def _get_headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def list_models(self):
        """llama.cpp usually serves one model, returning a placeholder or actual model info if available."""
        try:
            if "/v1" in self.base_url:
                url = f"{self.base_url}/models"
            else:
                url = f"{self.base_url}/v1/models"
            response = requests.get(url, headers=self._get_headers(), timeout=5)
            if response.status_code == 200:
                models = response.json().get("data", [])
                return [m["id"] for m in models]
            return ["llama.cpp-model"]
        except:
            return ["llama.cpp-model"]

    def stream_generation(self, model_name, prompt_or_messages, temperature):
        """
        Connects to llama.cpp's /completion or /v1/chat/completions endpoint.
        Using /completion for simple prompt-based translation as requested.
        """
        if isinstance(prompt_or_messages, list):
            # Convert list of messages to a single prompt string if using /completion
            prompt_text = ""
            for msg in prompt_or_messages:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                prompt_text += f"\n\n{role.upper()}: {content}"
            prompt_text += "\n\nASSISTANT:"
        else:
            prompt_text = prompt_or_messages

        payload = {
            "prompt": prompt_text,
            "temperature": temperature,
            "stream": True,
            "n_predict": 4096, # Adjust as needed
        }

        try:
            # Using llama.cpp's native /completion endpoint
            if "/v1" in self.base_url:
                url = f"{self.base_url}/completions"
            else:
                url = f"{self.base_url}/completion"
            with requests.post(url, json=payload, headers=self._get_headers(), stream=True, timeout=300) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith("data: "):
                            data = json.loads(line_str[6:])
                            if "content" in data:
                                yield data["content"]
                            if data.get("stop"):
                                # Optionally yield stats if llama.cpp provides them
                                stats = {
                                    "tokens_predicted": data.get("tokens_predicted"),
                                    "generation_settings": data.get("generation_settings")
                                }
                                yield f"__STATS_BLOCK__{json.dumps(stats)}__END_STATS__"
        except Exception as e:
            yield f"\n[ERROR] llama.cpp generation failed: {e}"

class OpenAIClient:
    """Handles all communication with the OpenAI API (fallback/alternative)."""
    def __init__(self, config):
        api_key = os.environ.get("OPENAI_API_KEY") or config.get('openai', {}).get('api_key')
        self.client = OpenAI(api_key=api_key) if api_key else None
        self.available_models = config.get('openai', {}).get('available_models', ["gpt-4o", "gpt-3.5-turbo"])

    def list_models(self):
        return self.available_models

    def stream_generation(self, model_name, prompt_or_messages, temperature):
        if not self.client:
            yield "[ERROR] OpenAI API key not found."
            return

        if not isinstance(prompt_or_messages, list):
            messages = [{"role": "user", "content": prompt_or_messages}]
        else:
            messages = prompt_or_messages
        
        try:
            stream = self.client.chat.completions.create(
                model=model_name,
                messages=messages,
                stream=True,
                temperature=temperature
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            yield f"\n[ERROR] OpenAI generation failed: {e}"
