from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.api.schemas import QuizResponse
from backend.quiz.extraction import extract_text
from backend.quiz.generation import generate_quiz_from_text

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/upload", response_model=QuizResponse)
async def upload(file: UploadFile = File(...), num_questions: int = Form(5)) -> QuizResponse:
    """Quiz from a student-uploaded file (PDF/PPTX) — the only quiz source: there's no
    public access to course lecture material to draw from otherwise, and generating
    from just the scraped course/announcement metadata produced quizzes too shallow to
    be useful. Ephemeral: the extracted text is sent straight to the LLM and never
    persisted into the shared index."""
    data = await file.read()
    try:
        text = extract_text(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from the uploaded file")

    questions = generate_quiz_from_text(text, num_questions)
    return QuizResponse(questions=questions, source_titles=[file.filename or "uploaded file"])
