"""
PromptAI — Humanisation Module (Rule-Based Only)
Objective 4: Humanising AI Responses through Linguistic Transformation

Academic Foundation:
1. Liebrecht, C., et al. (2021). "Linguistic elements of conversational human voice 
   in online brand communication: Manipulations and perceptions."
2. Liebrecht, C., et al. (2021). "Too Informal? How a Chatbot’s Communication 
   Style Affects Brand Attitude and Quality of Interaction."
"""

import re
import random
from typing import Dict, List

# 1. MESSAGE PERSONALIZATION & CONTRACTIONS
PERSONALIZATION_MAP = {
    r"\bit is\b": "it's",
    r"\byou are\b": "you're",
    r"\bdo not\b": "don't",
    r"\bcannot\b": "can't",
    r"\bwe are\b": "we're",
    r"\bthat is\b": "that's",
    r"\bthere is\b": "there's",
    r"\bI am\b": "I'm",
    r"\bwill not\b": "won't",
    r"\bthey are\b": "they're",
}

# 2. INFORMAL SPEECH (Lexical Shift: Latinate -> Germanic)
PHRASAL_VERB_MAP = {
    r"\butilise\b": "use",
    r"\bcommence\b": "start",
    r"\bterminate\b": "end",
    r"\bendeavour\b": "try",
    r"\bdemonstrate\b": "show",
    r"\bobtain\b": "get",
    r"\bretain\b": "keep",
    r"\bpurchase\b": "buy",
    r"\badditional\b": "extra",
    r"\bsubsequently\b": "after that",
    r"\bpertinent\b": "relevant",
    r"\bfacilitate\b": "help",
    r"\brequire\b": "need",
}

# 3. INVITATIONAL RHETORIC & TRANSITIONS
TRANSITION_MAP = {
    r"\bIn conclusion\b": "So",
    r"\bFurthermore\b": "Also",
    r"\bMoreover\b": "Plus",
    r"\bIn addition\b": "Additionally",
    r"\bTherefore\b": "That's why",
    r"\bConsequently\b": "As a result",
}
EXPANDED_HUMAN_MAP = {
    # Vocabulary (Latinate -> Germanic)
    r"\bpivotal\b": "really important",
    r"\badvancing\b": "moving forward",
    r"\bfoundational\b": "basic",
    r"\bunderstanding this concept\b": "getting a handle on this",
    
    # Structure (Softening the "AI list" feel)
    r"\b1\. Supervised Learning:\b": "First, let's look at Supervised Learning:",
    r"\bDefinition:\b": "Basically,",
    r"\bTypes:\b": "This usually covers",
}

# CONTEXTUAL HEDGING (Softening authoritative tone)
HEDGING_RULES = {
    r"\bThe first step involves\b": "I usually start by",
    r"\bIt is essential to\b": "You might want to",
    r"\bThe goal is to\b": "What we're looking to do is",
}

# WELL-WISHING CLOSINGS
WELL_WISHING = [
    "Have a great day!",
    "Hope this helps you out!",
    "Enjoy exploring this topic!",
    "Let me know if you have more questions!",
]

class LinguisticHumaniser:
    def _apply_heuristic_rules(self, text: str) -> str:
        processed = text
        
        # 1. Apply Hedging & Softeners
        for pattern, replacement in HEDGING_RULES.items():
            processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)

        # 2. Apply all linguistic maps
        all_rules = {**PERSONALIZATION_MAP, **PHRASAL_VERB_MAP, **TRANSITION_MAP, **EXPANDED_HUMAN_MAP}
        for pattern, replacement in all_rules.items():
            processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)
        
        # 3. Prosody Control: Break long sentences
        sentences = re.split(r'(?<=[.!?])\s+', processed)
        varied_sentences = []
        for s in sentences:
            if len(s.split()) > 25 and ", and " in s:
                parts = s.split(", and ", 1)
                varied_sentences.append(f"{parts[0]}. And {parts[1]}")
            else:
                varied_sentences.append(s)
        
        processed = " ".join(varied_sentences)
        
        # 4. Add Well-wishing closing
        if not any(w.lower() in processed.lower() for w in WELL_WISHING):
            processed = processed.strip()
            if not processed.endswith(('.', '!', '?')): processed += "."
            processed += f" {random.choice(WELL_WISHING)}"
            
        return processed

    def humanise(self, text: str) -> Dict[str, any]:
        final_text = self._apply_heuristic_rules(text)
        return {
            "original": text,
            "humanised": final_text,
            "method": "CHV-Taxonomy-Heuristic-Only"
        }