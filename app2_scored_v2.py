import io
import json
import re
import time
from datetime import date

import pandas as pd
import pymupdf
import streamlit as st

from resume_extractor import (
    MISSING, EDU_LEVELS, EDU_PATTERNS, KNOWN_SKILLS, clean_value, regex_extract,
)

# ==================================================
# 1. PAGE CONFIGURATION
# ==================================================

st.set_page_config(page_title="Resume Shortlisting", page_icon="📄", layout="wide")

# ==================================================
# 2. CONFIGURATION
# ==================================================

# Paste your free key from https://aistudio.google.com/apikey
# (keep your GitHub repo PRIVATE if the key is written here)
GEMINI_API_KEY = ""
GEMINI_MODEL = ""  # leave empty = auto-pick a Flash model your key can use
MAX_CHARS_TO_GEMINI = 30000

# Regex extraction (name, experience, education, title, salary, location,
# skills) lives in resume_extractor.py. Keep that file next to app.py.

# ==================================================
# 3. GEMINI EXTRACTION
# ==================================================

def get_api_key():
    key = GEMINI_API_KEY
    if key and not key.startswith("PASTE_"):
        return key
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        key = ""
    if key:
        return key
    import os
    return os.environ.get("GEMINI_API_KEY", "")


GEMINI_PROMPT = """You are an expert recruiter extracting data from a resume.
Return ONLY a JSON object with exactly these keys:
{
  "candidate_name": string or null,
  "total_relevant_experience_years": number or null,
  "education": [full degree entries, e.g. "BS Computer Science, FAST NUCES"],
  "current_job_title": string or null,
  "expected_salary_pkr_per_month": number or null,
  "location": string or null,
  "skills": [short skill names]
}
Rules:
- Experience: total professional work experience in years. Use a stated
  figure if present, otherwise compute from employment dates (today is
  {today}). Do not double-count overlapping jobs. Exclude education dates.
- Current job title: the role whose dates end in Present/Current/Now. If
  the candidate has no current job, use their most recent title.
- Salary: only if the resume states an expected salary. Convert to a plain
  number per month (e.g. "150k" -> 150000, "1.5 lac" -> 150000).
  Do NOT use past/current salary unless it is labelled as expected.
- Location: the candidate's current city (and country if given).
- Skills: technical and professional skills mentioned in the resume.
- Use null / empty list when the information is truly absent. Never guess.

RESUME:
\"\"\"
{resume}
\"\"\"
"""


@st.cache_data(show_spinner=False, ttl=3600)
def resolve_model(api_key):
    """Ask Google which models this key can use; pick the best Flash model."""
    import urllib.request
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
        headers={"x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        models = json.loads(resp.read().decode("utf-8")).get("models", [])

    skip = ("image", "tts", "live", "audio", "embedding", "thinking",
            "robotics", "computer", "learnlm", "gemma", "vision")
    candidates = []
    for m in models:
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        name = m["name"].split("/")[-1]
        low = name.lower()
        if "flash" not in low or any(k in low for k in skip):
            continue
        version = tuple(int(x) for x in re.findall(r"\d+", low.split("flash")[0])[:2]) or (0,)
        stable = not any(k in low for k in ("preview", "exp", "-0"))
        lite = "lite" in low
        candidates.append(((stable, not lite, version), name))
    if not candidates:
        raise RuntimeError("No Gemini Flash model available for this API key.")
    candidates.sort(reverse=True)
    return candidates[0][1]


def gemini_extract(text, api_key):
    """Returns a dict in the same shape as regex_extract's output, or raises."""
    import urllib.request

    prompt = GEMINI_PROMPT.replace("{today}", date.today().isoformat()) \
                          .replace("{resume}", text[:MAX_CHARS_TO_GEMINI])
    model = GEMINI_MODEL or resolve_model(api_key)
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "temperature": 0},
    }).encode("utf-8")

    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, data=body, method="POST",
                headers={"Content-Type": "application/json",
                         "x-goog-api-key": api_key},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            raw = payload["candidates"][0]["content"]["parts"][0]["text"]
            data = json.loads(raw)
            break
        except Exception as error:  # rate limit, bad JSON, network...
            last_error = error
            time.sleep(2 * (attempt + 1))
    else:
        raise last_error

    def s(v):
        v = (v or "").strip() if isinstance(v, str) else ""
        return v or None

    exp = data.get("total_relevant_experience_years")
    exp = float(exp) if isinstance(exp, (int, float)) else None
    sal = data.get("expected_salary_pkr_per_month")
    sal = float(sal) if isinstance(sal, (int, float)) else None
    edu = [clean_value(e) for e in (data.get("education") or []) if str(e).strip()]
    skills = [clean_value(k) for k in (data.get("skills") or []) if str(k).strip()]

    return {
        "Candidate Name": s(data.get("candidate_name")),
        "Experience (Years)": exp,
        "Education": "; ".join(edu) if edu else None,
        "Current Job Title": s(data.get("current_job_title")),
        "Salary (Numeric)": sal,
        "Location": s(data.get("location")),
        "Key Skills": ", ".join(skills) if skills else None,
    }


def merge_fields(regex_fields, ai_fields):
    """Prefer Gemini values; fall back to regex where Gemini found nothing."""
    merged = dict(regex_fields)
    for key, value in ai_fields.items():
        if value is not None:
            merged[key] = value
    if ai_fields.get("Salary (Numeric)") is not None:
        merged["Salary Expectations"] = f"{int(ai_fields['Salary (Numeric)']):,}"
    return merged

# ==================================================
# 4. PDF PARSING
# ==================================================

def read_pdf(pdf_bytes):
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
            pages = len(pdf)
            text = "\n".join(page.get_text() for page in pdf).strip()
    except Exception as error:
        return None, 0, str(error)
    if not text:
        return None, pages, "No readable text (scanned PDF? OCR needed)."
    return text, pages, None


def process_resumes(files, use_gemini, progress):
    api_key = get_api_key() if use_gemini else ""
    rows, texts, errors = [], {}, []
    seen = {}
    gemini_failed_once = False

    for idx, (name, data) in enumerate(files):
        progress.progress(idx / len(files), text=f"Processing {name} ...")
        count = seen.get(name, 0) + 1
        seen[name] = count
        label = name if count == 1 else f"{name} (#{count})"

        text, pages, error = read_pdf(data)
        if error:
            errors.append(f"{label}: {error}")
            continue

        fields = regex_extract(text)
        method = "Regex"
        if api_key:
            try:
                fields = merge_fields(fields, gemini_extract(text, api_key))
                method = "Gemini + Regex"
            except Exception as error:
                if not gemini_failed_once:
                    errors.append(f"Gemini failed ({error}); using regex "
                                  f"fallback for affected resumes.")
                    gemini_failed_once = True
                method = "Regex (Gemini failed)"

        rows.append({"Resume File": label, **fields,
                     "Pages": pages, "Extraction Method": method})
        texts[label] = text

    progress.progress(1.0, text="Done")
    return rows, texts, errors

# ==================================================
# 5. FILTERING
# ==================================================

def edu_levels_of(education_text):
    if not education_text or education_text == MISSING:
        return set()
    return {name for name, pattern in EDU_PATTERNS
            if re.search(pattern, education_text)}


def apply_criteria(df, texts, c):
    keep_unknown = c["include_unknown"]

    def combine(match, missing):
        return (match | missing) if keep_unknown else match

    mask = pd.Series(True, index=df.index)

    if c["min_exp"] > 0:
        col = df["Experience (Years)"]
        mask &= combine((col >= c["min_exp"]).fillna(False), col.isna())

    education_terms = [term.strip().lower() for term in c["education"].split(",") if term.strip()]
    if education_terms:
        match = df["Education"].apply(
            lambda value: any(term in str(value).lower() for term in education_terms)
            if pd.notna(value) and value != MISSING else False
        )
        mask &= combine(match, df["Education"] == MISSING)

    if c["job_title"].strip():
        q = c["job_title"].strip()
        missing = df["Current Job Title"] == MISSING
        match = df["Current Job Title"].str.contains(
            q, case=False, regex=False, na=False) & ~missing
        mask &= combine(match, missing)

    if c["location"].strip():
        q = c["location"].strip()
        missing = df["Location"] == MISSING
        match = df["Location"].str.contains(
            q, case=False, regex=False, na=False) & ~missing
        mask &= combine(match, missing)

    if c["min_sal"] > 0 or c["max_sal"] > 0:
        sal = df["Salary (Numeric)"]
        match = pd.Series(True, index=df.index)
        if c["min_sal"] > 0:
            match &= sal >= c["min_sal"]
        if c["max_sal"] > 0:
            match &= sal <= c["max_sal"]
        mask &= combine(match.fillna(False), sal.isna())

    skills = [s.strip().lower() for s in c["skills"].split(",") if s.strip()]
    if skills:
        check = all if c["skill_mode"] == "Match all" else any

        def has_skills(row):
            hay = (str(row["Key Skills"]) + " " +
                   texts.get(row["Resume File"], "")).lower()
            return check(s in hay for s in skills)

        match = df.apply(has_skills, axis=1)
        mask &= combine(match, df["Key Skills"] == MISSING)

    return df[mask]


def add_match_scores(df, texts, c):
    """Add a score out of the number of requirement fields the user supplied."""
    skills = [s.strip().lower() for s in c["skills"].split(",") if s.strip()]
    active_fields = sum([
        c["min_exp"] > 0,
        bool(c["education"].strip()),
        bool(c["job_title"].strip()),
        bool(c["location"].strip()),
        c["min_sal"] > 0 or c["max_sal"] > 0,
        bool(skills),
    ])

    def score_candidate(row):
        score = 0

        if c["min_exp"] > 0:
            value = row["Experience (Years)"]
            if pd.notna(value) and value >= c["min_exp"]:
                score += 1

        education_terms = [term.strip().lower() for term in c["education"].split(",") if term.strip()]
        if education_terms:
            value = row["Education"]
            if pd.notna(value) and value != MISSING and any(
                term in str(value).lower() for term in education_terms
            ):
                score += 1

        if c["job_title"].strip():
            value = row["Current Job Title"]
            if pd.notna(value) and value != MISSING and c["job_title"].strip().lower() in str(value).lower():
                score += 1

        if c["location"].strip():
            value = row["Location"]
            if pd.notna(value) and value != MISSING and c["location"].strip().lower() in str(value).lower():
                score += 1

        if c["min_sal"] > 0 or c["max_sal"] > 0:
            value = row["Salary (Numeric)"]
            if pd.notna(value):
                meets_min = c["min_sal"] <= 0 or value >= c["min_sal"]
                meets_max = c["max_sal"] <= 0 or value <= c["max_sal"]
                if meets_min and meets_max:
                    score += 1

        if skills:
            hay = (str(row["Key Skills"]) + " " + texts.get(row["Resume File"], "")).lower()
            checks = [skill in hay for skill in skills]
            matched = all(checks) if c["skill_mode"] == "Match all" else any(checks)
            if matched:
                score += 1

        return f"{score}/{active_fields}"

    result = df.copy()
    result["Match Score"] = result.apply(score_candidate, axis=1)
    return result

# ==================================================
# 6. PAGES
# ==================================================

for key, default in {
    "page": "criteria", "df": None, "texts": {}, "errors": [], "criteria": {},
}.items():
    st.session_state.setdefault(key, default)


def page_criteria():
    st.title("📄 Resume Shortlisting")
    st.subheader("Step 1 of 2 — Upload resumes and set your requirements")

    uploaded = st.file_uploader(
        "Upload candidate resumes (PDF)", type=["pdf"],
        accept_multiple_files=True, key="uploader",
    )

    st.markdown("#### Requirements")
    c1, c2 = st.columns(2)
    min_exp = c1.number_input("Relevant Experience (minimum years)",
                              min_value=0.0, value=0.0, step=0.5)
    education = c2.text_input(
        "Educational Qualification (any of)",
        placeholder="e.g. Bachelor's, Master's, BS Computer Science",
        help="Enter one or more qualifications separated by commas.")

    c3, c4 = st.columns(2)
    job_title = c3.text_input("Current Job Title (contains)",
                              placeholder="e.g. Data Analyst")
    location = c4.text_input("Location (contains)", placeholder="e.g. Lahore")

    c5, c6 = st.columns(2)
    min_sal = c5.number_input("Salary Expectations — Min (PKR/month)",
                              min_value=0, value=0, step=10_000)
    max_sal = c6.number_input("Salary Expectations — Max (PKR/month, 0 = no limit)",
                              min_value=0, value=0, step=10_000)

    skills = st.text_input("Key Skills (comma-separated)",
                           placeholder="e.g. Python, SQL, Power BI")
    skill_mode = st.radio("Skill matching", ["Match all", "Match any"],
                          horizontal=True)

    include_unknown = st.checkbox(
        "Include candidates with missing data for a filtered field", value=False)

    has_key = bool(get_api_key())
    use_gemini = st.checkbox(
        "Use Gemini AI to improve field detection", value=has_key,
        disabled=not has_key,
        help=None if has_key else "Add your Gemini API key in app.py to enable.")
    if not has_key:
        st.caption("No Gemini key found — regex extraction will be used.")

    if st.button("🚀 Process Resumes", type="primary"):
        if not uploaded:
            st.error("Please upload at least one PDF resume.")
            return
        files = [(f.name, f.getvalue()) for f in uploaded]
        progress = st.progress(0.0, text="Starting ...")
        rows, texts, errors = process_resumes(files, use_gemini, progress)
        st.session_state.df = pd.DataFrame(rows) if rows else None
        st.session_state.texts = texts
        st.session_state.errors = errors
        st.session_state.criteria = {
            "min_exp": min_exp, "education": education,
            "job_title": job_title, "location": location,
            "min_sal": min_sal, "max_sal": max_sal,
            "skills": skills, "skill_mode": skill_mode,
            "include_unknown": include_unknown,
        }
        st.session_state.page = "results"
        st.rerun()


def page_results():
    st.title("📄 Resume Shortlisting")
    st.subheader("Step 2 of 2 — Candidates ranked by match score")

    if st.button("← Back to upload & criteria"):
        st.session_state.page = "criteria"
        st.rerun()

    for msg in st.session_state.errors:
        st.warning(msg)

    df = st.session_state.df
    if df is None or df.empty:
        st.error("No resumes could be processed.")
        return

    df = add_match_scores(df, st.session_state.texts, st.session_state.criteria)
    # All candidates are shown. Sort descending by the score numerator.
    df = df.sort_values(
        by="Match Score",
        key=lambda scores: scores.str.split("/").str[0].astype(int),
        ascending=False,
        kind="stable",
    ).reset_index(drop=True)

    st.metric("Total Resumes", len(df))
    st.caption("All processed candidates are shown, ranked by match score. "
               "Extracted fields are preliminary — verify against the original "
               "resume. Salary is shown as PKR per month; foreign-currency "
               "figures are converted at approximate rates (see FX_TO_PKR in "
               "resume_extractor.py).")

    st.dataframe(df, width="stretch", hide_index=True)
    try:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Candidates")
        st.download_button(
            "📥 Download All Candidates as Excel", data=out.getvalue(),
            file_name="candidate_scores.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as error:
        st.error(f"Excel export failed: {error}")

    st.divider()
    st.subheader("Review Original Resume Text")
    choice = st.selectbox("Choose a resume", list(st.session_state.texts.keys()))
    if choice:
        st.text_area("Extracted text", st.session_state.texts[choice],
                     height=300, key="review_text")


if st.session_state.page == "criteria":
    page_criteria()
else:
    page_results()
