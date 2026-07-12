from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional

# ==================== IMPORTS ====================
from classifier.evaluate_ml_analyzer import predict_missing_dimensions        # ← Change if needed
from classifier.clarification import get_clarification_questions, ClarificationQuestion

import ollama

app = FastAPI(title="PromptAI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== MODELS ====================
class PromptRequest(BaseModel):
    prompt: str
    mode: str = "standard"

class AnalysisResponse(BaseModel):
    original_prompt: str
    missing_dimensions: List[str]
    clarification_needed: bool
    questions: List[ClarificationQuestion]
    message: str

class ChatRequest(BaseModel):
    prompt: str
    mode: str = "standard"
    clarification_answers: Optional[Dict[str, str]] = None

class ChatResponse(BaseModel):
    original_prompt: str
    improved_prompt: str
    missing_dimensions: List[str]
    response: str
    mode: str

# ==================== ENDPOINTS ====================
@app.get("/")
async def root():
    return {
        "status": "running",
        "title": "PromptAI Backend",
        "docs": "/docs"
    }

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_prompt(request: PromptRequest):
    missing = predict_missing_dimensions(request.prompt)
    
    return AnalysisResponse(
        original_prompt=request.prompt,
        missing_dimensions=missing,
        clarification_needed=len(missing) > 0,
        questions=get_clarification_questions(missing),
        message="Analysis complete."
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # 1. Get missing dimensions using your classifier
        missing = predict_missing_dimensions(request.prompt)
        print("Missing dimensions:", missing)   # for debugging

        # 2. Reconstruct prompt (if answers provided)
        improved_prompt = request.prompt
        if request.clarification_answers and len(request.clarification_answers) > 0:
            parts = [f"Original request: {request.prompt}"]
            for dim, ans in request.clarification_answers.items():
                if ans and str(ans).strip():
                    parts.append(f"{dim}: {ans}")
            improved_prompt = "\n".join(parts)

        print("Improved prompt sent to Qwen:", improved_prompt[:200] + "...")

        # 3. Call Ollama
        response = ollama.chat(
            model="qwen2.5:1.5b",
            messages=[{"role": "user", "content": improved_prompt}]
        )
        
        gemma_response = response['message']['content']

        return ChatResponse(
            original_prompt=request.prompt,
            improved_prompt=improved_prompt,
            missing_dimensions=missing,
            response=gemma_response,
            mode=request.mode
        )

    except Exception as e:
        import traceback
        print("ERROR in /chat:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)