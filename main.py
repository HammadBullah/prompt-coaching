
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import ollama
import sqlite3
import uuid
import json
import re
import os

from clarification.evaluate_ml_analyzer import predict_missing_dimensions
from clarification.clarification import get_clarification_questions, ClarificationQuestion
from clarification.recustructor import reconstruct_prompt, score_prompt, ALL_DIMS

app = FastAPI(
    title="PromptAI",
    description="Adaptive Prompt Coaching and Humanised AI Responses",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_MODEL = "qwen2.5:1.5b"




DB_PATH = os.path.join(os.path.dirname(__file__), "sessions.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id      TEXT PRIMARY KEY,
            original_prompt TEXT,
            missing_dims    TEXT,
            answers         TEXT DEFAULT '{}',
            refined_prompt  TEXT,
            status          TEXT DEFAULT 'clarifying',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def db_create_session(session_id: str, prompt: str, missing: list):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO sessions (session_id, original_prompt, missing_dims) VALUES (?,?,?)",
        (session_id, prompt, json.dumps(missing))
    )
    conn.commit()
    conn.close()


def db_get_session(session_id: str) -> Optional[dict]:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT session_id, original_prompt, missing_dims, answers, refined_prompt, status "
        "FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "session_id":     row[0],
        "original_prompt": row[1],
        "missing_dims":   json.loads(row[2]),
        "answers":        json.loads(row[3]),
        "refined_prompt": row[4],
        "status":         row[5],
    }


def db_save_answer(session_id: str, dimension: str, answer: str):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT answers FROM sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    if row:
        answers = json.loads(row[0])
        answers[dimension] = answer
        conn.execute(
            "UPDATE sessions SET answers=? WHERE session_id=?",
            (json.dumps(answers), session_id)
        )
        conn.commit()
    conn.close()


def db_save_refined(session_id: str, refined: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE sessions SET refined_prompt=?, status='complete' WHERE session_id=?",
        (refined, session_id)
    )
    conn.commit()
    conn.close()


@app.on_event("startup")
async def startup():
    init_db()


 
class AnalyseRequest(BaseModel):
    prompt: str

class AnswerRequest(BaseModel):
    session_id: str
    dimension: str
    answer: str

class GenerateRequest(BaseModel):
    session_id: str

class StandardRequest(BaseModel):
    prompt: str

class PromptRequest(BaseModel):
    """Legacy support — kept for compatibility"""
    prompt: str
    mode: str = "standard"
class ChatRequest(BaseModel):
    """Legacy support — kept for compatibility"""
    prompt: str
    mode: str = "standard"
    clarification_answers: Optional[Dict[str, str]] = None




 # HUMANISATION MODULE
 
CONTRACTION_MAP = {
    "it is":      "it's",
    "you are":    "you're",
    "they are":   "they're",
    "we are":     "we're",
    "I am":       "I'm",
    "do not":     "don't",
    "does not":   "doesn't",
    "did not":    "didn't",
    "will not":   "won't",
    "can not":    "can't",
    "cannot":     "can't",
    "should not": "shouldn't",
    "would not":  "wouldn't",
    "could not":  "couldn't",
    "have not":   "haven't",
    "has not":    "hasn't",
    "is not":     "isn't",
    "are not":    "aren't",
    "was not":    "wasn't",
    "were not":   "weren't",
    "that is":    "that's",
    "there is":   "there's",
    "here is":    "here's",
    "you will":   "you'll",
    "we will":    "we'll",
    "it will":    "it'll",
}

FORMAL_MAP = {
    "In conclusion,":               "So,",
    "Furthermore,":                 "Also,",
    "Moreover,":                    "On top of that,",
    "Subsequently,":                "After that,",
    "In addition,":                 "Plus,",
    "It is important to note that": "Keep in mind that",
    "It should be noted that":      "Worth noting that",
    "In order to":                  "To",
    "Due to the fact that":         "Because",
    "At this point in time":        "Right now",
    "In the event that":            "If",
    "With regard to":               "About",
    "Utilise":                      "Use",
    "utilise":                      "use",
    "Commence":                     "Start",
    "commence":                     "start",
    "Terminate":                    "End",
    "terminate":                    "end",
    "Endeavour":                    "Try",
    "endeavour":                    "try",
}


def apply_rule_transforms(text: str) -> str:
    for formal, natural in CONTRACTION_MAP.items():
        text = text.replace(formal, natural)
    for formal, natural in FORMAL_MAP.items():
        text = text.replace(formal, natural)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = []
    for s in sentences:
        if len(s.split()) > 40 and ", and " in s:
            parts = s.split(", and ", 1)
            result.append(parts[0] + ".")
            result.append("And " + parts[1])
        else:
            result.append(s)
    return " ".join(result)


def humanise_with_llm(text: str) -> Optional[str]:
    """Stage 2 —  Qwen 2.5 rewrite pass for natural conversational tone."""
    instruction = (
        "Rewrite the following AI-generated response to sound more natural and conversational, "
        "like a knowledgeable friend explaining something clearly. "
        "Use contractions, vary sentence length, write in second person where natural, "
        "and remove unnecessarily formal phrases. "
        "Keep all facts and meaning exactly the same. Do not add new information.\n\n"
        f"Text:\n{text}\n\nRewritten version:"
    )
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": instruction}],
            options={"temperature": 0.7, "num_predict": 600}
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"Humanisation LLM error: {e}")
        return None


def humanise(text: str) -> dict:
    """Full two-stage humanisation pipeline."""
    stage1 = apply_rule_transforms(text)
    stage2 = humanise_with_llm(stage1)
    return {
        "original":   text,
        "rule_based": stage1,
        "humanised":  stage2 if stage2 else stage1,
        "used_llm":   stage2 is not None,
    }


# LLM GENERATION
 
def generate_response(prompt: str) -> Optional[str]:
    """Generate a response from Qwen 2.5 via Ollama."""
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.7, "num_predict": 800}
        )
        return response["message"]["content"].strip()
    except Exception as e:
        print(f"LLM generation error: {e}")
        return None


def check_ollama() -> bool:
    try:
        ollama.list()
        return True
    except Exception:
        return False


# ENDPOINTS
 
@app.get("/")
async def root():
    return {
        "status": "running",
        "title":  "PromptAI Backend",
        "model":  OLLAMA_MODEL,
        "docs":   "/docs"
    }


@app.get("/api/prompt/status")
async def status():
    return {
        "api":    "running",
        "ollama": check_ollama(),
        "model":  OLLAMA_MODEL,
    }


@app.post("/api/prompt/analyse")
async def analyse(request: AnalyseRequest):
    prompt = request.prompt.strip()
    
    raw_missing = predict_missing_dimensions(prompt)
    missing = [m.lower().strip() for m in raw_missing] 
    
    quality_score = score_prompt(missing)
    questions = get_clarification_questions(missing)

    
    all_dims = ["goal", "audience", "format", "constraints", "context"]
    analysis = {d: d not in missing for d in ALL_DIMS}

    session_id = str(uuid.uuid4())
    db_create_session(session_id, prompt, missing)

    if len(missing) == 0 or quality_score >= 80:
        session_id = str(uuid.uuid4())
        refined = reconstruct_prompt(prompt, {}) 
        db_create_session(session_id, prompt, [])
        db_save_refined(session_id, refined) 
        
        return {
            "session_id":     session_id,
            "quality_score":  100,
            "analysis":       {d: True for d in ["goal", "audience", "format", "constraints", "context"]},
            "missing":        [],
            "needs_coaching": False,
            "refined_prompt": refined,
            "message":        "Your prompt is already well-structured! Enhancing for maximum quality...",
        }

    questions = get_clarification_questions(missing)
    return {
        "session_id": session_id,
        "quality_score": quality_score,
        "analysis": analysis,
        "missing": missing,
        "needs_coaching": True,
        "next_question": questions[0] if questions else None,
        "message": "I've identified some missing details to improve your prompt.",
    }



@app.post("/api/prompt/answer")
async def answer(request: AnswerRequest):
    session = db_get_session(request.session_id)
    db_save_answer(request.session_id, request.dimension, request.answer)
    
    updated_session = db_get_session(request.session_id)
    answered_keys = [k.lower() for k in updated_session["answers"].keys()]
    
    analysis = {
        d: (d not in session["missing_dims"]) or (d in answered_keys)
        for d in ALL_DIMS
    }
    
    score = int((len([v for v in analysis.values() if v]) / len(ALL_DIMS)) * 100)
    remaining = [d for d in session["missing_dims"] if d not in answered_keys]

    if remaining:
        questions = get_clarification_questions(remaining)
        return {
            "status": "clarifying",
            "analysis": analysis,
            "quality_score": score,
            "next_question": questions[0]
        }
    else:
        refined = reconstruct_prompt(session["original_prompt"], updated_session["answers"])
        db_save_refined(request.session_id, refined)
        return {
            "status": "ready",
            "analysis": {d: True for d in ALL_DIMS},
            "quality_score": 100,
            "refined_prompt": refined, 
            "message": "Reconstruction complete. Generating Expert Response...",
        }


@app.post("/api/prompt/generate")
async def generate(request: GenerateRequest):
    """
    Takes the reconstructed refined prompt, sends it to  Qwen 2.5,
    and returns a humanised response.
    """
    session = db_get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    prompt_to_use = session.get("refined_prompt") or session["original_prompt"]

    if not check_ollama():
        raise HTTPException(
            status_code=503,
            detail=f"Ollama is not running. Start it with: ollama run {OLLAMA_MODEL}"
        )

    raw = generate_response(prompt_to_use)
    if not raw:
        raise HTTPException(status_code=500, detail="Failed to generate response from  Qwen 2.5.")

    humanised = humanise(raw)

    return {
        "session_id":          request.session_id,
        "raw_response":        raw,
        "humanised_response":  humanised["humanised"],
        "rule_based_response": humanised["rule_based"],
        "used_llm":            humanised["used_llm"],
        "refined_prompt":      prompt_to_use,
    }


@app.post("/api/prompt/standard")
async def standard(request: StandardRequest):
    """
    Sends prompt directly to  Qwen 2.5 without coaching.
    Used for comparison in evaluation.
    """
    if not check_ollama():
        return {"response": f"Ollama not running. Start with: ollama run {OLLAMA_MODEL}", "ollama_running": False}

    raw = generate_response(request.prompt)
    return {
        "response":      raw or "Failed to generate response.",
        "ollama_running": True,
        "prompt_used":   request.prompt,
    }


@app.post("/analyze")
async def analyze_legacy(request: PromptRequest):
    missing = [
    d.lower()
    for d in predict_missing_dimensions(request.prompt)
]
    print("Missing:", missing)
    questions = get_clarification_questions(missing)
    return {
        "original_prompt":      request.prompt,
        "missing_dimensions":   missing,
        "clarification_needed": len(missing) > 0,
        "questions":            questions,
        "message":              "Analysis complete.",
    }


@app.post("/chat")
async def chat_legacy(request: ChatRequest):
    missing = predict_missing_dimensions(request.prompt)
    improved = request.prompt
    if request.clarification_answers:
        improved = reconstruct_prompt(request.prompt, request.clarification_answers)

    raw = generate_response(improved)
    if not raw:
        raise HTTPException(status_code=500, detail="LLM generation failed.")

    return {
        "original_prompt":    request.prompt,
        "improved_prompt":    improved,
        "missing_dimensions": missing,
        "response":           raw,
        "mode":               request.mode,
    }


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    session = db_get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session

 
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)