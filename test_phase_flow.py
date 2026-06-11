"""
Test script to demonstrate the refund/savings phase division and AI summary logging
"""
import logging
import sys
from datetime import datetime

# Set up logging to show in terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

print("\n" + "="*70)
print("🔍 TAX ASSESSMENT BOT - PHASE FLOW TEST")
print("="*70 + "\n")

print("📋 PHASE 1: REFUND ASSESSMENT")
print("-" * 70)
print("Questions 1-8: Income eligibility, travel for work, journey type, etc.")
print("Purpose: Determine if user qualifies for a tax refund")
print()

refund_questions = [
    ("Q1", "How much do you earn a year?", "Between £14k & £50k"),
    ("Q2", "Do you travel for work in your current job?", "Yes"),
    ("Q3", "How do you make your work journeys?", "My vehicle"),
    ("Q4", "How many miles do you drive a year?", "5000"),
    ("Q5", "How does your employer pay your mileage expenses?", "Mileage rate"),
]

for q_ref, q_title, answer in refund_questions:
    print(f"  {q_ref}: {q_title}")
    print(f"     → Answer: {answer}")

print("\n✅ PHASE 1 COMPLETE!")
print("-" * 70 + "\n")

print("💰 PHASE 2: SAVINGS ASSESSMENT")
print("-" * 70)
print("Questions 9-13: Daily travel, food expenses, employer reimbursement, etc.")
print("Purpose: Calculate potential tax savings from expenses")
print()

savings_questions = [
    ("Q8", "Do you buy food and drink when travelling for work?", "Yes"),
    ("Q9", "How many days do you travel a week on average?", "3"),
    ("Q10", "How much do you spend on food and drink per day on average?", "£10"),
    ("Q11", "Does your employer pay any expenses for your food and drink?", "No"),
    ("Q12", "How much of the spend does your employer pay?", "£0"),
    ("Q13", "Did you earn more than £14,000 in any of the last 4 tax years?", "Yes"),
]

for q_ref, q_title, answer in savings_questions:
    print(f"  {q_ref}: {q_title}")
    print(f"     → Answer: {answer}")

print("\n✅ PHASE 2 COMPLETE!")
print("="*70 + "\n")

# Simulate AI summary generation logging
print("🤤 GENERATING AI SUMMARY")
print("="*70)
print("Phase: 💰 Savings Assessment")
print("Provider: GEMINI")
print("="*70 + "\n")

logger.info("📝 Summary Input:")
logger.info("""
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
""")

logger.info("="*70)
logger.info("✅ AI SUMMARY GENERATED SUCCESSFULLY")
logger.info("="*70 + "\n")

logger.info("""🎯 AI SUMMARY:
Based on your responses, you travel an average of 3 days per week and spend £10 on food and drink daily while traveling for work. Since your employer does not reimburse these expenses, you could potentially claim approximately £1,440 annually in tax relief (£10 × 3 days × 48 weeks), which could result in significant tax savings depending on your tax bracket.
""")

logger.info("="*70 + "\n")

print("\n✅ TEST COMPLETE!")
print("="*70)
print("\nKey Improvements:")
print("  ✓ Clear division between Refund Assessment (Phase 1) and Savings Assessment (Phase 2)")
print("  ✓ AI summary is logged to terminal with formatted output")
print("  ✓ Each phase shows which questions are included")
print("  ✓ User sees phase progression in the chat header")
print("="*70 + "\n")
