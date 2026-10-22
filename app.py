import io
import re
from datetime import date
 
import pandas as pd
import pymupdf
import streamlit as st
 
# ==================================================
# 1. PAGE CONFIGURATION
# ==================================================
 
st.set_page_config(
    page_title="Resume Shortlisting",
    page_icon="📄",
    layout="wide",
)
 
st.title("📄 Resume Shortlisting Dashboard")
st.write("Upload resumes and filter candidates for shortlisting.")
 
# ==================================================
# 2. CONFIGURATION
# ==================================================
 
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
    "Islamabad","Rawalpindi","Lahore","Karachi","Faisalabad",
    "Multan","Gujranwala","Sialkot","Sargodha","Bahawalpur","Rahim Yar Khan","Dera Ghazi Khan","Sahiwal","Sheikhupura",
    "Gujrat","Jhelum","Peshawar","Mardan","Abbottabad","Swat","Mingora","Quetta","Gwadar","Khuzdar","Hyderabad",
    "Sukkur","Larkana","Nawabshah","Mirpur Khas","Muzaffarabad","Mirpur","Gilgit","Skardu","Chiniot","Okara","Kasur","Wah Cantt","Taxila","Attock",
    "Mianwali","Dera Ismail Khan","Kohat","Bannu","Turbat","Chaman","Jhang","Khanewal","Vehari","Pakpattan",
    "Hafizabad","Mandi Bahauddin","Narowal","Toba Tek Singh","Lodhran","Khairpur","Jacobabad","Thatta","Badin",
]
 
# Words are case-insensitive; abbreviations (MS, BE, BA...) are
# case-sensitive so "be" or "ms office" don't trigger a match.
# (?i:...) scopes the flag to that group only.
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
# 3. TEXT EXTRACTION HELPERS
# ==================================================
 
def clean_value(value):
    """Clean spaces and line breaks from extracted text."""
    return re.sub(r"\s+", " ", value).strip(" \t:;,-")
 
 
def find_label(text, labels):
    """Extract a value appearing after a known label (e.g. 'Location: Lahore')."""
    for label in labels:
        pattern = rf"(?im)^\s*{re.escape(label)}\s*[:\-]\s*([^\n\r]+)"
        match = re.search(pattern, text)
        if match:
            value = clean_value(match.group(1))
            if value:
                return value[:150]
    return MISSING
 
 
def extract_name(text):
    """Conservative first-lines heuristic for a name."""
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
    """Experience explicitly stated, e.g. '5 years of experience'."""
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
    """
    Estimate experience from date ranges such as 'Jan 2019 - Present'.
    Looks only at the experience section when one can be found, and
    merges overlapping ranges so parallel jobs aren't double-counted.
    """
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
    """
    Extract full education entries rather than broad categories.
    Remove trailing year ranges such as (2016 - 2018).
    """

    lines = [clean_value(line) for line in text.splitlines()]

    # Find the education section if a heading exists
    section_start = None

    for i, line in enumerate(lines):
        if EDU_HEADING.match(line):
            section_start = i + 1
            break

    if section_start is not None:
        section_lines = []

        # Stop when another major resume section begins
        end_heading = re.compile(
            r"(?i)^\s*(?:"
            r"work\s+experience|professional\s+experience|"
            r"employment(?:\s+history)?|experience|"
            r"skills|technical\s+skills|certifications|"
            r"projects|professional\s+summary|"
            r"summary|achievements|references"
            r")\s*:?\s*$"
        )

        for line in lines[section_start:]:
            if end_heading.match(line):
                break
            section_lines.append(line)
    else:
        # If there is no Education heading, search all lines
        section_lines = lines

    education_entries = []

    for line in section_lines:
        if not line:
            continue

        # Remove common bullet characters
        line = re.sub(r"^\s*[-•*▪◦]+\s*", "", line)

        # Only retain lines containing a recognized qualification
        if not any(
            re.search(pattern, line)
            for _, pattern in EDU_PATTERNS
        ):
            continue

        # Remove a trailing date range, with or without parentheses
        line = re.sub(
            r"\s*[\(\[]?\b(?:19|20)\d{2}\s*"
            r"(?:-|–|—|to)\s*"
            r"(?:(?:19|20)\d{2}|present|current|ongoing)"
            r"\b[\)\]]?\s*$",
            "",
            line,
            flags=re.IGNORECASE
        )

        line = clean_value(line)

        if line and line not in education_entries:
            education_entries.append(line)

    return "; ".join(education_entries) if education_entries else MISSING

 
def extract_job_titles(text):
    """
    Extract job titles only from lines containing employment
    date ranges, then remove the dates and company details.
    """

    lines = [clean_value(line) for line in text.splitlines()]

    # Step 1: Find the work-experience section
    section_start = None

    for i, line in enumerate(lines):
        if EXP_HEADING.match(line):
            section_start = i + 1
            break

    if section_start is not None:
        section_lines = []

        end_heading = re.compile(
            r"(?i)^\s*(?:"
            r"education(?:al)?(?:\s+background|\s+qualifications?)?|"
            r"academic(?:s|\s+qualifications?)?|"
            r"skills|technical\s+skills|certifications|"
            r"projects|professional\s+summary|"
            r"summary|achievements|references"
            r")\s*:?\s*$"
        )

        for line in lines[section_start:]:
            if end_heading.match(line):
                break
            section_lines.append(line)
    else:
        section_lines = lines

    # Step 2: Match lines containing employment date ranges
    date_pattern = re.compile(
        r"(?i)(?:"
        r"(?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2}"
        r"\s*(?:-|–|—|to)\s*"
        r"(?:(?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2}|"
        r"present|current|now|ongoing|to\s+date)"
        r"|"
        r"\b(?:19|20)\d{2}\s*[-–—]\s*"
        r"(?:19|20)\d{2}\b"
        r")"
    )

    job_titles = []

    for line in section_lines:
        if not line:
            continue

        # Only keep lines that contain a date range
        match = date_pattern.search(line)

        if not match:
            continue

        # Remove the date range
        title_line = clean_value(
            date_pattern.sub("", line)
        )

        if not title_line:
            continue

        # Remove common bullet characters
        title_line = re.sub(
            r"^\s*[-•*▪◦]+\s*", "", title_line
        )

        # Keep the title before company/location details
        # Example: Senior Data Analyst - Techlogix Solutions, Lahore
        title = re.split(
            r"\s+[|•]\s+|\s+[-–—]\s+",
            title_line,
            maxsplit=1
        )[0]

        title = clean_value(title)

        if title:
            job_titles.append(title)

    # Step 3: Remove duplicates, preserving order
    unique_titles = []
    seen = set()

    for title in job_titles:
        key = title.casefold()

        if key not in seen:
            seen.add(key)
            unique_titles.append(title)

    return "; ".join(unique_titles) if unique_titles else MISSING


def extract_job_title(text):
    """
    First use an explicitly stated current job title.
    If missing, find a work-experience entry ending in Present,
    Current, Now, or Ongoing and extract its job title.
    """

    # Step 1: Look for an explicitly stated job title
    stated_title = find_label(text, [
        "Current Job Title",
        "Current Position",
        "Current Role",
        "Job Title",
        "Designation",
        "Current Designation",
    ])

    if stated_title != MISSING:
        return stated_title

    # Step 2: Restrict the search to the work-experience section
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

    # Step 3: Find an employment date range ending in the present
    current_date = re.compile(
        r"(?i)(?:"
        r"(?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2}"
        r"\s*(?:-|–|—|to)\s*"
        r"(?:(?:[A-Za-z]{3,9}\.?\s+)?(?:19|20)\d{2})?"
        r"\s*(?:\([^)]*\)\s*)?"
        r"(?:present|current|now|ongoing|to\s+date)"
        r"|"
        r"\b(?:present|current|now|ongoing)\b"
        r")"
    )

    for i, line in enumerate(lines):
        if not line or not current_date.search(line):
            continue

        # If the date is on the same line as the job title,
        # remove the date and keep the remaining title text.
        title = clean_value(current_date.sub("", line))

        # Handle common formats such as:
        # Senior Analyst | ABC Company | Jan 2022 - Present
        if title:
            parts = [
                clean_value(part)
                for part in re.split(r"\s*[|•]\s*", title)
                if clean_value(part)
            ]
            return parts[-1][:150] if parts else title[:150]

        # If the date is on its own line, use the preceding
        # non-empty line as the likely job title.
        for j in range(i - 1, -1, -1):
            if lines[j]:
                return lines[j][:150]

    # Step 4: Nothing could be identified
    return MISSING

  
def extract_salary(text):
    return find_label(text, [
        "Salary Expectations", "Expected Salary", "Salary Expectation",
        "Expected Compensation", "Salary Requirement",
    ])
 
 
def parse_salary(value):
    """Turn '150k', 'PKR 150,000', '1.5 lac' into a number (first figure only)."""
    if not value or value == MISSING:
        return None
    m = re.search(r"(\d[\d,]*\.?\d*)\s*(k|lacs?|lakhs?|m)?\b", value, re.I)
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
        pattern = rf"(?<!\w){re.escape(city)}(?!\w)"

        if re.search(pattern, text, re.IGNORECASE):
            return city

    return MISSING

def extract_location(text):
    # First, search the entire resume for a Pakistani city
    city = extract_pakistan_city(text)

    if city != MISSING:
        return city

    return find_label(text, [
        "Current Location", "Location", "City", "Address", "Based In",
    ])
 
 
def extract_skills(text):
    found = []
    for skill in KNOWN_SKILLS:
        pattern = (
            r"(?<![A-Za-z0-9+#])"
            + re.escape(skill)
            + r"(?![A-Za-z0-9+#])"
        )
        if re.search(pattern, text, re.IGNORECASE):
            found.append(skill)
    return ", ".join(found) if found else MISSING
 
 
# ==================================================
# 4. CACHED RESUME PARSING
# ==================================================
 
@st.cache_data(show_spinner=False)
def parse_resume(pdf_bytes: bytes):
    """Parse one PDF. Cached on file contents, so filter clicks don't re-parse."""
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
            page_count = len(pdf)
            text = "\n".join(page.get_text() for page in pdf).strip()
    except Exception as error:
        return {"error": str(error)}
 
    if not text:
        return {"error": "No readable text. This PDF may be scanned and need OCR."}
 
    stated = extract_stated_experience(text)
    if stated is not None:
        experience, source = stated, "Stated"
    else:
        estimated = estimate_experience(text)
        experience = estimated
        source = "Estimated" if estimated is not None else MISSING
 
    salary_text = extract_salary(text)
 
    return {
        "text": text,
        "fields": {
            "Candidate Name": extract_name(text),
            "Experience (Years)": experience,
            "Experience Source": source,
            "Education": extract_education(text),
            "Current Job Title": extract_job_title(text),
            "Job Titles": extract_job_titles(text),
            "Salary Expectations": salary_text,
            "Salary (Numeric)": parse_salary(salary_text),
            "Location": extract_location(text),
            "Key Skills": extract_skills(text),
            "Pages": page_count,
        },
    }
 
 
# ==================================================
# 5. RESUME UPLOAD AND PROCESSING
# ==================================================
 
uploaded_files = st.file_uploader(
    "Upload candidate resumes (PDF)",
    type=["pdf"],
    accept_multiple_files=True,
)
 
candidates = []
resume_texts = {}
processing_errors = []
 
if uploaded_files:
    seen_names = {}
    for uploaded_file in uploaded_files:
        # Make labels unique so duplicate filenames don't overwrite each other
        count = seen_names.get(uploaded_file.name, 0) + 1
        seen_names[uploaded_file.name] = count
        label = uploaded_file.name if count == 1 else f"{uploaded_file.name} (#{count})"
 
        result = parse_resume(uploaded_file.getvalue())
 
        if "error" in result:
            processing_errors.append(f"{label}: {result['error']}")
            continue
 
        candidates.append({"Resume File": label, **result["fields"]})
        resume_texts[label] = result["text"]
 
    for error in processing_errors:
        st.warning(error)
 
# ==================================================
# 6. FILTERS (SIDEBAR) AND TABLE
# ==================================================
 
if candidates:
    df = pd.DataFrame(candidates)
 
    st.success(f"Successfully extracted text from {len(df)} resume(s).")
 
    # ---------- Sidebar filters ----------
    st.sidebar.header("Shortlisting Filters")
 
    include_unknown = st.sidebar.checkbox(
        "Include candidates with missing data",
        value=False,
        help="When ticked, a candidate whose value for a filtered field "
             "couldn't be found is kept instead of hidden.",
    )
 
    # Relevant experience
    exp_known = df["Experience (Years)"].dropna()
    max_exp = max(30, int(exp_known.max())) if len(exp_known) else 30
    min_experience = st.sidebar.slider(
        "Minimum Relevant Experience (years)", 0, max_exp, 0,
        help="Uses stated experience, or an estimate from date ranges.",
    )
 
    # Education (match any)
    education_options = sorted({
        item.strip()
        for value in df["Education"] if value != MISSING
        for item in value.split(",")
    })
    selected_education = st.sidebar.multiselect(
        "Educational Qualification (any of)", education_options
    )
 
    # Job title and location: partial text match
    job_query = st.sidebar.text_input("Current Job Title contains")
    location_query = st.sidebar.text_input("Location contains")
 
    # Salary range
    st.sidebar.markdown("**Salary Expectations**")
    sal_cols = st.sidebar.columns(2)
    min_salary = sal_cols[0].number_input("Min", min_value=0, value=0, step=10_000)
    max_salary = sal_cols[1].number_input(
        "Max (0 = no limit)", min_value=0, value=0, step=10_000
    )
    st.sidebar.caption("Currencies are not converted.")
 
    # Skills
    skills_options = sorted({
        skill.strip()
        for value in df["Key Skills"] if value != MISSING
        for skill in value.split(",")
    })
    selected_skills = st.sidebar.multiselect("Key Skills", skills_options)
    skill_mode = st.sidebar.radio(
        "Skill matching", ["Match all", "Match any"], horizontal=True
    )
 
    # ---------- Apply filters ----------
    def combine(match, missing):
        """Keep matches; optionally keep rows where the data is missing."""
        return (match | missing) if include_unknown else match
 
    mask = pd.Series(True, index=df.index)
 
    if min_experience > 0:
        missing = df["Experience (Years)"].isna()
        match = df["Experience (Years)"] >= min_experience
        mask &= combine(match.fillna(False), missing)
 
    if selected_education:
        missing = df["Education"] == MISSING
        match = df["Education"].apply(
            lambda v: any(e in v.split(", ") for e in selected_education)
        )
        mask &= combine(match, missing)
 
    if job_query.strip():
        missing = df["Current Job Title"] == MISSING
        match = (
            df["Current Job Title"]
            .str.contains(job_query.strip(), case=False, regex=False, na=False)
            & ~missing
        )
        mask &= combine(match, missing)
 
    if location_query.strip():
        missing = df["Location"] == MISSING
        match = (
            df["Location"]
            .str.contains(location_query.strip(), case=False, regex=False, na=False)
            & ~missing
        )
        mask &= combine(match, missing)
 
    if min_salary > 0 or max_salary > 0:
        sal = df["Salary (Numeric)"]
        missing = sal.isna()
        match = pd.Series(True, index=df.index)
        if min_salary > 0:
            match &= sal >= min_salary
        if max_salary > 0:
            match &= sal <= max_salary
        mask &= combine(match.fillna(False), missing)
 
    if selected_skills:
        check = all if skill_mode == "Match all" else any
        missing = df["Key Skills"] == MISSING
        match = df["Key Skills"].apply(
            lambda v: check(s in v.split(", ") for s in selected_skills)
        )
        mask &= combine(match, missing)
 
    filtered = df[mask]
 
    # ---------- Display ----------
    st.subheader("Shortlisted Candidates")
 
    col1, col2 = st.columns(2)
    col1.metric("Total Resumes", len(df))
    col2.metric("Matching Candidates", len(filtered))
 
    st.caption(
        "Extracted fields are preliminary and should be verified against "
        "each original resume. Estimated experience is calculated from date "
        "ranges and may be inaccurate."
    )
 
    # On older Streamlit versions use use_container_width=True instead.
    st.dataframe(filtered, width="stretch", hide_index=True)
 
    # ---------- Excel export ----------
    try:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            filtered.to_excel(writer, index=False, sheet_name="Shortlist")
 
        st.download_button(
            label="📥 Download Shortlist as Excel",
            data=output.getvalue(),
            file_name="candidate_shortlist.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as error:
        st.error(f"Excel export failed: {error}")
 
    # ---------- Review original text ----------
    st.divider()
    st.subheader("Review Original Resume Text")
 
    selected_resume = st.selectbox(
        "Choose a resume to review", options=list(resume_texts.keys())
    )
    if selected_resume:
        st.text_area(
            "Extracted text",
            value=resume_texts[selected_resume],
            height=300,
            key="review_resume_text",
        )
 
else:
    st.info(
        "Upload PDF resumes to extract candidate details "
        "and populate the shortlisting table."
    )
 