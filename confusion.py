import torch
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import multilabel_confusion_matrix, classification_report, hamming_loss

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
# IMPORTANT: This order must match how you trained your model
dimensions = ["goal", "audience", "format", "constraints", "context"]
device = torch.device("mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu")

model_path = "./prompt_classifier"  # Path to your saved model folder
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForSequenceClassification.from_pretrained(model_path).to(device)

# ==========================================
# 2. TEST DATASET (51 PROMPTS)
# ==========================================
raw_data = [
    {"prompt": "I graduated last year and have been struggling to find my first job", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": True}},
    {"prompt": "write a press release", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "If a song sings a bird, then what is a book reading?", "labels": {"goal": True, "audience": True, "format": True, "constraints": True, "context": True}},
    {"prompt": "Explain the term 'evidence-based decision-making'.", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": True}},
    {"prompt": "How can a person manage his or her stress levels to improve mental health?", "labels": {"goal": True, "audience": True, "format": False, "constraints": False, "context": False}},
    {"prompt": "write a 3 paragraph introduction for my essay", "labels": {"goal": True, "audience": False, "format": False, "constraints": True, "context": False}},
    {"prompt": "Classify the type of fuel as petrol/diesel for the following list: [0.5 diesel, petrol 2.5 , 2 petrol, 0.75 diesel]", "labels": {"goal": True, "audience": True, "format": True, "constraints": False, "context": True}},
    {"prompt": "Create a list of 5 features that a gym membership should offer.", "labels": {"goal": True, "audience": True, "format": True, "constraints": True, "context": False}},
    {"prompt": "Describe the impact of the internet on the job market in the past 10 years", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Suggest an appropriate replacement for the underlined phrase. The teacher gave the assignment to the whole class, including those in the back benches.", "labels": {"goal": True, "audience": True, "format": True, "constraints": True, "context": True}},
    {"prompt": "Rephrase the given sentence so that it remains as accurate as possible. Coffee beans should be roasted before they can be steeped.", "labels": {"goal": False, "audience": False, "format": True, "constraints": True, "context": True}},
    {"prompt": "Gather some recent data related to the increasing rates of unemployment.", "labels": {"goal": False, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Hola, escribe en español por favor", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": True}},
    {"prompt": "Describe how Machine Learning algorithms can lead to better decision making.", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Generate a unique business name.", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Tell me  how a medieval village in England was controlled or ruled by the local lord, was there some kind of supervisor?", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": True}},
    {"prompt": "make something cool", "labels": {"goal": False, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Given the given sentence, rewrite it in the active voice. This task has been completed by me.", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": True}},
    {"prompt": "write a 2 minute speech on leadership", "labels": {"goal": True, "audience": False, "format": False, "constraints": True, "context": False}},
    {"prompt": "draft an email to my manager requesting time off work", "labels": {"goal": True, "audience": True, "format": True, "constraints": False, "context": False}},
    {"prompt": "create a pros and cons list of working from home", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": False}},
    {"prompt": "Use the input to generate three sentences that could fit in the following context I wanted to go on a picnic with my friends", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": True}},
    {"prompt": "What is the major difference between TCP and UDP?", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "what the difference between intermediate and final goods, please provide examples", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": True}},
    {"prompt": "create a checklist for moving to a new house", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": False}},
    {"prompt": "Paraphrase the following sentence: I want to buy a car.", "labels": {"goal": False, "audience": False, "format": True, "constraints": False, "context": True}},
    {"prompt": "Provide an example of a financial tool that is used to identify returns on an investment.", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Detect any evidence of gender-biased language in the following sentence and suggest an alternative if necessary. The firefighter and nurse worked together to save the patient.", "labels": {"goal": True, "audience": True, "format": True, "constraints": False, "context": True}},
    {"prompt": "write a bio for my Twitter profile", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": False}},
    {"prompt": "Name three characteristics commonly associated with a strong leader.", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "create a recipe card for chocolate brownies", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": False}},
    {"prompt": "Perform sentiment analysis and produce a label indicating whether the sentiment of given sentence is positive, negative, or neutral. I'm so excited!", "labels": {"goal": True, "audience": False, "format": True, "constraints": True, "context": True}},
    {"prompt": "Provide a real-world example of the following concept. Natural selection", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": True}},
    {"prompt": "Given a sentence, output the word count. I wanted to go to the beach.", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": True}},
    {"prompt": "explain this to me", "labels": {"goal": False, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "write a sales pitch", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "draft a refund request email to an online retailer", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": False}},
    {"prompt": "Create a graphic representation of a dichotomous key.", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": False}},
    {"prompt": "calcula la mediana de followers...", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "write a casual 80 word birthday message...", "labels": {"goal": True, "audience": True, "format": True, "constraints": True, "context": False}},
    {"prompt": "the current monarch of UK?", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "create a budget plan", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Edit the following text for clarity...", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": True}},
    {"prompt": "Specify the ideal temperature...", "labels": {"goal": False, "audience": False, "format": False, "constraints": False, "context": True}},
    {"prompt": "explain artificial intelligence", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Analyze the given data...", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": True}},
    {"prompt": "our restaurant just opened downtown...", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": True}},
    {"prompt": "write a press release for journalists...", "labels": {"goal": True, "audience": True, "format": True, "constraints": False, "context": False}},
    {"prompt": "Name an animal that is commonly kept as a pet.", "labels": {"goal": True, "audience": False, "format": False, "constraints": False, "context": False}},
    {"prompt": "Assign the following class name to the object...", "labels": {"goal": True, "audience": False, "format": True, "constraints": False, "context": True}},
    {"prompt": "Write a clear patient information leaflet...", "labels": {"goal": True, "audience": True, "format": True, "constraints": True, "context": True}},
]

# ==========================================
# 3. DATA PROCESSING
# ==========================================
test_prompts = [item['prompt'] for item in raw_data]

# Binary Matrix Mapping
true_labels = np.array([
    [int(item['labels']['goal']), 
     int(item['labels']['audience']), 
     int(item['labels']['format']), 
     int(item['labels']['constraints']), 
     int(item['labels']['context'])] 
    for item in raw_data
])

# ==========================================
# 4. BATCH INFERENCE
# ==========================================
model.eval()
with torch.no_grad():
    inputs = tokenizer(test_prompts, return_tensors="pt", truncation=True, padding=True).to(device)
    outputs = model(**inputs)
    probs = torch.sigmoid(outputs.logits).cpu().numpy()
    all_preds = (probs > 0.5).astype(int)

# ==========================================
# 5. METRICS REPORT
# ==========================================
print("Multi-Label Performance Report:\n")
print(classification_report(true_labels, all_preds, target_names=dimensions))
print(f"Hamming Loss: {hamming_loss(true_labels, all_preds):.4f}")

# ==========================================
# 6. PROFESSIONAL HEATMAPS
# ==========================================
mcm = multilabel_confusion_matrix(true_labels, all_preds)

sns.set_theme(style="white")
fig, axes = plt.subplots(1, 5, figsize=(30, 6))
colors = ["Blues", "Greens", "Oranges", "Reds", "Purples"]

for i, (matrix, ax) in enumerate(zip(mcm, axes)):
    # Calculate group annotations (Count + %)
    group_counts = ["{0:0.0f}".format(value) for value in matrix.flatten()]
    group_percentages = ["({0:.1%})".format(value) for value in matrix.flatten()/np.sum(matrix)]
    labels_text = [f"{v1}\n{v2}" for v1, v2 in zip(group_counts, group_percentages)]
    labels_text = np.asarray(labels_text).reshape(2, 2)
    
    # Plotting
    sns.heatmap(matrix, annot=labels_text, fmt="", cmap=colors[i], ax=ax, cbar=False,
                xticklabels=[f"No {dimensions[i]}", dimensions[i]],
                yticklabels=[f"No {dimensions[i]}", dimensions[i]],
                annot_kws={"size": 13, "weight": "bold"})
    
    ax.set_title(f'Dimension: {dimensions[i].upper()}', fontsize=16, pad=20, weight='bold')
    ax.set_xlabel('Predicted', fontsize=12)
    ax.set_ylabel('Actual', fontsize=12)
    
    # Add borders to heatmaps
    for _, spine in ax.spines.items():
        spine.set_visible(True)
        spine.set_color('#cccccc')

plt.suptitle("Prompt Coaching Model: Multi-Label Evaluation Suite", fontsize=24, y=1.1, weight='bold')
plt.tight_layout()
plt.show()