import sys
import os
import json
import ollama

# 1. Setup paths to import your existing logic
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from clarification.evaluate_ml_analyzer import predict_missing_dimensions
from clarification.recustructor import reconstruct_prompt
from humanizer.humanizer import LinguisticHumaniser

# Initialize
human_processor = LinguisticHumaniser()
TEST_MODEL = "qwen2.5:1.5b"
OUTPUT_FILE = "results/rq3_raw_data.json"

# COMMON DIMENSION SPECIFICATIONS (The 'Expert Profile')
# These ensure every coached prompt is high-density.
COMMON_ANSWERS = {
    "goal": "Provide a comprehensive overview",
    "audience": "poeple",
    "format": "paragraph",
    "constraints": "Keep the tone professional yet coaching-oriented, and ensure the length is around 300 words.",
    "context": "This is for prompt specifc people"
}

test_prompts = [
    "Write a report about AI",
    "Explain machine learning",
    "Plan a trip to Japan",
    "Write a Python function to sort data",
    "Create a marketing strategy",
    "Help me write an email to my boss",
    "Explain how a car engine works",
    "Write a business plan",
    "Give me advice on losing weight",
    "Write a short story about a robot",
]

def generate_data():
    results = []
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    print(f"--- STARTING AUTONOMOUS RQ3 EVALUATION ---")

    for i, original_prompt in enumerate(test_prompts):
        print(f"\n[{i+1}/{len(test_prompts)}] Processing: {original_prompt}")
        
        # --- PHASE 1: STANDARD PASS ---
        print("   > Generating Standard Response...")
        std_resp = ollama.chat(
            model=TEST_MODEL,
            messages=[{"role": "user", "content": original_prompt}]
        )["message"]["content"]

        # --- PHASE 2: COACHED PASS ---
        print("   > Analyzing dimensions...")
        missing = [m.lower().strip() for m in predict_missing_dimensions(original_prompt)]
        
        # Automatically fill missing dimensions from our Expert Profile
        answers = {dim: COMMON_ANSWERS.get(dim, "Provide more detail.") for dim in missing}
        
        print(f"   > Automatically added specifications for: {list(answers.keys())}")
        
        # A. Reconstruct using your logic
        refined_prompt = reconstruct_prompt(original_prompt, answers)
        
        # B. Generate from refined prompt
        print("   > Generating Coached Response...")
        coached_raw = ollama.chat(
            model=TEST_MODEL,
            messages=[{"role": "user", "content": refined_prompt}]
        )["message"]["content"]
        
        # C. Humanise using your module
        humanised_data = human_processor.humanise(coached_raw)
        coached_final = humanised_data["humanised"]

        # --- PHASE 3: STORE ---
        item = {
            "id": i + 1,
            "original_prompt": original_prompt,
            "dimensions_detected_missing": missing,
            "refined_prompt": refined_prompt,
            "response_standard": std_resp,
            "response_coached": coached_final
        }
        results.append(item)
        
        # Save progress
        with open(OUTPUT_FILE, "w") as f:
            json.dump(results, f, indent=2)

    print(f"\n--- SUCCESS! ALL 20 SAMPLES SAVED TO {OUTPUT_FILE} ---")

if __name__ == "__main__":
    generate_data()