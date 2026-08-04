# evaluate.py
# Run this to generate all your results

import json
import requests
import time
from datetime import datetime

# Configuration
OLLAMA_URL = "http://127.0.0.1:11434"
API_URL = "http://127.0.0.1:8000"
MODEL = "qwen2.5:1.5b"
TEST_SIZE = 100

# Judge prompt (for LLM-as-judge)
JUDGE_PROMPT = """You are an expert evaluator. Compare these two AI responses.

ORIGINAL PROMPT: {prompt}

RESPONSE A (Standard - no coaching):
{response_a}

RESPONSE B (Coached - with coaching):
{response_b}

Rate each response (1-5) on:
- Relevance: Does it address what was asked?
- Specificity: Does it provide concrete details?
- Clarity: Is it well-organised?
- Completeness: Does it cover all aspects?

Then state your overall winner (A, B, or tie).

Output EXACTLY in this JSON format, no other text:
{{
    "relevance_a": 1-5,
    "relevance_b": 1-5,
    "specificity_a": 1-5,
    "specificity_b": 1-5,
    "clarity_a": 1-5,
    "clarity_b": 1-5,
    "completeness_a": 1-5,
    "completeness_b": 1-5,
    "winner": "A",
    "confidence": "high"
}}
"""

def load_test_prompts():
    """Load your held-out test set (100 prompts)."""
    with open('prompts_dataset.json', 'r') as f:
        data = json.load(f)
    # Take last 100 (or use random sample)
    return data[-TEST_SIZE:]

def generate_standard(prompt):
    """Generate response without coaching."""
    try:
        resp = requests.post(f"{API_URL}/api/prompt/standard", 
                           json={"prompt": prompt}, timeout=30)
        return resp.json().get("response", "")
    except:
        return ""

def generate_coached(prompt):
    """Generate response with coaching."""
    try:
        # Step 1: Analyse
        analysis = requests.post(f"{API_URL}/api/prompt/analyse",
                                json={"prompt": prompt}, timeout=10).json()
        
        session_id = analysis.get("session_id")
        if not session_id:
            return {"refined": prompt, "response": ""}
        
        # Step 2: Answer coaching questions (default answers for automation)
        while analysis.get("needs_coaching"):
            q = analysis.get("next_question")
            if not q:
                break
            
            # Use sensible default answers
            defaults = {
                "audience": "general audience",
                "format": "clear and concise",
                "constraints": "no specific constraints",
                "context": "general purpose"
            }
            answer = defaults.get(q.get("dimension", ""), "general purpose")
            
            analysis = requests.post(f"{API_URL}/api/prompt/answer",
                                   json={"session_id": session_id,
                                        "dimension": q["dimension"],
                                        "answer": answer}, timeout=10).json()
        
        # Step 3: Generate
        result = requests.post(f"{API_URL}/api/prompt/generate",
                              json={"session_id": session_id}, timeout=60).json()
        
        return {
            "refined": result.get("refined_prompt", prompt),
            "response": result.get("humanised_response", "")
        }
    except Exception as e:
        print(f"Error: {e}")
        return {"refined": prompt, "response": ""}

def judge_responses(prompt, resp_a, resp_b):
    """Use LLM to judge both responses."""
    judge_prompt = JUDGE_PROMPT.format(
        prompt=prompt,
        response_a=resp_a or "No response",
        response_b=resp_b or "No response"
    )
    
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate",
                           json={"model": MODEL,
                                "prompt": judge_prompt,
                                "stream": False}, timeout=30)
        
        result_text = resp.json().get("response", "")
        
        # Extract JSON from response
        import re
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"Judge error: {e}")
    
    return None

def main():
    print("=" * 60)
    print("PROMPTAI EVALUATION")
    print("=" * 60)
    
    prompts = load_test_prompts()
    print(f"Loaded {len(prompts)} test prompts\n")
    
    results = []
    
    for i, item in enumerate(prompts):
        prompt = item.get("instruction", item.get("text", ""))
        print(f"[{i+1}/{len(prompts)}] Processing: {prompt[:50]}...")
        
        # Generate both responses
        standard_resp = generate_standard(prompt)
        time.sleep(0.5)  # Rate limiting
        
        coached_result = generate_coached(prompt)
        coached_resp = coached_result["response"]
        refined = coached_result["refined"]
        time.sleep(0.5)
        
        # Judge
        judge_result = judge_responses(prompt, standard_resp, coached_resp)
        
        results.append({
            "prompt": prompt,
            "refined_prompt": refined,
            "standard_response": standard_resp,
            "coached_response": coached_resp,
            "judge_scores": judge_result
        })
        
        time.sleep(0.3)
    
    # Save raw results
    with open('evaluation_results_raw.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "=" * 60)
    print("RAW RESULTS SAVED TO: evaluation_results_raw.json")
    print("=" * 60)
    
    return results

if __name__ == "__main__":
    main()