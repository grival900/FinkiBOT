from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.api.schemas import QuizGenerateRequest, QuizResponse
from backend.core.retrieval import search
from backend.db import get_db
from backend.quiz.extraction import extract_text
from backend.quiz.generation import generate_quiz_from_text

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate", response_model=QuizResponse)
def generate(payload: QuizGenerateRequest, db: Session = Depends(get_db)) -> QuizResponse:
    """Quiz from already-indexed content (course pages, announcements). Limited by what
    the scrapers actually cover — mostly course names/tags and announcement text, not
    full lecture material, since that isn't publicly scraped."""
    results = search(db, payload.course_query, k=8)
    if not results:
        raise HTTPException(status_code=404, detail="No indexed content found for that course/topic yet")

    context = "\n\n---\n\n".join(f"[{r.title}]\n{r.chunk_text}" for r in results)
    questions = generate_quiz_from_text(context, payload.num_questions)
    source_titles = list(dict.fromkeys(r.title for r in results))
    return QuizResponse(questions=questions, source_titles=source_titles)


@router.post("/upload", response_model=QuizResponse)
async def upload(file: UploadFile = File(...), num_questions: int = Form(5)) -> QuizResponse:
    """Quiz from a student-uploaded file (PDF/PPTX) — this is how the quiz maker works
    around not having public access to course materials. Ephemeral: the extracted text
    is sent straight to the LLM and never persisted into the shared index."""
    data = await file.read()
    try:
        text = extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from the uploaded file")

    questions = generate_quiz_from_text(text, num_questions)
    return QuizResponse(questions=questions, source_titles=[file.filename or "uploaded file"])
