import torch
from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

model_path = "./prompt_classifier"

tokenizer = DistilBertTokenizerFast.from_pretrained(model_path)
model = DistilBertForSequenceClassification.from_pretrained(model_path)

labels = ["goal", "audience", "format", "constraints", "context"]

def predict(text):
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        padding=True
    )

    with torch.no_grad():
        logits = model(**inputs).logits

    probs = torch.sigmoid(logits)[0]

    thresholds = [0.3, 0.5, 0.5, 0.6, 0.4]

    results = {}

    for label, prob, threshold in zip(labels, probs, thresholds):
        results[label] = {
            "probability": round(prob.item(), 4),
            "predicted": prob.item() >= threshold
        }

    return results

print(predict("Explain cloud computing using language suitable for a child."))