# AI Resume & Job Match Agent

An AI-powered Applicant Tracking System (ATS) analyzer built with **FastAPI**, **Google GenAI SDK (Gemini)**, and **Pydantic**. Upload a resume (`PDF`, `DOCX`, or `TXT`) and provide a job description URL or text to receive a structured compatibility score, matched skills, missing keyword gaps, and tailored resume bullet-point rewrites.

---

## Key Features

- **Multi-Format Resume Parsing:** Extracts text cleanly in-memory from `PDF`, `DOCX`, and `TXT` files without persisting user documents to disk.
- **Smart Job Description Ingestion:** Accepts public job board URLs (via Jina Reader markdown extraction) with automatic detection of authentication walls (e.g., LinkedIn), falling back smoothly to direct text input.
- **Deterministic Structured Outputs:** Enforces strict JSON schema validation via `google-genai` and Pydantic `BaseModel` (`MatchReport`), guaranteeing reliable UI rendering without brittle regex parsing.
- **Model Fallback & Retry Resilience:** Automatically handles transient `503 UNAVAILABLE` spikes and `429` rate limits using exponential backoff and multi-model routing (`gemini-3.8-flash` → `gemini-3.6-flash` → `gemini-3.5-flash-lite`).

---

## Architecture & Engineering Decisions

1. **Zero Disk Persistence (Privacy-First):** Uploaded resumes are read directly into memory (`io.BytesIO`) and discarded immediately after inference, eliminating local storage cleanup overhead and privacy risks.
2. **Graceful Handling of Anti-Bot Walls:** Major job boards like LinkedIn block automated server-side scraping. Rather than failing silently, the ingestion layer inspects HTTP status codes and login-wall signatures to guide the user to paste the job text directly.
3. **Container Security:** The provided `Dockerfile` runs the Uvicorn server under a dedicated unprivileged system user (`appuser`) on `python:3.12-slim`.

---

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Uvicorn
- **AI / LLM:** Google GenAI SDK (`google-genai`), Pydantic Structured Outputs
- **Document & Web Extraction:** `pypdf`, `python-docx`, `httpx`
- **Frontend:** HTML5, Bootstrap 5, Vanilla JavaScript (Fetch API)

---

## Quick Start

### Option 1: Run Locally with Python

1. **Clone the repository**
   ```bash
   git clone [https://github.com/shakil-noor/resume-matcher.git](https://github.com/shakil-noor/resume-matcher.git)
   cd resume-matcher

2. **Create a virtual environment & install dependencies**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Open .env and add your GEMINI_API_KEY
   ```

4. **Start the server**
   ```bash
   uvicorn main:app --reload
   ```
   Open `http://127.0.0.1:8000` in your browser.

---

### Option 2: Run with Docker

1. **Build the image**
   ```bash
   docker build -t resume-match-agent .
   ```

2. **Run the container**
   ```bash
   docker run -d -p 8000:8000 --env-file .env --name resume-agent resume-match-agent
   ```
   Open `http://127.0.0.1:8000` in your browser.