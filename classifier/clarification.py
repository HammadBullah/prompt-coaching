from pydantic import BaseModel
from typing import List

class ClarificationQuestion(BaseModel):
    dimension: str
    question: str
    example: str = "standard"

def get_clarification_questions(missing_dimensions: List[str]) -> List[ClarificationQuestion]:
    """Return clarification questions for missing dimensions"""
    DIMENSION_QUESTIONS = {
        "Goal": {
            "question": "What is your main goal or intended output?",
            "example": "e.g., Explain the concept, Write a Python function, Generate a business plan..."
        },
        "Audience": {
            "question": "Who is the intended audience for this output?",
            "example": "e.g., university students, software developers, managers, beginners"
        },
        "Format": {
            "question": "What format or structure do you want for the response?",
            "example": "e.g., bullet points, step-by-step guide, table, email, report"
        },
        "Constraints": {
            "question": "Any constraints on length, tone, or style?",
            "example": "e.g., under 300 words, formal tone, friendly and conversational"
        },
        "Context": {
            "question": "Please provide any additional background or context.",
            "example": "e.g., this is for an MSc assignment, user is a beginner in the topic..."
        }
    }
    
    questions = []
    for dim in missing_dimensions:
        q = DIMENSION_QUESTIONS.get(dim, {
            "question": f"Please provide more information about the {dim.lower()} aspect.",
            "example": ""
        })
        questions.append(ClarificationQuestion(
            dimension=dim,
            question=q["question"],
            example=q["example"]
        ))
    return questions