import io
import json
import re
import time
from datetime import date

import pandas as pd
import pymupdf
import streamlit as st

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

KNOWN_SKILLS = [
    "Python", "SQL", "Excel", "Power BI", "Tableau",
    "UiPath", "RPA", "Automation", "Machine Learning",
    "Data Analysis", "Data Analytics", "SAP", "Java",
    "C++", "C#", ".NET", "JavaScript", "HTML", "CSS",
    "Pandas", "NumPy", "Power Automate",
    "Communication", "Project Management", "Leadership",
    "Statistics", "AWS", "Azure", "Data Visualization",
    "ETL", "Data Engineering", "Artificial Intelligence",
    "Deep Learning", "TensorFlow", "PyTorch", "Git",
]

PAKISTAN_CITIES = [
    "Islamabad", "Rawalpindi", "Lahore", "Karachi", "Faisalabad",
    "Multan", "Gujranwala", "Sialkot", "Sargodha", "Bahawalpur",
    "Rahim Yar Khan", "Dera Ghazi Khan", "Sahiwal", "Sheikhupura",
    "Gujrat", "Jhelum", "Peshawar", "Mardan", "Abbottabad", "Swat",
    "Mingora", "Quetta", "Gwadar", "Khuzdar", "Hyderabad",
    "Sukkur", "Larkana", "Nawabshah", "Mirpur Khas", "Muzaffarabad",
    "Mirpur", "Gilgit", "Skardu", "Chiniot", "Okara", "Kasur",
    "Wah Cantt", "Taxila", "Attock", "Mianwali", "Dera Ismail Khan",
    "Kohat", "Bannu", "Turbat", "Chaman", "Jhang", "Khanewal",
    "Vehari", "Pakpattan", "Hafizabad", "Mandi Bahauddin", "Narowal",
    "Toba Tek Singh", "Lodhran", "Khairpur", "Jacobabad", "Thatta", "Badin",
]

EDU_PATTERNS = [
    ("PhD",
     r"(?i:(?<![A-Za-z])(?:ph\.?\s?d|doctorate|doctoral)(?![A-Za-z]))"),
    ("Master's",
     r"(?i:(?<![A-Za-z])(?:master'?s?|mphil)(?![A-Za-z]))"
     r"|(?<![A-Za-z])(?:MS|MSc|M\.Sc|MBA|MTech|M\.Tech|MCS|MA)(?![A-Za-z])"),
    ("Bachelor's",
     r"(?i:(?<![A-Za-z])(?:bachelor'?s?|bsc)(?![A-Za-z]))"
     r"|(?<![A-Za-z])(?:BS|BSc|B\.Sc|BBA|BTech|B\.Tech|BE|BCS|BA)(?![A-Za-z])"),
    ("Intermediate",
     r"(?i:(?<![A-Za-z])(?:a[- ]levels?|fsc)(?![A-Za-z]))"
     r"|(?<![A-Za-z])(?:ICS|ICom|FA)(?![A-Za-z])"),
    ("Matriculation",
     r"(?i:(?<![A-Za-z])(?:matriculation|matric|o[- ]levels?)(?![A-Za-z]))"),
    ("Diploma",
     r"(?i:(?<![A-Za-z])diploma(?![A-Za-z]))"),
]
EDU_LEVELS = [name for name, _ in EDU_PATTERNS]

EXP_HEADING = re.compile(
    r"(?im)^\s*(?:work\s+|professional\s+)?"
    r"(?:experience|employment(?:\s+history)?)\s*:?\s*$"
)
EDU_HEADING = re.compile(
    r"(?im)^\s*(?:education(?:al)?(?:\s+background|\s+qualifications?)?"
    r"|academic(?:s|\s+qualifications?)?)\s*:?\s*$"
)
DATE_RANGE = re.compile(
    r"\b((?:19|20)\d{2})\s*(?:-|–|—|to)\s*"
    r"(?:[A-Za-z]{3,9}\.?\s+)?"
    r"((?:19|20)\d{2}|present|current|date|now|ongoing)\b",
    re.IGNORECASE,
)

MISSING = "Not found"

# ==================================================
# 3. REGEX EXTRACTION (FALLBACK)
# ==================================================

def clean_value(value):
    return re.sub(r"\s+", " ", value).strip(" \t:;,-")


def find_label(text, labels):
    for label in labels:
        pattern = rf"(?im)^\s*{re.escape(label)}\s*[:\-]\s*([^\n\r]+)"
        match = re.search(pattern, text)
        if match:
            value = clean_value(match.group(1))
            if value:
                return value[:150]
    return MISSING


def extract_name(text):
    ignored = re.compile(
        r"resume|curriculum vitae|cv\b|email|phone|mobile|"
        r"linkedin|github|address|portfolio|https?://|www\.",
        re.IGNORECASE,
    )
    for line in text.splitlines()[:12]:
        line = clean_value(line)
        if not line or ignored.search(line) or "@" in line:
            continue
        if re.search(r"\d", line):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and len(line) <= 60:
            return line
    return MISSING


def extract_stated_experience(text):
    patterns = [
        r"(?i)(?:relevant\s+)?experience\s*[:\-]\s*(\d+(?:\.\d+)?)\s*\+?\s*years?",
        r"(?i)(\d+(?:\.\d+)?)\s*\+?\s*years?(?:\s+of)?\s+(?:relevant\s+)?experience",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def estimate_experience(text):
    section = text
    start = EXP_HEADING.search(text)
    if start:
        section = text[start.end():]
    end = EDU_HEADING.search(section)
    if end:
        section = section[:end.start()]

    this_year = date.today().year
    spans = []
    for s, e in DATE_RANGE.findall(section):
        s = int(s)
        e = int(e) if e.isdigit() else this_year
        if s <= e <= this_year:
            spans.append((s, e))
    if not spans:
        return None

    spans.sort()
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    total = sum(e - s for s, e in merged)
    return float(total) if total else None


def extract_education(text):
    lines = [clean_value(line) for line in text.splitlines()]
    section_start = None
    for i, line in enumerate(lines):
        if EDU_HEADING.match(line):
            section_start = i + 1
            break

    if section_start is not None:
        section_lines = []
        end_heading = re.compile(
            r"(?i)^\s*(?:work\s+experience|professional\s+experience|"
            r"employment(?:\s+history)?|experience|skills|technical\s+skills|"
            r"certifications|projects|professional\s+summary|summary|"
            r"achievements|references)\s*:?\s*$"
        )
        for line in lines[section_start:]:
            if end_heading.match(line):
                break
            section_lines.append(line)
    else:
        section_lines = lines

    entries = []
    for line in section_lines:
        if not line:
            continue
        line = re.sub(r"^\s*[-•*▪◦]+\s*", "", line)
        if not any(re.search(p, line) for _, p in EDU_PATTERNS):
            continue
        line = re.sub(
            r"\s*[\(\[]?\b(?:19|20)\d{2}\s*(?:-|–|—|to)\s*"
            r"(?:(?:19|20)\d{2}|present|current|ongoing)\b[\)\]]?\s*$",
            "", line, flags=re.IGNORECASE,
        )
        line = clean_value(line)
        if line and line not in entries:
            entries.append(line)
    return "; ".join(entries) if entries else MISSING


def extract_job_title(text):
    stated = find_label(text, [
        "Current Job Title", "Current Position", "Current Role",
        "Job Title", "Designation", "Current Designation",
    ])
    if stated != MISSING:
        return stated

    section = text
    start = EXP_HEADING.search(text)
    if start:
        section = text[start.end():]
    end_heading = re.compile(
        r"(?im)^\s*(?:education(?:al)?(?:\s+background|"
        r"\s+qualifications?)?|academic(?:s|\s+qualifications?)?|"
        r"skills|certifications|projects|references|"
        r"professional\s+summary|summary)\s*:?\s*$"
    )
    end = end_heading.search(section)
    if end:
        section = section[:end.start()]
    lines = [clean_value(line) for line in section.splitlines()]

    current_date = re.compile(
        r"(?i)(?:(?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2}\s*(?:-|–|—|to)\s*"
        r"(?:(?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2})?\s*(?:\([^)]*\)\s*)?"
        r"(?:present|current|now|ongoing|to\s+date)"
        r"|\b(?:present|current|now|ongoing)\b)"
    )
    for i, line in enumerate(lines):
        if not line or not current_date.search(line):
            continue
        title = clean_value(current_date.sub("", line))
        if title:
            parts = [clean_value(p) for p in re.split(r"\s*[|•]\s*", title)
                     if clean_value(p)]
            return parts[-1][:150] if parts else title[:150]
        for j in range(i - 1, -1, -1):
            if lines[j]:
                return lines[j][:150]
    return MISSING


def extract_salary(text):
    return find_label(text, [
        "Salary Expectations", "Expected Salary", "Salary Expectation",
        "Expected Compensation", "Salary Requirement",
    ])


def parse_salary(value):
    if not value or value == MISSING:
        return None
    m = re.search(r"(\d[\d,]*\.?\d*)\s*(k|lacs?|lakhs?|m)?\b", str(value), re.I)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit == "k":
        num *= 1_000
    elif unit.startswith(("lac", "lakh")):
        num *= 100_000
    elif unit == "m":
        num *= 1_000_000
    return num


def extract_pakistan_city(text):
    for city in sorted(PAKISTAN_CITIES, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(city)}(?!\w)", text, re.IGNORECASE):
            return city
    return MISSING


def extract_location(text):
    city = extract_pakistan_city(text)
    if city != MISSING:
        return city
    return find_label(text, ["Current Location", "Location", "City",
                             "Address", "Based In"])


def extract_skills(text):
    found = []
    for skill in KNOWN_SKILLS:
        pattern = (r"(?<![A-Za-z0-9+#])" + re.escape(skill)
                   + r"(?![A-Za-z0-9+#])")
        if re.search(pattern, text, re.IGNORECASE):
            found.append(skill)
    return ", ".join(found) if found else MISSING


def regex_extract(text):
    stated = extract_stated_experience(text)
    if stated is not None:
        experience = stated
    else:
        experience = estimate_experience(text)
    salary_text = extract_salary(text)
    return {
        "Candidate Name": extract_name(text),
        "Experience (Years)": experience,
        "Education": extract_education(text),
        "Current Job Title": extract_job_title(text),
        "Salary Expectations": salary_text,
        "Salary (Numeric)": parse_salary(salary_text),
        "Location": extract_location(text),
        "Key Skills": extract_skills(text),
    }

# ==================================================
# 4. GEMINI EXTRACTION
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
# 5. PDF PARSING
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
# 6. FILTERING
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

    if c["education"]:
        wanted = set(c["education"])
        match = df["Education"].apply(lambda v: bool(edu_levels_of(v) & wanted))
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

# ==================================================
# 7. PAGES
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
    education = c2.multiselect(
        "Educational Qualification (any of)", EDU_LEVELS,
        help="Candidate is kept if they hold any selected level.")

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
    st.subheader("Step 2 of 2 — Shortlisted candidates")

    if st.button("← Back to upload & criteria"):
        st.session_state.page = "criteria"
        st.rerun()

    for msg in st.session_state.errors:
        st.warning(msg)

    df = st.session_state.df
    if df is None or df.empty:
        st.error("No resumes could be processed.")
        return

    filtered = apply_criteria(df, st.session_state.texts,
                              st.session_state.criteria)

    m1, m2 = st.columns(2)
    m1.metric("Total Resumes", len(df))
    m2.metric("Matching Candidates", len(filtered))

    st.caption("Extracted fields are preliminary — verify against the original "
               "resume. Salary is assumed to be in PKR (no currency conversion).")

    if filtered.empty:
        st.info("No candidates match all requirements. Go back and relax "
                "some criteria, or tick 'Include candidates with missing data'.")
    else:
        st.dataframe(filtered, width="stretch", hide_index=True)
        try:
            out = io.BytesIO()
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                filtered.to_excel(writer, index=False, sheet_name="Shortlist")
            st.download_button(
                "📥 Download Shortlist as Excel", data=out.getvalue(),
                file_name="candidate_shortlist.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception as error:
            st.error(f"Excel export failed: {error}")

    with st.expander("Show all processed resumes (unfiltered)"):
        st.dataframe(df, width="stretch", hide_index=True)

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