import sqlite3
import json
import ollama
import pandas as pd
import os

# Configuration
TEST_MODEL = "qwen2.5:1.5b" 
JUDGE_MODEL = "qwen2.5:1.5b" # Use a larger model here if possible for the final report!
DB_PATH = "/Users/hammadsafi/Downloads/prompt coaching/sessions.db"
OUTPUT_DIR = "results"
OUTPUT_PATH = f"{OUTPUT_DIR}/rq3_win_rate_results.csv"

def get_judge_verdict(prompt: str, resp_a: str, resp_b: str) -> str:
    """
    Asks the Judge LLM to pick a winner between Standard (A) and Coached (B).
    """
    judge_system_prompt = (
        "You are an expert academic judge evaluating AI response quality. "
        "You will see a user's original prompt and two different AI responses.\n\n"
        "Evaluation Criteria:\n"
        "1. Helpfulness: Does the response provide exactly what is needed?\n"
        "2. Detail: Does it follow all context and constraints provided?\n"
        "3. Tone: Is it conversational and coaching-oriented (natural)?\n\n"
        "Rules:\n"
        "- Response A is a direct answer to the vague prompt.\n"
        "- Response B is an answer generated after a coaching process.\n\n"
        "Output ONLY the letter 'A', 'B', or the word 'TIE'."
    )
    
    judge_user_message = (
        f"USER ORIGINAL PROMPT: {prompt}\n\n"
        f"RESPONSE A (Standard):\n{resp_a}\n\n"
        f"RESPONSE B (Coached & Humanised):\n{resp_b}\n\n"
        "WINNER (A/B/TIE):"
    )

    try:
        response = ollama.chat(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": judge_system_prompt},
                {"role": "user", "content": judge_user_message}
            ],
            options={"temperature": 0.1}
        )
        verdict = response["message"]["content"].strip().upper()
        if "B" in verdict and "A" not in verdict: return "B" # Coached Win
        if "A" in verdict and "B" not in verdict: return "A" # Standard Win
        return "TIE"
    except Exception as e:
        print(f"Judging error: {e}")
        return "ERROR"

def evaluate_rq3():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    query = "SELECT original_prompt, refined_prompt, humanised_response FROM sessions WHERE status='complete'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("No completed sessions found in database to evaluate.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results = []
    
    print(f"Evaluating {len(df)} completed sessions...")

    for i, row in df.iterrows():
        print(f"Processing session {i+1}...")
        
        # 1. Generate Standard Response (Uncoached) from original prompt
        try:
            standard_resp_raw = ollama.chat(
                model=TEST_MODEL,
                messages=[{"role": "user", "content": row['original_prompt']}]
            )
            standard_resp = standard_resp_raw["message"]["content"]
        except:
            standard_resp = "Error generating standard response."

        # 2. Get Coached Response from DB (this is already humanised)
        coached_resp = row['humanised_response']

        # 3. Judge
        verdict = get_judge_verdict(row['original_prompt'], standard_resp, coached_resp)

        results.append({
            "Session": i + 1,
            "Verdict": verdict,
            "Standard_Win": 1 if verdict == "A" else 0,
            "Coached_Win": 1 if verdict == "B" else 0,
            "Tie": 1 if verdict == "TIE" else 0
        })

    results_df = pd.DataFrame(results)
    results_df.to_csv(OUTPUT_PATH, index=False)

    print("="*40)
    print("RQ3 EVALUATION COMPLETE")
    print(f"Samples Evaluated: {len(results_df)}")
    print(f"Coached Win Rate: {(results_df['Coached_Win'].sum() / len(results_df)) * 100:.1f}%")
    print(f"Detailed results saved to: {OUTPUT_PATH}")
    print("="*40)

if __name__ == "__main__":
    evaluate_rq3()
