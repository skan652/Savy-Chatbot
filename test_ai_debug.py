"""
Test script to debug AI summary generation
"""
import os
import sys
from pathlib import Path

# Add the project to path
sys.path.insert(0, str(Path(__file__).parent))

# Set up environment
os.environ["USE_AI"] = "true"
os.environ["AI_PROVIDER"] = "gemini"
os.environ["GOOGLE_API_KEY"] = "AQ.Ab8RN6K6VvQmXxxHhmHHafZMwyV_alsMvbVYyWgrLe15gHtoIw"
os.environ["GOOGLE_MODEL"] = "gemini-2.5-flash"

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')

from ai_client import AIClient

print("\n" + "="*70)
print("🧪 TESTING AI SUMMARY GENERATION")
print("="*70 + "\n")

# Initialize AI client
ai_client = AIClient()

print(f"Provider: {ai_client.provider}")
print(f"Model: {ai_client.google_model}")
print(f"Has Google API Key: {bool(ai_client.google_key)}\n")

# Test AI summary
test_summary = """
💰 Savings Assessment Summary:

How many days do you travel a week on average?
→ 3

How much do you spend on food and drink per day on average?
→ £10

Does your employer pay any expenses for your food and drink?
→ No

How much of the spend does your employer pay?
→ £0

Did you earn more than £14,000 in any of the last 4 tax years?
→ Yes
"""

system_prompt = "You are a tax assessment specialist. Provide a concise, professional summary of the user's assessment in 2-3 sentences."

print("📝 Input Summary:")
print(test_summary)
print("\n🔄 Calling ai_client.generate()...")
print("="*70 + "\n")

try:
    result = ai_client.generate(
        prompt=test_summary,
        system_prompt=system_prompt,
        max_tokens=500,
        temperature=0.7
    )
    
    print("\n" + "="*70)
    if result:
        print("✅ AI RESPONSE RECEIVED:")
        print("="*70)
        print(result)
        print("="*70)
    else:
        print("❌ AI RESPONSE IS EMPTY")
        print("="*70)
        
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n")
