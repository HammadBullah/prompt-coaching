import json
import ollama
import os
import random

# Configuration
OLLAMA_MODEL = "qwen2.5:1.5b"
INPUT_FILE = "/Users/hammadsafi/Downloads/prompt coaching/dataset/final_dataset.json"
OUTPUT_FILE = "/Users/hammadsafi/Downloads/prompt coaching/dataset/final_dataset.json"

# Targets: We want to generate data for classes with low support
TARGET_DIMENSIONS = ["constraints", "context"]

def generate_synthetic_prompts(dimension, count=50):
    print(f"Generating {count} samples for dimension: {dimension}...")
    
    # We provide examples to the LLM to ensure it follows your specific schema
    instruction = (
        f"You are a data scientist creating a training set for an LLM prompt classifier. "
        f"Generate {count} unique and diverse user prompts that EXPLICITLY include the '{dimension}' dimension.\n\n"
        f"For each prompt, you must also determine if other dimensions are present:\n"
        f"- goal (the main task)\n"
        f"- audience (who it is for)\n"
        f"- format (bullet points, table, email, etc.)\n"
        f"- constraints (word count, tone, style rules)\n"
        f"- context (background info, situation)\n\n"
        f"Output ONLY a valid JSON list of objects in this EXACT format:\n"
        f'[{{"prompt": "text...", "labels": {{"goal": 1, "audience": 0, "format": 1, "constraints": 1, "context": 0}}}}]'
    )

    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": instruction}],
            options={"temperature": 0.8} # High temp for diversity
        )
        # Extract JSON from response
        content = response["message"]["content"]
        start = content.find("[")
        end = content.rfind("]") + 1
        return json.loads(content[start:end])
    except Exception as e:
        print(f"Error generating for {dimension}: {e}")
        return []

def augment_dataset():
    # 1. Load original data
    with open(INPUT_FILE, "r") as f:
        original_data = json.load(f)
    
    print(f"Original dataset size: {len(original_data)}")
    
    new_samples = []
    
    # 2. Generate for minority classes
    for dim in TARGET_DIMENSIONS:
      
        batch = generate_synthetic_prompts(dim, count=500)
        new_samples.extend(batch)

    # 3. Clean and Validate
    valid_samples = []
    required_keys = ["goal", "audience", "format", "constraints", "context"]
    
    for s in new_samples:
        if "prompt" in s and "labels" in s and all(k in s["labels"] for k in required_keys):
            # Ensure labels are 1 or 0 (ints) for your DistilBERT script
            s["labels"] = {k: int(v) for k, v in s["labels"].items()}
            valid_samples.append(s)

    # 4. Merge
    final_data = original_data + valid_samples
    
    # 5. Save
    with open(OUTPUT_FILE, "w") as f:
        json.dump(final_data, f, indent=2)
    
    print("="*40)
    print("DATA AUGMENTATION COMPLETE")
    print(f"Added {len(valid_samples)} new samples.")
    print(f"New total size: {len(final_data)}")
    print(f"File saved to: {OUTPUT_FILE}")
    print("="*40)

if __name__ == "__main__":
    augment_dataset()