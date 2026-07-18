from pydantic import BaseModel
from typing import List

class ClarificationQuestion(BaseModel):
    dimension: str
    question: str
    example: str = ""

def get_clarification_questions(missing_dimensions: List[str]) -> List[ClarificationQuestion]:
    DIMENSION_QUESTIONS = {
        "goal": {
            "question": "What is your main goal or intended output?",
            "example": "e.g., Explain a concept, Write a Python function, Generate a business plan..."
        },
        "audience": {
            "question": "Who is the intended audience for this output?",
            "example": "e.g., university students, software developers, managers, beginners"
        },
        "format": {
            "question": "What format or structure do you want for the response?",
            "example": "e.g., bullet points, step-by-step guide, table, email, report"
        },
        "constraints": {
            "question": "Any constraints on length, tone, or style?",
            "example": "e.g., under 300 words, formal tone, friendly and conversational"
        },
        "context": {
            "question": "Please provide any additional background or context.",
            "example": "e.g., this is for an MSc assignment, I am a beginner in this topic..."
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
                example=q_data["example"]
            ))
        else:
            questions.append(ClarificationQuestion(
                dimension=dim_key,
                question=f"Could you tell me more about the {dim_key}?",
                example=""
            ))
            
    return questions