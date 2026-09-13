import pandas as pd
import json
import sys
import os
from sklearn.metrics import classification_report

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
from clarification.evaluate_ml_analyzer import predict_missing_dimensions

DATASET_PATH = os.path.join(os.path.dirname(__file__), "prompts_dataset.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "results/rq1_accuracy_results.txt")
ALL_DIMS = ["goal", "audience", "format", "constraints", "context"]

def evaluate_rq1():
    with open(DATASET_PATH, 'r') as f:
        data = json.load(f)
    
    y_true, y_pred = [], []
    print(f"Testing classifier on {len(data)} NEW samples...")

    for item in data:
        prompt = item['instruction']
        expected = item['expected_dimensions']
        
        print(f"   > Processing: {prompt}")
        true_labels = [1 if expected.get(dim, False) else 0 for dim in ALL_DIMS]
        y_true.append(true_labels)

        missing_predicted = [m.lower().strip() for m in predict_missing_dimensions(prompt)]
        pred_labels = [1 if dim not in missing_predicted else 0 for dim in ALL_DIMS]
        y_pred.append(pred_labels)

    report = classification_report(
        y_true, y_pred, 
        target_names=ALL_DIMS, 
        digits=3, 
        zero_division=0
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write("RQ1\n" + "="*45 + "\n" + report)

    print("="*40 + "\nFINAL RQ1 RESULTS\n" + report + "\n" + "="*40)

if __name__ == "__main__":
    evaluate_rq1()