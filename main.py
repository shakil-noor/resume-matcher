import asyncio
import io
import os
from typing import List, Optional

import docx
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from pypdf import PdfReader

load_dotenv()

app = FastAPI(title="AI Resume & Job Match Agent")
templates = Jinja2Templates(directory="templates")

# Initialize the official Google GenAI SDK
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# --- 1. Structured Output Schema ---
class BulletRewrite(BaseModel):
    original_context: str = Field(
        description="The area or weak point in the current resume"
    )
    suggested_bullet: str = Field(
        description="An ATS-optimized, action-oriented resume bullet tailored to the job"
    )


class MatchReport(BaseModel):
    match_score: int = Field(
        description="Overall compatibility score from 0 to 100"
    )
    executive_summary: str = Field(
        description="2-3 sentence candid assessment of fit"
    )
    matched_skills: List[str] = Field(
        description="Skills, tools, and qualifications present in both resume and job description"
    )
    missing_gaps: List[str] = Field(
        description="Important keywords, tools, certifications, or experience required by the job but missing from the resume"
    )
    improvement_areas: List[str] = Field(
        description="Specific strategic advice on how to position the candidate better"
    )
    bullet_rewrites: List[BulletRewrite] = Field(
        description="3-4 concrete resume bullet point suggestions incorporating target keywords"
    )


# --- 2. Helper Tools (Document & Web Extraction) ---
def extract_resume_text(filename: str, file_bytes: bytes) -> str:
    ext = filename.lower().split(".")[-1]
    if ext == "pdf":
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    elif ext in ("docx", "doc"):
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs).strip()
    elif ext == "txt":
        return file_bytes.decode("utf-8", errors="ignore").strip()
    else:
        raise HTTPException(
            status_code=400, detail="Unsupported file format. Upload PDF, DOCX, or TXT."
        )


async def fetch_job_from_url(url: str) -> str:
    """Uses Jina Reader to convert a public job URL into clean text."""
    reader_url = f"https://r.jina.ai/{url.strip()}"
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http:
        resp = await http.get(reader_url, headers={"Accept": "text/plain"})
        text = resp.text

        # Detect LinkedIn or login-wall blocks
        blocked_indicators = [
            "authwall",
            "Sign in to LinkedIn",
            "Join LinkedIn",
            "403 Forbidden",
            "Just a moment...",
        ]
        if resp.status_code != 200 or any(b.lower() in text.lower() for b in blocked_indicators) or len(text) < 250:
            raise HTTPException(
                status_code=422,
                detail="LinkedIn or this site blocked automated access. Please copy and paste the Job Description text directly.",
            )
        return text[:15000]  # Cap length to keep token usage clean


# --- 3. Routes ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/analyze", response_model=MatchReport)
async def analyze_match(
    resume_file: UploadFile = File(...),
    job_url: Optional[str] = Form(None),
    job_text: Optional[str] = Form(None),
):
    # Step 1: Parse Resume
    file_bytes = await resume_file.read()
    resume_content = extract_resume_text(resume_file.filename, file_bytes)
    if len(resume_content) < 50:
        raise HTTPException(
            status_code=400, detail="Could not extract readable text from the resume."
        )

    # Step 2: Acquire Job Description (Prioritize pasted text, fallback to URL)
    jd_content = ""
    if job_text and len(job_text.strip()) > 50:
        jd_content = job_text.strip()
    elif job_url and job_url.strip().startswith("http"):
        jd_content = await fetch_job_from_url(job_url)
    else:
        raise HTTPException(
            status_code=400,
            detail="Please provide either a valid Job URL or paste the Job Description text.",
        )

    # Step 3: Run Gemini Agent with Structured Output
    prompt = f"""
    You are an expert technical recruiter and ATS (Applicant Tracking System) optimization specialist.
    Compare the following Candidate Resume against the Target Job Description.
    Be honest, specific, and practical. Do not hallucinate skills the candidate doesn't have—instead, highlight how they can frame existing experience or what gaps they must address.

    === CANDIDATE RESUME ===
    {resume_content}

    === TARGET JOB DESCRIPTION ===
    {jd_content}
    """

    models_to_try = [
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
    ]

    last_error = None

    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=MatchReport,
                        temperature=0.2,
                    ),
                )
                return MatchReport.model_validate_json(response.text)
            except Exception as e:
                last_error = e
                error_str = str(e)
                if "503" in error_str or "429" in error_str or "UNAVAILABLE" in error_str:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                break

    raise HTTPException(
        status_code=503,
        detail=f"All Gemini models are currently busy. Please try again in a moment. ({last_error})",
    )