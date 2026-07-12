
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

# ── Your existing classifier imports ─────────────────────────
from classifier.evaluate_ml_analyzer import predict_missing_dimensions
from classifier.clarification import get_clarification_questions, ClarificationQuestion


# ═══════════════════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════════════════

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

# ── Model config ──────────────────────────────────────────────
OLLAMA_MODEL = "qwen2.5:1.5b"   # your local Ollama model


# ═══════════════════════════════════════════════════════════════
# DATABASE — session storage
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# PROMPT RECONSTRUCTION
# ═══════════════════════════════════════════════════════════════

def reconstruct_prompt(original: str, answers: Dict[str, str]) -> str:
    """
    Creates an optimized prompt from the original prompt
    and clarification answers.
    """

    normalized_answers = {
        key.lower().strip(): value.strip()
        for key, value in answers.items()
        if value and value.strip()
    }

    prompt_parts = []

    # Main task
    prompt_parts.append(
        f"Create a response for the following task: {original}."
    )


    if "goal" in normalized_answers:
        prompt_parts.append(
            f"The goal is: {normalized_answers['goal']}."
        )

    if "context" in normalized_answers:
        prompt_parts.append(
            f"Background context: {normalized_answers['context']}."
        )

    if "audience" in normalized_answers:
        prompt_parts.append(
            f"The intended audience is: {normalized_answers['audience']}."
        )

    if "format" in normalized_answers:
        prompt_parts.append(
            f"The output should be in a {normalized_answers['format']} format."
        )

    if "constraints" in normalized_answers:
        prompt_parts.append(
            f"Important constraints: {normalized_answers['constraints']}."
        )


    prompt_parts.append(
        "Follow all requirements above and provide the final answer directly."
    )


    return "\n\n".join(prompt_parts)


def score_prompt(prompt: str, missing: list) -> int:
    all_dims = [
        "goal",
        "audience",
        "format",
        "constraints",
        "context"
    ]

    missing = [m.lower() for m in missing]

    present = len(
        [
            d for d in all_dims
            if d not in missing
        ]
    )

    score = int((present / len(all_dims)) * 100)

    return score


# ═══════════════════════════════════════════════════════════════
# HUMANISATION MODULE
# ═══════════════════════════════════════════════════════════════

# Stage 1 — Rule-based linguistic transforms
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
    # Break very long sentences at natural conjunction points
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
    """Stage 2 — Gemma 4 rewrite pass for natural conversational tone."""
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


# ═══════════════════════════════════════════════════════════════
# LLM GENERATION
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════

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


# ── Step 1: Analyse prompt ─────────────────────────────────────
@app.post("/api/prompt/analyse")
async def analyse(request: AnalyseRequest):

    print("=" * 60)
    print("REQUEST RECEIVED")
    print("Prompt:", repr(request.prompt))

    if not request.prompt or len(request.prompt.strip()) < 3:
        print("ERROR: Prompt too short")
        raise HTTPException(status_code=400, detail="Prompt is too short.")

    prompt = request.prompt.strip()

    print("Running classifier...")

    missing = predict_missing_dimensions(prompt)

    print("Missing:", missing)

    quality_score = score_prompt(prompt, missing)

    print("Score:", quality_score)
    print("=" * 60)

    # Build analysis dict for frontend dimension display
    all_dims = ["goal", "audience", "format", "constraints", "context"]
    analysis = {d: d not in missing for d in all_dims}

    # If nothing is missing or score already high — skip coaching
    if len(missing) == 0 or quality_score >= 80:
        session_id = str(uuid.uuid4())
        db_create_session(session_id, prompt, [])
        return {
            "session_id":     session_id,
            "quality_score":  quality_score,
            "analysis":       analysis,
            "missing":        [],
            "present_count":  len(all_dims),
            "needs_coaching": False,
            "next_question":  None,
            "message":        "Your prompt is already well-structured! Generating response…",
        }

    # Create session
    session_id = str(uuid.uuid4())
    db_create_session(session_id, prompt, missing)

    # Get first clarifying question
    questions = get_clarification_questions(missing)
    first_q = questions[0] if questions else None

    return {
        "session_id":     session_id,
        "quality_score":  quality_score,
        "analysis":       analysis,
        "missing":        missing,
        "present_count":  len(all_dims) - len(missing),
        "needs_coaching": True,
        "next_question":  first_q,
        "message":        f"Your prompt is missing some details. I'll ask you a few quick questions to make it better.",
    }


# ── Step 2: Submit clarification answer ────────────────────────
@app.post("/api/prompt/answer")
async def answer(request: AnswerRequest):
    """
    Receives the user's answer to a clarifying question.
    Saves it and returns the next question, or signals coaching is complete.
    """
    session = db_get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Save this answer
    db_save_answer(request.session_id, request.dimension, request.answer)

    # Get updated answers
    updated_session = db_get_session(request.session_id)
    answered = list(updated_session["answers"].keys())
    remaining_missing = [d for d in session["missing_dims"] if d not in answered]

    if remaining_missing:
        # More questions to ask
        questions = get_clarification_questions(remaining_missing)
        next_q = questions[0] if questions else None
        return {
            "status":          "clarifying",
            "next_question":   next_q,
            "answered_count":  len(answered),
            "total_questions": len(session["missing_dims"]),
        }
    else:
        # All answered — reconstruct the refined prompt
        refined = reconstruct_prompt(
            session["original_prompt"],
            updated_session["answers"]
        )
        db_save_refined(request.session_id, refined)

        all_dims = ["goal", "audience", "format", "constraints", "context"]
        original_score = score_prompt(session["original_prompt"], session["missing_dims"])
        refined_score = 100  # all dimensions now filled

        return {
            "status":        "ready",
            "next_question": None,
            "refined_prompt": refined,
            "comparison": {
                "original":       session["original_prompt"],
                "refined":        refined,
                "original_score": original_score,
                "refined_score":  refined_score,
                "improvement":    refined_score - original_score,
            },
            "message": "All details collected. Building your improved prompt and generating response…",
        }


# ── Step 3: Generate humanised response ────────────────────────
@app.post("/api/prompt/generate")
async def generate(request: GenerateRequest):
    """
    Takes the reconstructed refined prompt, sends it to Gemma 4,
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
        raise HTTPException(status_code=500, detail="Failed to generate response from Gemma 4.")

    humanised = humanise(raw)

    return {
        "session_id":          request.session_id,
        "raw_response":        raw,
        "humanised_response":  humanised["humanised"],
        "rule_based_response": humanised["rule_based"],
        "used_llm":            humanised["used_llm"],
        "refined_prompt":      prompt_to_use,
    }


# ── Standard (uncoached) mode ──────────────────────────────────
@app.post("/api/prompt/standard")
async def standard(request: StandardRequest):
    """
    Sends prompt directly to Gemma 4 without coaching.
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


# ── Legacy /analyze endpoint (kept for compatibility) ──────────
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


# ── Legacy /chat endpoint (kept for compatibility) ─────────────
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


# ── Session data retrieval ────────────────────────────────────
@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    session = db_get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


# ═══════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)