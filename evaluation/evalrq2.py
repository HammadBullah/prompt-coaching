import sqlite3
import json
import pandas as pd
import os

DB_PATH = "/Users/hammadsafi/Downloads/prompt coaching/sessions.db"
OUTPUT_PATH = "results/rq2_completeness_results.csv"

def calculate_score(dims_count):
    return int((dims_count / 5) * 100)

def evaluate_rq2():
    if not os.path.exists(DB_PATH):
        print(f"Error: {DB_PATH} not found. Run some sessions in the app first!")
        return

    conn = sqlite3.connect(DB_PATH)
    query = "SELECT session_id, original_prompt, missing_dims, answers, refined_prompt FROM sessions WHERE status='complete'"
    df = pd.read_sql_query(query, conn)
    conn.close()

    results = []

    for _, row in df.iterrows():
        missing = json.loads(row['missing_dims'])
        answers = json.loads(row['answers'])
        
        # Original dimensions = 5 total - missing count
        original_dims_count = 5 - len(missing)
        original_score = calculate_score(original_dims_count)
        
        # Refined dimensions = Original + unique answers provided
        final_dims_count = original_dims_count + len(answers)
        final_score = calculate_score(final_dims_count)
        
        results.append({
            "Session_ID": row['session_id'][:8],
            "Original_Dims": original_dims_count,
            "Original_Score": f"{original_score}%",
            "Final_Dims": final_dims_count,
            "Final_Score": f"{final_score}%",
            "Improvement_Delta": f"+{final_score - original_score}%"
        })

    results_df = pd.DataFrame(results)
    results_df.to_csv(OUTPUT_PATH, index=False)
    
    print("="*40)
    print("RQ2 EVALUATION COMPLETE")
    print(f"File saved to: {OUTPUT_PATH}")
    print(f"Average Improvement: {results_df['Improvement_Delta'].str.replace('%','').astype(int).mean():.1f}%")
    print("="*40)

if __name__ == "__main__":
    evaluate_rq2()
