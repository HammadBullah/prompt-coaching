# clarification.py
from pydantic import BaseModel
from typing import List, Optional
import re

class ClarificationQuestion(BaseModel):
    dimension: str
    question: str
    example: str = ""
    priority: int = 0


class CoachingDecision(BaseModel):
    needs_coaching: bool
    reason: str
    questions: List[ClarificationQuestion]
    quality_score: float  # ← This was missing


class SmartClarifier:
    """Smart clarification logic - decides WHEN and WHAT to ask"""
    
    def __init__(self):
        self.priority_map = {
            "audience": 1,
            "format": 2,
            "constraints": 3,
            "context": 4
        }
        self.min_confidence_ask = 0.5
        self.min_words_for_coaching = 3
        self.max_questions = 4
    
    def should_coach(
        self, 
        prompt: str, 
        analysis: dict,
        humanizer_score: Optional[float] = None
    ) -> CoachingDecision:
        
        if self._is_trivial(prompt):
            quality_score = self._calculate_quality_score(analysis)
            return CoachingDecision(
                needs_coaching=False,
                reason="Trivial input - direct response generated",
                questions=[],
                quality_score=quality_score  # ← Added
            )
        
        if self._is_comprehensive(prompt):
            quality_score = self._calculate_quality_score(analysis)
            return CoachingDecision(
                needs_coaching=False,
                reason="Prompt is well-structured",
                questions=[],
                quality_score=quality_score  # ← Added
            )
        
        # Rule 3: Skip if quality score is already high
        if humanizer_score and humanizer_score >= 80:
            return CoachingDecision(
                needs_coaching=False,
                reason="High prompt quality detected",
                questions=[],
                quality_score=humanizer_score  # ← Added
            )
        
        questions_to_ask = self._get_smart_questions(analysis)
        quality_score = self._calculate_quality_score(analysis)
        
        if not questions_to_ask:
            return CoachingDecision(
                needs_coaching=False,
                reason="No clarification needed",
                questions=[],
                quality_score=quality_score
            )
        
        return CoachingDecision(
            needs_coaching=True,
            reason=f"Coaching needed - {len(questions_to_ask)} dimension(s) to clarify",
            questions=questions_to_ask,
            quality_score=quality_score
        )
    
    def _is_trivial(self, prompt: str) -> bool:
        prompt_lower = prompt.lower().strip()
        words = prompt_lower.split()
        word_count = len(words)
        
        trivial_words = {
            'hi', 'hey', 'hello', 'hiya', 'yo',
            'thanks', 'thank', 'thankyou',
            'bye', 'goodbye', 'ciao',
            'ok', 'okay', 'yes', 'no', 'sure',
            'maybe', 'perhaps',
            'help', 'please',
            'wtf', 'omg', 'lol', 'haha', 'lmao', 'rofl', 'brb', 'ttyl', 'idk', 'smh', 
            'how are you', 'what\'s up', 'whats up', 'sup', 'wazzup', 'yo', 'hey there', 'hi there'
        }
        
        if prompt_lower in trivial_words:
            return True
        
        if word_count == 1:
            return True
        
        if word_count < 3:
            intent_words = {'write', 'explain', 'tell', 'make', 'create', 
                          'give', 'show', 'find', 'get', 'need'}
            if not any(w in prompt_lower for w in intent_words):
                return True
        
        if re.match(r'^[\W\d]+$', prompt):
            return True
        
        return False
    
    def _is_comprehensive(self, prompt: str) -> bool:
        words = prompt.split()
        word_count = len(words)
        
        if word_count < 8:
            return False
        
        indicator_keywords = {
            "goal": ['write', 'explain', 'describe', 'analyze', 'create', 
                    'help', 'make', 'tell', 'show', 'give', 'generate'],
            "audience": ['for', 'to', 'audience', 'beginner', 'expert', 'student',
                        'developer', 'manager', 'reader', 'who'],
            "format": ['format', 'list', 'table', 'paragraph', 'email', 'report',
                      'bullet', 'step', 'outline', 'structure', 'number'],
            "constraints": ['without', 'must', 'need', 'only', 'avoid', 
                           'limit', 'max', 'min', 'under', 'over'],
            "context": ['because', 'since', 'while', 'currently', 'situation',
                       'background', 'context', 'im']
        }
        
        satisfied = 0
        for dim, keywords in indicator_keywords.items():
            if any(kw in prompt.lower() for kw in keywords):
                satisfied += 1
        
        return satisfied >= 4 or (word_count >= 20 and satisfied >= 2)
    
    def _get_smart_questions(self, analysis: dict) -> List[ClarificationQuestion]:
        missing_with_low_confidence = []
        
        for dim, confidence_key in [
            ("goal", "goal_confidence"),
            ("audience", "audience_confidence"),
            ("format", "format_confidence"),
            ("constraints", "constraints_confidence"),
            ("context", "context_confidence")
        ]:
            if not analysis.get(dim, False):
                confidence = analysis.get(confidence_key, 0.5)
                if confidence < self.min_confidence_ask or dim == "goal":
                    missing_with_low_confidence.append({
                        "dimension": dim,
                        "confidence": confidence
                    })
        
        missing_with_low_confidence.sort(
            key=lambda x: self.priority_map.get(x["dimension"], 99)
        )
        
        missing_with_low_confidence = missing_with_low_confidence[:self.max_questions]
        
        return get_clarification_questions(
            [item["dimension"] for item in missing_with_low_confidence]
        )
    
    def _calculate_quality_score(self, analysis: dict) -> float:
        dimensions = ["goal", "audience", "format", "constraints", "context"]
        satisfied = sum(1 for d in dimensions if analysis.get(d, False))
        return (satisfied / len(dimensions)) * 100


def get_clarification_questions(missing_dimensions: List[str]) -> List[ClarificationQuestion]:
    
    DIMENSION_QUESTIONS = {
        "goal": {
            "question": "What is your main goal or intended output?",
            "example": "e.g., Explain a concept, Write a Python function, Generate a business plan...",
            "priority": 1
        },
        "audience": {
            "question": "Who is the intended audience for this output?",
            "example": "e.g., university students, software developers, managers, beginners",
            "priority": 2
        },
        "format": {
            "question": "What format or structure do you want for the response?",
            "example": "e.g., bullet points, step-by-step guide, table, email, report",
            "priority": 3
        },
        "constraints": {
            "question": "Any constraints on length, tone, or style?",
            "example": "e.g., under 300 words, formal tone, friendly and conversational",
            "priority": 4
        },
        "context": {
            "question": "Please provide any additional background or context.",
            "example": "e.g., this is for an MSc assignment, I am a beginner in this topic...",
            "priority": 5
        }
    }
    
    questions = []
    
    for dim in missing_dimensions:
        dim_key = dim.lower().strip()
        q_data = DIMENSION_QUESTIONS.get(dim_key)
        
        if q_data:
            questions.append(ClarificationQuestion(
                dimension=dim_key,
                question=q_data["question"],
                example=q_data.get("example", ""),
                priority=q_data.get("priority", 99)
            ))
        else:
            questions.append(ClarificationQuestion(
                dimension=dim_key,
                question=f"Could you tell me more about the {dim_key}?",
                example="",
                priority=99
            ))
    
    questions.sort(key=lambda x: x.priority)
    return questions