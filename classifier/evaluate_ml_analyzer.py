import torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification
from typing import List, Dict

model_path = "./prompt_classifier"
tokenizer = DistilBertTokenizerFast.from_pretrained(model_path)
model = DistilBertForSequenceClassification.from_pretrained(model_path)

labels = ["goal", "audience", "format", "constraints", "context"]
thresholds = [0.3, 0.5, 0.5, 0.6, 0.4]

def predict_missing_dimensions(text: str) -> List[str]:
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=512
    )
    
    with torch.no_grad():
        logits = model(**inputs).logits
        probs = torch.sigmoid(logits)[0]
    
    missing = []
    for label, prob, threshold in zip(labels, probs, thresholds):
        if prob.item() < threshold:
            missing.append(label.capitalize())
    
    return missing