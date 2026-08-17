import re
import random
from typing import Dict, List

import requests
import json

class LLMPolisher:
    def __init__(self, model: str = "qwen2.5:1.5b", ollama_url: str = "http://127.0.0.1:11434"):
        self.model = model
        self.ollama_url = ollama_url
    
    def polish(self, text: str) -> str:
        """
        Rewrite AI text to sound more human/conversational.
        """
        
        polish_prompt = f"""You are rewriting AI-generated text to sound more natural 
and conversational, like a helpful human friend.

RULES:
- Keep the same meaning and information
- Use contractions (don't, it's, you're, etc.)
- Prefer simple words over complex ones
- Sound warm and friendly, not robotic
- Keep it natural, like chatting with a knowledgeable friend
- Remove any overly formal or academic phrasing

TEXT TO REWRITE:
{text}

Rewrite this text to sound natural and conversational:"""

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": polish_prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "top_p": 0.9
                    }
                },
                timeout=60
            )
            
            result = response.json()
            polished = result.get("response", "").strip()
            
            # Fallback to original if polish fails
            return polished if polished else text
            
        except Exception as e:
            print(f"LLM Polish failed: {e}")
            return text
    
    def polish_with_context(self, text: str, context: str = "") -> str:
        """
        Polish with additional context about tone/style.
        """
        
        context_instruction = ""
        if context == "academic":
            context_instruction = "Keep it informative but avoid excessive formality."
        elif context == "casual":
            context_instruction = "Make it super casual and friendly."
        elif context == "professional":
            context_instruction = "Keep it professional but still approachable."
        
        polish_prompt = f"""Rewrite this text to sound natural and conversational.
{context_instruction}

TEXT:
{text}

Rewrite naturally:"""

        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": polish_prompt,
                    "stream": False
                },
                timeout=60
            )
            
            return response.json().get("response", "").strip()
            
        except Exception as e:
            print(f"LLM Polish failed: {e}")
            return text

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

TRANSITION_MAP = {
    r"\bIn conclusion\b": "So",
    r"\bFurthermore\b": "Also",
    r"\bMoreover\b": "Plus",
    r"\bIn addition\b": "Additionally",
    r"\bTherefore\b": "That's why",
    r"\bConsequently\b": "As a result",
}
EXPANDED_HUMAN_MAP = {
    r"\bpivotal\b": "really important",
    r"\badvancing\b": "moving forward",
    r"\bfoundational\b": "basic",
    r"\butilising\b": "using",
    r"\butilise\b": "use",
    
    r"\bThis approach aims to\b": "This should help you",
    r"\bI'll emphasize the importance of\b": "I'll touch on why",
    r"\bethical considerations in\b": "ethics when building",
    r"\bThroughout\b": "As we go through this",
    r"\bSuch as\b": "like",
    r"\bIn order to\b": "to",
    r"\bIn terms of\b": "when it comes to",
    r"\bIn particular\b": "especially",
    r"\bIn this context\b": "here",
    r"\bThe key takeaway\b": "So the main thing",
    r"\bIt should be noted that\b": "Just so you know",
    r"\bAs mentioned earlier\b": "Like I said",
    r"\bIt is worth noting that\b": "It's worth knowing",
    r"\bWith that said\b": "That said",
    r"\bDue to the fact that\b": "Because",
    r"\bOn the other hand\b": "But",
    
    r"\b1\. Supervised Learning:\b": "First, let's look at Supervised Learning:",
    r"\bDefinition:\b": "Basically,",
    r"\bTypes:\b": "This usually covers",
    r"\bClassification:\b": "Classification is when:",
    r"\bRegression:\b": "Regression is when:",
}

HEDGING_RULES = {
    r"\bThe first step involves\b": "I usually start by",
    r"\bIt is essential to\b": "You might want to",
    r"\bThe goal is to\b": "What we're looking to do is",
}

WELL_WISHING = [
    "Have a great day!",
    "Hope this helps you out!",
    "Enjoy exploring this topic!",
    "Let me know if you have more questions!",
]

class LinguisticHumaniser:
    def apply_heuristic_rules(self, text: str) -> str:
        processed = text
        
        for pattern, replacement in HEDGING_RULES.items():
            processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)

        all_rules = {**PERSONALIZATION_MAP, **PHRASAL_VERB_MAP, **TRANSITION_MAP, **EXPANDED_HUMAN_MAP}
        for pattern, replacement in all_rules.items():
            processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)
        
        sentences = re.split(r'(?<=[.!?])\s+', processed)
        varied_sentences = []
        for s in sentences:
            if len(s.split()) > 25 and ", and " in s:
                parts = s.split(", and ", 1)
                varied_sentences.append(f"{parts[0]}. And {parts[1]}")
            else:
                varied_sentences.append(s)
        
        processed = " ".join(varied_sentences)
        
        if not any(w.lower() in processed.lower() for w in WELL_WISHING):
            processed = processed.strip()
            if not processed.endswith(('.', '!', '?')): processed += "."
            processed += f" {random.choice(WELL_WISHING)}"
            
        return processed

    def humanise(self, text: str) -> Dict[str, any]:
        final_text = self.apply_heuristic_rules(text)
        return {
            "original": text,
            "humanised": final_text,
            "method": "CHV-Taxonomy-Heuristic-Only"
        }
        
class HumanizationPipeline:

    def __init__(self):
        self.llm_polisher = LLMPolisher()
        self.linguistic_humaniser = LinguisticHumaniser()
    
    def humanize(self, llm_response: str) -> Dict[str, any]:
    
        
        llm_polished = self.llm_polisher.polish(llm_response)
        
        rule_humanised = self.linguistic_humaniser.apply_heuristic_rules(llm_polished)
        
        return {
            "stage_1_llm_polished": llm_polished,
            "stage_2_rule_humanised": rule_humanised,
            "final_output": rule_humanised,
            "stats": {
                "original_length": len(llm_response),
                "after_llm_polish": len(llm_polished),
                "final_length": len(rule_humanised),
                "stages_completed": 2
            },
            "method": "LLM-Polish → Rule-Based"
        }
    
    def humanize_quick(self, llm_response: str) -> str:

        return self.linguistic_humaniser.apply_heuristic_rules(llm_response)
    
    def humanize_llm_only(self, llm_response: str) -> str:
  
        return self.llm_polisher.polish(llm_response)