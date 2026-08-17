import torch
import os
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification
from typing import List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
model_path = os.path.join(BASE_DIR, "prompt_classifier")

print(f"--- Loading model from: {model_path} ---")

tokenizer = DistilBertTokenizerFast.from_pretrained(model_path)
model = DistilBertForSequenceClassification.from_pretrained(model_path)

labels = ["goal", "audience", "format", "constraints", "context"]

thresholds = [0.3, 0.4, 0.4, 0.2, 0.3] 

def predict_missing_dimensions(text: str) -> List[str]:
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512
    )
    
    model.eval()
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.sigmoid(logits)[0]
    
    missing = []
    for label, prob, threshold in zip(labels, probs, thresholds):
        if prob.item() < threshold:
            missing.append(label.lower()) # Keep it lowercase for system consistency
            
    return missing


def predict_with_confidence(text: str) -> dict:
    """
    Returns a dictionary mapping each dimension to its prediction (bool)
    and raw confidence score (float).
    """
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512
    )

    model.eval()
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.sigmoid(logits)[0]

    result = {}
    for label, prob, threshold in zip(labels, probs, thresholds):
        # A dimension is 'PRESENT' if its probability meets the threshold
        result[label] = prob.item() >= threshold
        result[f"{label}_confidence"] = prob.item()

    return result
