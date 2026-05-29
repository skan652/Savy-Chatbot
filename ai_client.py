# ai_client.py
import os
import time
import requests
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class AIClient:
    """
    Multi-provider AI Client supporting Gemini and OpenAI.
    """

    def __init__(self):
        self._load_dotenv_if_present()

        # ChatGPT / OpenAI credentials
        self.chatgpt_key = os.environ.get("CHATGPT_API_KEY")
        self.openai_key = os.environ.get("OPENAI_API_KEY")
        self.openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.chatgpt_model = os.environ.get("CHATGPT_MODEL", self.openai_model)

        # Google Gemini credentials
        self.google_key = os.environ.get("GOOGLE_API_KEY")
        self.google_token = os.environ.get("GOOGLE_API_TOKEN")
        self.google_model = os.environ.get("GOOGLE_MODEL", "gemini-2.5-flash")

        # Request settings
        self.request_timeout = int(os.environ.get("AI_REQUEST_TIMEOUT", "30"))
        self.max_retries = int(os.environ.get("AI_MAX_RETRIES", "3"))

        # Provider selection
        requested_provider = os.environ.get("AI_PROVIDER")
        if requested_provider:
            self.provider = requested_provider.lower()
        elif self.google_key or self.google_token:
            self.provider = "gemini"
        elif self.chatgpt_key or self.openai_key:
            self.provider = "openai"
        else:
            self.provider = "gemini"

        logger.info(f"AIClient initialized: provider={self.provider}, model={self.google_model}")

    def _load_dotenv_if_present(self):
        dotenv_path = os.path.join(os.getcwd(), ".env")
        if not os.path.exists(dotenv_path):
            return

        try:
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
        except Exception as e:
            logger.error(f"Could not load .env file: {e}")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7
    ) -> str:
        """Generate text using the selected provider."""
        if self.provider in ("gemini", "google"):
            return self._generate_gemini(prompt, system_prompt, max_tokens, temperature)
        elif self.provider in ("openai", "chatgpt"):
            return self._generate_openai(prompt, system_prompt, max_tokens, temperature)
        else:
            raise NotImplementedError(f"Provider '{self.provider}' not supported")

    def _generate_gemini(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate using Google Gemini API."""
        if not self.google_key and not self.google_token:
            raise EnvironmentError("GOOGLE_API_KEY or GOOGLE_API_TOKEN not set for Gemini")

        # Use the model from env or default to a working one
        model = self.google_model
        
        # Use v1 endpoint (not v1beta)
        url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent"
        params = {"key": self.google_key} if self.google_key else {}
        
        headers = {"Content-Type": "application/json"}
        if self.google_token:
            headers["Authorization"] = f"Bearer {self.google_token}"
        
        # Build the prompt with system instructions
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        
        # Correct request body format for Gemini API
        body = {
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": 0.95,
                "topK": 40
            }
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    json=body,
                    timeout=self.request_timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        parts = content.get("parts", [])
                        if parts:
                            text = parts[0].get("text", "").strip()
                            if text:
                                logger.info(f"Successfully generated with model {model}")
                                return text
                    return ""
                elif response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limited. Retrying in {wait_time}s")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error("Rate limit exceeded after retries")
                        return ""
                else:
                    logger.error(f"Gemini API error ({response.status_code}): {response.text}")
                    if attempt == self.max_retries - 1:
                        return ""
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                else:
                    return ""
        
        return ""

    def _generate_openai(
        self,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Generate using OpenAI/ChatGPT API."""
        api_key = self.chatgpt_key or self.openai_key
        if not api_key:
            raise EnvironmentError("CHATGPT_API_KEY or OPENAI_API_KEY not set")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.chatgpt_model or self.openai_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        for attempt in range(self.max_retries):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.request_timeout)
                resp.raise_for_status()
                data = resp.json()

                choices = data.get("choices") or []
                if not choices:
                    return ""

                text_parts = []
                for ch in choices:
                    msg = ch.get("message") or {}
                    content = msg.get("content") or ""
                    text_parts.append(content)

                return "\n".join(text_parts).strip()

            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limited. Retrying in {wait_time}s")
                        time.sleep(wait_time)
                        continue
                logger.error(f"OpenAI API error: {exc}")
                if attempt == self.max_retries - 1:
                    raise
            except requests.exceptions.RequestException as exc:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"OpenAI request error: {exc}")
                raise
        
        return ""
