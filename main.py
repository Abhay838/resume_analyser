from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from datetime import datetime, timezone
import fitz  # PyMuPDF
import re, json, os
from openai import OpenAI
import firebase_admin
from firebase_admin import credentials, firestore

# Load API key
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load Firebase credentials from environment variable
firebase_key = os.getenv("FIREBASE_KEY")
if not firebase_key:
    raise ValueError("FIREBASE_KEY not set in environment variables")

cred_dict = json.loads(firebase_key)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

app = FastAPI()

def extract_text_from_pdf(pdf_file: str):
    text = ""
    with fitz.open(pdf_file) as doc:
        for page in doc:
            text += page.get_text()
    return text.strip()

def analyze_resume(text: str):
    prompt = f"""
    You are a professional ATS (Applicant Tracking System) resume analyzer.
    Return ONLY JSON.
    {{
      "personal_details": {{
        "full_name": "",
        "phone": "",
        "email": "",
        "linkedin": "",
        "location": ""
      }},
      "summary": "",
      "skills": [],
      "experience": [{{"title":"","company":"","duration":"","location":"","details":""}}],
      "education": [{{"degree":"","institution":"","years":"","details":""}}],
      "ats_score": 0,
      "suggestions": []
    }}
    Resume Text:
    {text}
    """
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    return response.choices[0].message.content

def clean_json_output(result_str: str):
    try:
        json_str = re.search(r"\{.*\}", result_str, re.S).group()
        return json.loads(json_str)
    except Exception:
        return {"raw_response": result_str}

@app.post("/analyze_resume/")
async def analyze_resume_endpoint(file: UploadFile = File(...)):
    temp_path = "temp.pdf"
    with open(temp_path, "wb") as f:
        f.write(await file.read())

    text = extract_text_from_pdf(temp_path)
    result_str = analyze_resume(text)
    data = clean_json_output(result_str)

    # Save to Firestore
    doc_ref = db.collection("resumes").document()
    doc_ref.set({
        "resume_data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

    return data
