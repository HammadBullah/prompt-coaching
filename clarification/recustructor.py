"""
PromptAI — Prompt Reconstructor Module
Objective 3: Conversational Coaching and Prompt Reconstruction

Refined version: Performs a two-stage reconstruction.
1. String-based structural building (Skeleton)
2. LLM-based linguistic refinement (Expert Prompt)

Student: Hammad Safi | 24145973
"""

import ollama
from typing import Dict, List, Optional

# Constants
OLLAMA_MODEL = "qwen2.5:1.5b"
DIMENSION_ORDER = ["goal", "context", "audience", "format", "constraints"]
ALL_DIMS = ["goal", "audience", "format", "constraints", "context"]

DIMENSION_LABELS = {
    "goal":        "Goal",
    "context":     "Background Context",
    "audience":    "Intended Audience",
    "format":      "Output Format",
    "constraints": "Constraints",
}

def score_prompt(missing_dims: List[str]) -> int:
    """Calculates quality score 0–100 based on dimension presence."""
    missing_lower = [m.lower().strip() for m in missing_dims]
    present = len([d for d in ALL_DIMS if d not in missing_lower])
    return int((present / len(ALL_DIMS)) * 100)

def _build_skeleton(original: str, answers: Dict[str, str]) -> str:
    """Stage 1: Creates a structured multi-line string (The Skeleton)."""
    normalised = {k.lower().strip(): v.strip() for k, v in answers.items() if v and v.strip()}
    
    sections = [f"Task: {original.strip()}"]
    for dim in DIMENSION_ORDER:
        if dim in normalised:
            label = DIMENSION_LABELS[dim]
            sections.append(f"{label}: {normalised[dim]}")
    
    sections.append("Instruction: Provide a complete and direct response.")
    return "\n\n".join(sections)

def _ai_refine(skeleton: str) -> str:
    """Stage 2: Asks Local LLM to professionalize the skeleton into an Expert Prompt."""
    instruction = (
        "You are an expert Prompt Engineer. I will give you a structured set of components. "
        "Rewrite them into one cohesive, professional, and high-performance prompt. "
        "Do NOT answer the prompt. ONLY output the refined prompt text with all the dimenstions strictly following.\n\n"
        f"STRUCTURED COMPONENTS:\n{skeleton}\n\n"
        "REFINED EXPERT PROMPT:"
    )
    
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": instruction}],
            options={"temperature": 0.2} # Low temperature for precision
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"Reconstructor LLM Error: {e}")
        return skeleton # Fallback to skeleton if LLM fails

def reconstruct_prompt(original: str, answers: Dict[str, str], use_ai_refinement: bool = True) -> str:
    """
    The main entry point for Objective 3.
    Builds the skeleton and then (optionally) refines it using the local LLM.
    """
    # 1. Create the structured string
    skeleton = _build_skeleton(original, answers)
    
    if not use_ai_refinement:
        return skeleton
    
    # 2. Let the AI 'reconstruct' it into a better prompt
    return _ai_refine(skeleton)