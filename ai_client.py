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
        self.google_model = os.environ.get("GOOGLE_MODEL", "gemini-1.5-flash")

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
            logger.error("No Google API key or token provided")
            return ""

        model = self.google_model
        logger.info(f"Using Gemini model: {model}")
        
        # Build the prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt
        
        # Try multiple authentication methods
        auth_methods = []
        
        # Method 1: API key in URL (most common)
        if self.google_key:
            auth_methods.append({
                "name": "API Key in URL",
                "url": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.google_key}",
                "headers": {"Content-Type": "application/json"}
            })
        
        # Method 2: API key in header (alternative)
        if self.google_key:
            auth_methods.append({
                "name": "API Key in Header",
                "url": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                "headers": {
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.google_key
                }
            })
        
        # Method 3: Bearer token (if you have a token)
        if self.google_token:
            auth_methods.append({
                "name": "Bearer Token",
                "url": f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.google_token}"
                }
            })
        
        # Request body
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
        
        # Try each authentication method
        for auth_method in auth_methods:
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"Trying auth: {auth_method['name']} (attempt {attempt + 1})")
                    
                    response = requests.post(
                        auth_method["url"],
                        headers=auth_method["headers"],
                        json=body,
                        timeout=self.request_timeout
                    )
                    
                    logger.info(f"Response status: {response.status_code}")
                    
                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            content = candidates[0].get("content", {})
                            parts = content.get("parts", [])
                            if parts:
                                text = parts[0].get("text", "").strip()
                                if text:
                                    logger.info(f"✅ Gemini response: {text[:100]}...")
                                    return text
                                else:
                                    logger.warning("Empty text in response")
                            else:
                                logger.warning("No parts in response")
                        else:
                            logger.warning("No candidates in response")
                            # Check for finish reason
                            if candidates:
                                finish_reason = candidates[0].get("finishReason", "UNKNOWN")
                                logger.warning(f"Finish reason: {finish_reason}")
                        # If we get here, response was 200 but no content
                        # Return a default summary
                        return self._generate_fallback_summary(prompt)
                    
                    elif response.status_code == 401:
                        logger.error(f"Authentication failed (401) with {auth_method['name']}")
                        logger.error(f"Response: {response.text[:300]}")
                        break  # Try next auth method
                    
                    elif response.status_code == 404:
                        logger.warning(f"Model not found (404). Trying different model...")
                        # Try with a different model
                        fallback_models = ["gemini-1.5-flash", "gemini-pro", "gemini-1.5-pro"]
                        for fallback_model in fallback_models:
                            if fallback_model != model:
                                logger.info(f"Trying fallback model: {fallback_model}")
                                # Update URL with fallback model
                                fallback_url = auth_method["url"].replace(model, fallback_model)
                                response = requests.post(
                                    fallback_url,
                                    headers=auth_method["headers"],
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
                                                logger.info(f"✅ Gemini response with fallback model: {text[:100]}...")
                                                return text
                        break
                    
                    elif response.status_code == 429:
                        if attempt < self.max_retries - 1:
                            wait_time = 2 ** attempt
                            logger.warning(f"Rate limited (429). Retrying in {wait_time}s")
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error("Rate limit exceeded")
                            break
                    
                    else:
                        logger.error(f"Gemini API error ({response.status_code}): {response.text[:300]}")
                        break
                        
                except requests.exceptions.RequestException as e:
                    logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    else:
                        break
        
        # If all methods fail, return a fallback summary
        logger.warning("All Gemini API attempts failed. Using fallback summary.")
        return self._generate_fallback_summary(prompt)

    def _generate_fallback_summary(self, prompt: str) -> str:
        """Generate a fallback summary when API fails"""
        # Extract key information from the prompt
        lines = prompt.split('\n')
        summary_parts = []
        
        for line in lines:
            if '→' in line or ':' in line:
                summary_parts.append(line.strip())
        
        if summary_parts:
            fallback = "📝 **Assessment Summary**\n\nBased on your responses:\n\n"
            for part in summary_parts[:8]:
                fallback += f"• {part}\n"
            if len(summary_parts) > 8:
                fallback += f"\n• ... and {len(summary_parts) - 8} more responses"
            fallback += "\n\nA tax specialist will review your information and contact you soon."
            return fallback
        else:
            return "Thank you for completing the tax assessment. Your responses have been recorded and will be reviewed by our tax specialists."

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
            logger.error("No OpenAI API key provided")
            return self._generate_fallback_summary(prompt)

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
                    return self._generate_fallback_summary(prompt)

                text_parts = []
                for ch in choices:
                    msg = ch.get("message") or {}
                    content = msg.get("content") or ""
                    text_parts.append(content)

                result = "\n".join(text_parts).strip()
                if result:
                    return result
                else:
                    return self._generate_fallback_summary(prompt)

            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    if attempt < self.max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limited. Retrying in {wait_time}s")
                        time.sleep(wait_time)
                        continue
                logger.error(f"OpenAI API error: {exc}")
                if attempt == self.max_retries - 1:
                    return self._generate_fallback_summary(prompt)
            except requests.exceptions.RequestException as exc:
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"OpenAI request error: {exc}")
                return self._generate_fallback_summary(prompt)
        
        return self._generate_fallback_summary(prompt)