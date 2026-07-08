import spacy
import re
from typing import Dict

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None
    print("WARNING: spaCy model not found. Run: python -m spacy download en_core_web_sm")


def check_goal(prompt: str, doc=None) -> bool:
    action_verbs = [
        "write", "create", "make", "help", "explain", "generate", "build",
        "design", "draft", "summarise", "summarize", "analyse", "analyze",
        "describe", "list", "compare", "suggest", "recommend", "find",
        "translate", "rewrite", "improve", "fix", "plan", "develop"
    ]
    prompt_lower = prompt.lower()
    has_action = any(verb in prompt_lower for verb in action_verbs)

    if doc:
        has_verb = any(token.pos_ == "VERB" for token in doc)
        return has_action or (has_verb and len(prompt.split()) >= 5)

    return has_action and len(prompt.split()) >= 4


def check_audience(prompt: str, doc=None) -> bool:
    audience_signals = [
        "for", "to", "audience", "reader", "user", "student", "students",
        "children", "child", "kids", "beginner", "expert", "professional",
        "manager", "teacher", "client", "customer", "developer", "team",
        "boss", "colleague", "friend", "teenager", "adult", "senior"
    ]
    prompt_lower = prompt.lower()
    return any(signal in prompt_lower.split() for signal in audience_signals)


def check_format(prompt: str, doc=None) -> bool:
    format_signals = [
        "email", "essay", "paragraph", "list", "bullet", "report", "blog",
        "post", "summary", "article", "letter", "message", "code", "script",
        "table", "slide", "presentation", "tweet", "caption", "story",
        "poem", "outline", "plan", "template", "format", "structure"
    ]
    prompt_lower = prompt.lower()
    return any(signal in prompt_lower for signal in format_signals)


def check_constraints(prompt: str, doc=None) -> bool:
    constraint_signals = [
        "short", "long", "brief", "detailed", "formal", "informal", "casual",
        "professional", "simple", "words", "sentences", "pages", "tone",
        "style", "concise", "comprehensive", "under", "maximum", "minimum",
        "friendly", "serious", "funny", "technical", "non-technical"
    ]
    has_number_length = bool(re.search(r'\d+\s*(words?|sentences?|pages?|lines?|paragraphs?)', prompt.lower()))
    prompt_lower = prompt.lower()
    has_signal = any(signal in prompt_lower for signal in constraint_signals)
    return has_signal or has_number_length


def check_context(prompt: str, doc=None) -> bool:
    context_signals = [
        "because", "since", "as", "background", "context", "situation",
        "currently", "recently", "our", "my", "we", "i am", "i'm",
        "the project", "the company", "working on", "studying", "trying to"
    ]
    prompt_lower = prompt.lower()
    has_signal = any(signal in prompt_lower for signal in context_signals)
    has_length = len(prompt.split()) > 15
    return has_signal or has_length


def analyse_prompt(prompt: str) -> Dict:
    doc = nlp(prompt) if nlp else None

    analysis = {
        "goal":        check_goal(prompt, doc),
        "audience":    check_audience(prompt, doc),
        "format":      check_format(prompt, doc),
        "constraints": check_constraints(prompt, doc),
        "context":     check_context(prompt, doc),
    }

    present_count = sum(1 for v in analysis.values() if v)
    quality_score = round((present_count / len(analysis)) * 100)
    missing = [dim for dim, present in analysis.items() if not present]

    return {
        "analysis":     analysis,
        "quality_score": quality_score,
        "missing":      missing,
        "total_dimensions": len(analysis),
        "present_count": present_count
    }

def score_prompt(prompt: str) -> float:
    result = analyse_prompt(prompt)
    return result["quality_score"]