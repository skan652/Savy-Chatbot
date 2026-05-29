import os
import sys

# Ensure project root is on import path so `from ai_client import AIClient` works
sys.path.insert(0, os.getcwd())

from ai_client import AIClient
import logging

# Enable debug logging so ai_client debug messages are visible
logging.basicConfig(level=logging.DEBUG)

# Load .env if present (same logic as app.py)
dotenv_path = os.path.join(os.getcwd(), ".env")
if os.path.exists(dotenv_path):
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"Warning: Could not load .env file: {e}")

# Ensure AI is enabled for the test
os.environ.setdefault("USE_AI", "1")
provider = os.environ.get("AI_PROVIDER", "gemini").lower()

ai = AIClient()

# Build a sample plain summary (useful if you don't have session data)
plain_summary = "Assessment Summary:\n\n- Income: Between £14k & £50k\n- Travel for work: Yes\n- Mileage: 8,000\n\n"
system_prompt = "You are a tax assessment assistant. Provide a concise, professional summary of the taxpayer's assessment in 2-3 sentences."

# If no credentials are present, stub the response to avoid real network calls
has_creds = bool(ai.chatgpt_key or ai.openai_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_TOKEN"))

if not has_creds:
    print("No AI credentials found in environment; using stubbed AI summary for demonstration.\n")
    ai_summary = "The assessment suggests several potential tax savings related to mileage and travel expenses; a tax specialist should review the details to maximize refunds."
else:
    try:
        ai_summary = ai.generate(prompt=plain_summary, system_prompt=system_prompt, max_tokens=200, temperature=0.7)
    except Exception as e:
        ai_summary = f"Error generating AI summary: {e}"

print("----- AI Summary -----\n")
print(ai_summary)
print("\n----------------------")
