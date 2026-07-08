import json
import math
import numpy as np
import torch
from datasets import Dataset
from transformers import DistilBertTokenizerFast
from torch import nn
from transformers import DistilBertForSequenceClassification
from sklearn.metrics import f1_score, hamming_loss, accuracy_score, confusion_matrix
from transformers import Trainer
from torch.utils.data import DataLoader
from sklearn.metrics import confusion_matrix
import matplotlib.pyplot as plt


with open("/Users/hammadsafi/Downloads/prompt coaching/dataset/final_dataset.json", "r", encoding="utf-8") as f:
    data = json.load(f)

dataset = Dataset.from_list(data)

with open("/Users/hammadsafi/Downloads/prompt coaching/dataset/final_dataset.json") as f:
    raw_data = json.load(f)

dims = ["goal", "audience", "format", "constraints", "context"]
total = len(raw_data)
counts = [0, 0, 0, 0, 0]

for item in raw_data:
    for i, dim in enumerate(dims):
        counts[i] += int(bool(item["labels"][dim]))

weights = []
print("Class weights:")
weights = []
print("Class weights:")
for i, dim in enumerate(dims):
    pos = counts[i]
    neg = total - pos
    w = round(math.sqrt(neg / pos), 2) if pos > 0 else 1.0
    weights.append(w)
    print(f"  {dim:<14}: pos={pos}, neg={neg}, weight={w}")

class_weights = torch.tensor(weights, dtype=torch.float)

def preprocess(example):
    return {
        "text": example["prompt"],
        "labels": [
            float(example["labels"]["goal"]),
            float(example["labels"]["audience"]),
            float(example["labels"]["format"]),
            float(example["labels"]["constraints"]),
            float(example["labels"]["context"]),
        ]
    }

dataset = dataset.map(preprocess)

dataset = dataset.train_test_split(test_size=0.2, seed=42)

train_ds = dataset["train"]
test_ds = dataset["test"]

tokenizer = DistilBertTokenizerFast.from_pretrained("distilbert-base-uncased")

def tokenize(example):
    tokens = tokenizer(
        example["text"],
        truncation=True,
        padding="max_length",
        max_length=128
    )

    tokens["labels"] = example["labels"]
    return tokens

train_ds = train_ds.map(tokenize)
test_ds = test_ds.map(tokenize)

train_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])
test_ds.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

model = DistilBertForSequenceClassification.from_pretrained(
    "distilbert-base-uncased",
    num_labels=5
)

model.config.problem_type = "multi_label_classification"

device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
model = model.to(device)


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    probs = torch.sigmoid(torch.tensor(logits))
    preds = (probs > 0.5).int().numpy()
    labels = labels.astype(int)
    return {
        "f1_micro": f1_score(labels, preds, average="micro"),
        "f1_macro": f1_score(labels, preds, average="macro"),
    }

from transformers import TrainingArguments

training_args = TrainingArguments(
    output_dir="./results",
    eval_strategy="epoch",
    save_strategy="epoch",
    learning_rate=2e-5,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=16,
    num_train_epochs=8,
    weight_decay=0.01,
    logging_dir="./logs",
    dataloader_pin_memory=False
)

# Calculate class weights from your training data
def compute_class_weights(train_dataset):
    dims = ["goal", "audience", "format", "constraints", "context"]
    counts = [0, 0, 0, 0, 0]
    total = 0

    for item in train_dataset:
        labels = item["labels"]
        
        if isinstance(labels, dict):
            label_list = [float(labels[d]) for d in dims]
        elif hasattr(labels, "tolist"):
            label_list = labels.tolist()
        else:
            label_list = list(labels)
        
        for i, val in enumerate(label_list):
            counts[i] += int(round(float(val)))
        total += 1

    weights = []
    print("Class weights:")
    for i, dim in enumerate(dims):
        pos = counts[i]
        neg = total - pos
        w = neg / pos if pos > 0 else 1.0
        weights.append(w)
        print(f"  {dim:<14}: pos={pos}, neg={neg}, weight={w:.2f}")

    return torch.tensor(weights, dtype=torch.float)

# Custom trainer with weighted loss
class WeightedTrainer(Trainer):
    def __init__(self, class_weights, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights.to(self.model.device)

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=self.class_weights)
        loss = loss_fn(logits, labels.float())
        return (loss, outputs) if return_outputs else loss


train_indices = list(range(len(train_ds)))
train_raw = [raw_data[i] for i in range(int(len(raw_data) * 0.8))]

class_weights = compute_class_weights(train_raw)
print("Class weights:", class_weights)

trainer = WeightedTrainer(
    class_weights=class_weights,
    model=model,
    args=training_args,
    train_dataset=train_ds,
    eval_dataset=test_ds,
    compute_metrics=compute_metrics,
)

trainer.train()

model.save_pretrained("./prompt_classifier")
tokenizer.save_pretrained("./prompt_classifier")


def get_predictions(model, dataset, device):
    model.eval()
    loader = DataLoader(dataset, batch_size=16)
    y_true, y_pred, y_prob = [], [], []
    
    for batch in loader:
        inputs = {
            "input_ids": batch["input_ids"].to(device),
            "attention_mask": batch["attention_mask"].to(device)
        }
        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.sigmoid(logits).cpu()
        preds = (probs > 0.5).int()
        y_true.extend(batch["labels"].int().tolist())
        y_pred.extend(preds.tolist())
        y_prob.extend(probs.tolist())
    
    return np.array(y_true), np.array(y_pred), np.array(y_prob)

y_true, y_pred, y_prob = get_predictions(model, test_ds, device)

print("Hamming Loss:", hamming_loss(y_true, y_pred))
print("F1 Micro:", f1_score(y_true, y_pred, average="micro"))
print("F1 Macro:", f1_score(y_true, y_pred, average="macro"))
print("Exact Match:", accuracy_score(y_true, y_pred))

labels = ["goal", "audience", "format", "constraints", "context"]

plt.bar(labels, np.sum(y_true, axis=0))
plt.title("Label Distribution (Ground Truth)")
plt.show()


x = np.arange(len(labels))

plt.bar(x - 0.2, np.sum(y_true, axis=0), 0.4, label="Actual")
plt.bar(x + 0.2, np.sum(y_pred, axis=0), 0.4, label="Predicted")

plt.xticks(x, labels)
plt.legend()
plt.title("Actual vs Predicted")
plt.show()


f1_per_label = f1_score(y_true, y_pred, average=None)

plt.bar(labels, f1_per_label)
plt.title("F1 per Label")
plt.ylim(0, 1)
plt.show()

for i, label in enumerate(labels):
    cm = confusion_matrix(y_true[:, i], y_pred[:, i])

    print(f"\nConfusion Matrix - {label}")
    print(cm)