# statistical_analysis.py

import json
import numpy as np
from scipy import stats

# Load results
with open('evaluation_results_raw.json', 'r') as f:
    results = json.load(f)

# Extract scores
metrics = {
    "standard": {"relevance": [], "specificity": [], "clarity": [], "completeness": []},
    "coached": {"relevance": [], "specificity": [], "clarity": [], "completeness": []}
}

winners = {"A": 0, "B": 0, "tie": 0}

for item in results:
    scores = item.get("judge_scores", {})
    if not scores:
        continue
    
    for metric in ["relevance", "specificity", "clarity", "completeness"]:
        metrics["standard"][metric].append(scores.get(f"{metric}_a", 0))
        metrics["coached"][metric].append(scores.get(f"{metric}_b", 0))
    
    winners[scores.get("winner", "tie")] += 1

# Calculate statistics
print("=" * 70)
print("COMPARATIVE EVALUATION RESULTS")
print("=" * 70)

n = len(results)
print(f"\n📊 Total prompts evaluated: {n}")

print(f"\n🏆 WIN RATE:")
print(f"   Standard (A):  {winners['A']:3d} ({100*winners['A']/n:5.1f}%)")
print(f"   Coached  (B):  {winners['B']:3d} ({100*winners['B']/n:5.1f}%)")
print(f"   Tie:           {winners['tie']:3d} ({100*winners['tie']/n:5.1f}%)")

print("\n" + "-" * 70)
print(f"{'Metric':<15} {'Standard (Mean±SD)':<20} {'Coached (Mean±SD)':<20} {'p-value':<12} {'Sig?':<6}")
print("-" * 70)

effect_sizes = {}

for metric in ["relevance", "specificity", "clarity", "completeness"]:
    std = np.array(metrics["standard"][metric])
    coh = np.array(metrics["coached"][metric])
    
    std_mean, std_std = np.mean(std), np.std(std)
    coh_mean, coh_std = np.mean(coh), np.std(coh)
    
    # Wilcoxon signed-rank test (paired, non-parametric)
    try:
        stat, p_value = stats.wilcoxon(std, coh)
    except:
        p_value = 1.0
    
    sig = "✓" if p_value < 0.05 else "✗"
    
    # Cohen's d effect size
    diff = coh_mean - std_mean
    pooled_std = np.sqrt((np.std(std)**2 + np.std(coh)**2) / 2)
    cohens_d = diff / pooled_std if pooled_std > 0 else 0
    effect_sizes[metric] = cohens_d
    
    print(f"{metric.capitalize():<15} {std_mean:.2f}±{std_std:.2f}           {coh_mean:.2f}±{coh_std:.2f}           {p_value:<12.4f} {sig:<6}")

# Overall score comparison
overall_std = []
overall_coh = []
for metric in ["relevance", "specificity", "clarity", "completeness"]:
    overall_std.extend(metrics["standard"][metric])
    overall_coh.extend(metrics["coached"][metric])

overall_std = np.array(overall_std)
overall_coh = np.array(overall_coh)

print("-" * 70)
print(f"{'Overall':<15} {np.mean(overall_std):.2f}±{np.std(overall_std):.2f}           {np.mean(overall_coh):.2f}±{np.std(overall_coh):.2f}")

stat, p_value = stats.wilcoxon(overall_std, overall_coh)
print(f"\nOverall Statistical Significance: p = {p_value:.6f} {'✓' if p_value < 0.05 else '✗'}")

# Effect size interpretation
print("\n📐 EFFECT SIZES (Cohen's d):")
for metric, d in effect_sizes.items():
    if abs(d) < 0.2:
        size = "negligible"
    elif abs(d) < 0.5:
        size = "small"
    elif abs(d) < 0.8:
        size = "medium"
    else:
        size = "large"
    print(f"   {metric.capitalize()}: {d:+.3f} ({size})")

# Calculate win rate statistical significance (binomial test)
from scipy.stats import binom_test
# Expected win rate if no difference = 50%
# Observed wins = winners['B']
try:
    p_binomial = binom_test(winners['B'], n - winners['tie'], 0.5)
    print(f"\n📈 Win Rate Significance (binomial test): p = {p_binomial:.6f} {'✓' if p_binomial < 0.05 else '✗'}")
except:
    pass

print("\n" + "=" * 70)