import gradio as gr
import fitz  # PyMuPDF
from openai import OpenAI
from pymongo import MongoClient
from datetime import datetime, timezone
import os, json, re
from dotenv import load_dotenv


# Load env
load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
mongoDb = os.getenv("MONGODB_URI")

# DB setup
db_name = "career_bot"
collection_name = "resume"
db_client = MongoClient(mongoDb)
db = db_client[db_name]
collection = db[collection_name]

def extract_text_from_pdf(pdf_file):
    """Extract raw text from PDF using PyMuPDF."""
    text = ""
    with fitz.open(pdf_file) as doc:
        for page in doc:
            text += page.get_text()
    return text.strip()

def analyze_resume(text):
    """Send resume text to OpenAI for structured analysis."""
    prompt = f"""
You are a professional ATS (Applicant Tracking System) resume analyzer.
Extract and return ONLY JSON, no extra text. 
- Always include phone, email, LinkedIn if available. 
- For experience and education, provide detailed multiline descriptions (not inline).
- Provide 3–5 suggestions as full sentences.
- Calculate an ATS score between 0–100 based on relevance, clarity, and completeness.

JSON Format:
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
  "experience": [
    {{
      "title": "",
      "company": "",
      "duration": "",
      "location": "",
      "details": ""
    }}
  ],
  "education": [
    {{
      "degree": "",
      "institution": "",
      "years": "",
      "details": ""
    }}
  ],
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


def clean_json_output(result_str):
    """Ensure the OpenAI output is valid JSON."""
    try:
        # Remove non-JSON text before/after
        json_str = re.search(r"\{.*\}", result_str, re.S).group()
        return json.loads(json_str)
    except Exception:
        return {"raw_response": result_str}


def save_to_mongodb(user_data):
    """Save analyzed resume data to MongoDB with timestamp."""
    document = {
        "resume_data": user_data,
        "timestamp": datetime.now(timezone.utc)
    }
    collection.insert_one(document)


 #ui to show resume
def process_resume(pdf_file):
    if not pdf_file.endswith(".pdf"):
        return "❌ Please upload a PDF file only."

    text = extract_text_from_pdf(pdf_file)
    result_str = analyze_resume(text)
    data = clean_json_output(result_str)
    # Format report
    if "raw_response" in data:
        report = data["raw_response"]
    else:
    # Build experience string separately
      experience_str = "\n\n".join([
        f"**{exp['title']}** at {exp['company']} \n📅 {exp['duration']} | 📍 {exp['location']}\n{exp['details']}"
        for exp in data.get('experience', [])
    ])

    # Build education string separately
    education_str = "\n\n".join([
        f"**{edu['degree']}** at {edu['institution']} \n📅 {edu['years']}\n{edu.get('details','')}"
        for edu in data.get('education', [])
    ])

    # Build suggestions string separately
    suggestions_str = "\n".join([f"- {s}" for s in data.get('suggestions', [])])

    # Final report string
    report = f"""
    ## 📌 Resume Analysis

    ### 👤 Personal Details
    - **Name**: {data['personal_details'].get('full_name', '')}
    - **Phone**: {data['personal_details'].get('phone', '')}
    - **Email**: {data['personal_details'].get('email', '')}
    - **LinkedIn**: {data['personal_details'].get('linkedin', '')}
    - **Location**: {data['personal_details'].get('location', '')}

    ### 📝 Summary
    {data.get('summary', '')}

    ### 💡 Skills
    {", ".join(data.get('skills', []))}

    ### 💼 Experience
    {experience_str}

    ### 🎓 Education
    {education_str}

    ### 📊 ATS Score
    **{data.get('ats_score', 0)} / 100**

    ### ✅ Suggestions
    {suggestions_str}
    """

    save_to_mongodb(data)
    return report



# ------------------ GRADIO UI ------------------
with gr.Blocks() as demo:
    gr.Markdown("## 📄 Resume Analyzer Bot")
    gr.Markdown("Upload your PDF resume to get ATS analysis & suggestions")

    with gr.Row():
        upload = gr.File(label="Upload Resume (PDF only)", file_types=[".pdf"])

    output = gr.Markdown(label="Analysis Result")  # Changed from Textbox → Markdown

    upload.change(fn=process_resume, inputs=upload, outputs=output)

if __name__ == "__main__":
    demo.launch()
 