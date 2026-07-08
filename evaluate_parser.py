import json
import sys
import os

BACKEND_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND_PATH)

from parser import analyse_prompt

DIMENSIONS = ["goal", "audience", "format", "constraints", "context"]
LABELLED_FILE = "/Users/hammadsafi/Downloads/adaptive_prompt_coaching/dataset/final_dataset.json"
RESULTS_FILE = "evaluation_results.json"


def load_labelled_data(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def evaluate(data):
    stats = {dim: {"tp": 0, "tn": 0, "fp": 0, "fn": 0} for dim in DIMENSIONS}
    total_correct = 0
    total_predictions = 0
    misclassified_examples = []

    for item in data:
        prompt = item["prompt"]
        true_labels = item["labels"]

        if any(v is None for v in true_labels.values()):
            continue

        result = analyse_prompt(prompt)
        predicted = result["analysis"]

        for dim in DIMENSIONS:
            true_val = true_labels[dim]
            pred_val = predicted[dim]

            total_predictions += 1
            if true_val == pred_val:
                total_correct += 1

            if true_val and pred_val:
                stats[dim]["tp"] += 1
            elif not true_val and not pred_val:
                stats[dim]["tn"] += 1
            elif not true_val and pred_val:
                stats[dim]["fp"] += 1
            elif true_val and not pred_val:
                stats[dim]["fn"] += 1

            if true_val != pred_val:
                misclassified_examples.append({
                    "id": item["id"],
                    "prompt": prompt[:80] + ("..." if len(prompt) > 80 else ""),
                    "dimension": dim,
                    "true": true_val,
                    "predicted": pred_val
                })

    dimension_results = {}
    for dim in DIMENSIONS:
        tp, tn, fp, fn = stats[dim]["tp"], stats[dim]["tn"], stats[dim]["fp"], stats[dim]["fn"]
        total = tp + tn + fp + fn

        accuracy = (tp + tn) / total if total > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

        dimension_results[dim] = {
            "accuracy": round(accuracy * 100, 1),
            "precision": round(precision * 100, 1),
            "recall": round(recall * 100, 1),
            "f1_score": round(f1 * 100, 1),
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn,
        }

    overall_accuracy = (total_correct / total_predictions * 100) if total_predictions > 0 else 0

    return {
        "overall_accuracy": round(overall_accuracy, 1),
        "total_prompts_evaluated": len(data),
        "total_predictions": total_predictions,
        "per_dimension": dimension_results,
        "misclassified_examples": misclassified_examples
    }


def print_report(results):
    print("=" * 60)
    print("PROMPT ANALYSER EVALUATION RESULTS")
    print("=" * 60)
    print(f"\nPrompts evaluated: {results['total_prompts_evaluated']}")
    print(f"Overall Accuracy: {results['overall_accuracy']}%\n")

    print(f"{'Dimension':<14}{'Accuracy':<11}{'Precision':<11}{'Recall':<10}{'F1':<8}")
    print("-" * 54)
    for dim, m in results["per_dimension"].items():
        print(f"{dim:<14}{m['accuracy']:<11}{m['precision']:<11}{m['recall']:<10}{m['f1_score']:<8}")

    print(f"\nTotal misclassifications: {len(results['misclassified_examples'])}")

    dim_errors = {}
    for ex in results["misclassified_examples"]:
        dim_errors[ex["dimension"]] = dim_errors.get(ex["dimension"], 0) + 1

    print("\nMisclassifications per dimension:")
    for dim, count in sorted(dim_errors.items(), key=lambda x: -x[1]):
        print(f"  {dim:<14}: {count}")

    print("\nSample misclassified prompts (first 10):")
    for ex in results["misclassified_examples"][:10]:
        print(f"  [{ex['dimension']}] true={ex['true']}, predicted={ex['predicted']}")
        print(f"     \"{ex['prompt']}\"")


def main():
    if not os.path.exists(LABELLED_FILE):
        print(f"❌ Could not find {LABELLED_FILE}")
        print("Make sure labelled_dataset.json is in the same folder as this script.")
        return

    data = load_labelled_data(LABELLED_FILE)
    print(f"Loaded {len(data)} labelled prompts\n")

    results = evaluate(data)
    print_report(results)

    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Full results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()