"""
resume_extractor.py  -  regex extraction for the Resume Shortlisting app.

Fields: Candidate Name, Experience (Years), Education, Current Job Title,
Salary Expectations / Salary (Numeric, PKR per month), Location, Key Skills.

app.py only needs:
    from resume_extractor import (MISSING, EDU_LEVELS, EDU_PATTERNS,
                                  KNOWN_SKILLS, clean_value, regex_extract)
"""
import re
from datetime import date

MISSING = "Not found"

# ==================================================
# CONFIG
# ==================================================

KNOWN_SKILLS = [
    "Python", "SQL", "Excel", "Power BI", "Tableau", "UiPath", "RPA",
    "Automation", "Machine Learning", "Data Analysis", "Data Analytics",
    "SAP", "Java", "C++", "C#", ".NET", "JavaScript", "TypeScript", "HTML",
    "CSS", "Pandas", "NumPy", "Power Automate", "Communication",
    "Project Management", "Leadership", "Statistics", "AWS", "Azure", "GCP",
    "Data Visualization", "ETL", "Data Engineering", "Artificial Intelligence",
    "Deep Learning", "TensorFlow", "PyTorch", "Git", "Docker", "Kubernetes",
    "Linux", "MySQL", "PostgreSQL", "MongoDB", "React", "Node.js", "Django",
    "Flask", "Spark", "Hadoop", "NLP", "Computer Vision", "Scikit-learn",
    "Salesforce", "Apex", "Visualforce", "Lightning Web Components", "LWC",
    "Spring Boot", "REST API", "SOAP", "CI/CD", "Agile", "Scrum", "JIRA",
    "QuickBooks", "Accounting", "Auditing", "Recruitment", "Customer Service",
    "Microsoft Office", "SEO", "Photoshop", "Figma",
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

US_STATES = (
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS "
    "MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV "
    "WI WY DC ON BC AB QC"
).split()
COUNTRIES = (
    "Pakistan|United States|USA|United Kingdom|UK|UAE|United Arab Emirates|"
    "Saudi Arabia|Qatar|Canada|Australia|India|Germany|Singapore|Malaysia|"
    "Turkey|Bahrain|Kuwait|Oman"
)

# Approximate rates, ONLY used to compare foreign-currency salaries with the
# PKR min/max filter.  Edit when needed.
FX_TO_PKR = {"PKR": 1, "USD": 280, "GBP": 355, "EUR": 305, "AED": 76, "SAR": 75}

# ==================================================
# EDUCATION PATTERNS
# ==================================================

CERT_LABEL = "Certificate / Training"
_NA = r"(?<![A-Za-z])"          # not preceded by a letter
_NZ = r"(?![A-Za-z])"           # not followed by a letter
_NS = r"(?<!, )"                # avoids state codes: "Boston, MA"

EDU_PATTERNS = [
    ("PhD",
     r"(?i:" + _NA + r"(?:ph\.?\s?d|doctorate|doctoral)" + _NZ + r")"),
    ("Master's",
     r"(?i:" + _NA + r"(?:master'?s?|mphil|m\.phil)" + _NZ + r")"
     r"|" + _NS + _NA + r"(?:MS|M\.S\.?|MSc|M\.Sc\.?|MBA|M\.B\.A\.?|MTech|"
     r"M\.Tech\.?|MCS|MA|M\.A\.?|MEng|MPH|MPA|LLM|MCom|FCPS|MCPS|MRCP)" + _NZ),
    ("Bachelor's",
     r"(?i:" + _NA + r"(?:bachelor'?s?|bsc|b\.sc\.?)" + _NZ + r")"
     r"|" + _NA + r"(?:BS|B\.S\.?|BSc|B\.Sc\.?|BBA|BTech|B\.Tech\.?|BE|B\.E\.?|"
     r"BEng|BCS|BA|B\.A\.?|BCom|B\.Com\.?|BSCS|BSSE|BSIT|BSAI|BSN|BPT|BDS|"
     r"BArch|BFA|MBBS|M\.B\.B\.S\.?|DPT|LLB|LL\.B\.?|DVM|Pharm[\s.\-]?D)" + _NZ),
    ("Intermediate",
     r"(?i:" + _NA + r"(?:a[- ]levels?|f\.?\s?sc|hssc|hsc|higher\s+secondary|"
     r"intermediate\s+(?:in|of|part|pre|science|commerce|arts)|"
     r"pre[- ](?:medical|engineering))" + _NZ + r")"
     r"|" + _NA + r"(?:ICS|ICom|I\.Com|FA)" + _NZ),
    ("Matriculation",
     r"(?i:" + _NA + r"(?:matriculation|matric|o[- ]levels?|ssc|"
     r"secondary\s+school\s+certificate)" + _NZ + r")"),
    ("Diploma",
     r"(?i:" + _NA + r"(?:diploma|associate\s+degree)" + _NZ + r")"
     r"|" + _NA + r"(?:DAE|ADP)" + _NZ),
    (CERT_LABEL,
     r"(?i:" + _NA + r"(?:certificates?|certifications?|certified|training|"
     r"boot\s?camp|nanodegree|short\s+course|licen[cs]ed?)" + _NZ + r")"),
]
EDU_LEVELS = [name for name, _ in EDU_PATTERNS]
DEGREE_PATTERNS = [p for name, p in EDU_PATTERNS if name != CERT_LABEL]

CERT_EXTRA = re.compile(
    r"(?i)\b(?:program(?:me)?|course|workshop|seminar|fellowship|"
    r"apprenticeship)\b")
INSTITUTION = re.compile(
    r"(?i)\b(?:university|college|institute|school|academy|foundation|"
    r"association|board|council|society|cent(?:re|er)|polytechnic|"
    r"seminary|international|iqra|nust|comsats|fast|nucES|lums)\b")
# lines inside an education entry that are not part of its name
EDU_NOISE = re.compile(
    r"(?i)^\s*(?:graduated|graduation|completed|expected|gpa|cgpa|grade|"
    r"percentage|marks|class\s+of|batch|year|result|thesis|major|minor|"
    r"course\s+curriculum)\b")
LABEL_HEAD = re.compile(r"(?i)educational?\s+qualifications?")

# ==================================================
# DATES
# ==================================================

MONTH_RE = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|"
            r"July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
            r"Nov(?:ember)?|Dec(?:ember)?)")
MONTH_NUM = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
             "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
# "March 2020", "15th Nov 2021", "1 July 2021", "03/2020", "2019"
_DATE_TOKEN = (
    r"(?:(?:(?:\d{1,2}(?:st|nd|rd|th)?\s+)?" + MONTH_RE + r"\.?,?\s+)?"
    r"(?:19|20)\d{2}(?!\d)"
    r"|(?:0?[1-9]|1[0-2])[/.](?:19|20)\d{2}(?!\d))"
)
_PRESENT = (r"(?:present|current(?:ly)?|now|ongoing|till\s+date|"
            r"to\s+date|date|today)")
RANGE_RE = re.compile(
    r"(?<![A-Za-z0-9/.])(?P<s>" + _DATE_TOKEN + r")\s*"
    r"(?:[-–—−]+|\bto\b|\buntil\b|\btill\b)\s*"
    r"(?P<e>" + _DATE_TOKEN + r"|" + _PRESENT + r"(?![A-Za-z]))",
    re.IGNORECASE,
)

# ==================================================
# SECTION HEADINGS
# ==================================================

BULLET_CHARS = "•▪◦●■➢➤✓✔‣∙►❖\uf0b7\uf0a7\uf076\uf0d8"

_SECTION_DEFS = [
    ("projects", r"(?:personal\s+|academic\s+|key\s+)?projects?"),
    ("other",
     r"achievements?|awards?|honou?rs|languages?|interests|hobbies|"
     r"publications?|volunteer(?:ing)?(?:\s+experience|\s+work)?|"
     r"extracurricular(?:\s+activities)?|declaration|"
     r"contact(?:\s+(?:information|details))?|links"),
    ("coursework", r"relevant\s+(?:courses|coursework)|coursework"),
    ("experience",
     r"(?:work\s+|professional\s+|relevant\s+|industry\s+)?experiences?|"
     r"employment(?:\s+history|\s+record)?|work\s+history|"
     r"career\s+history|professional\s+background"),
    ("education",
     r"education(?:al)?(?:\s+background|\s+qualifications?|\s+details|"
     r"\s+history)?(?:\s*(?:&|and)\s*(?:certifications?|training|"
     r"licen[cs]es|courses))?|"
     r"academic(?:s|\s+qualifications?|\s+background|\s+record)?"),
    ("certifications",
     r"(?:licen[cs]es\s*(?:&|and)\s*)?(?:certifications?|certificates?)"
     r"(?:\s*(?:&|and)\s*(?:training|courses|licen[cs]es))?|"
     r"(?:trainings?|courses)(?:\s*(?:&|and)\s*certifications?)?"),
    ("skills",
     r"(?:key\s+)?(?:technical\s+|core\s+|professional\s+|it\s+)?skills"
     r"(?:\s*(?:&|and)\s*\w+)?|core\s+competencies|competencies|"
     r"areas\s+of\s+expertise|expertise|technologies"),
    ("summary",
     r"(?:professional\s+|career\s+|executive\s+)?"
     r"(?:summary|profile|objective)|about\s+me|"
     r"personal\s+(?:details|information|profile)"),
    ("references", r"references?"),
]
_SECTION_RE = re.compile(
    r"(?<![A-Za-z])(?:"
    + "|".join(f"(?P<{n}>{p})" for n, p in _SECTION_DEFS)
    + r")(?![A-Za-z])[ \t]*:?",
    re.IGNORECASE,
)

TITLE_WORDS = re.compile(
    r"(?i)\b(?:manager|engineer|analyst|developer|officer|executive|director|"
    r"lead|head|consultant|specialist|associate|assistant|intern|internee|"
    r"trainee|coordinator|supervisor|administrator|architect|designer|"
    r"accountant|technician|guard|teacher|lecturer|professor|clerk|"
    r"representative|scientist|researcher|programmer|tester|auditor|advisor|"
    r"adviser|controller|president|founder|owner|agent|operator|driver|nurse|"
    r"doctor|physician|pharmacist|cashier|receptionist|secretary|planner|"
    r"strategist|editor|writer|producer|recruiter|buyer|merchandiser|"
    r"inspector|foreman|mechanic|electrician|chef|cook|waiter|salesman|"
    r"salesperson|sales|marketing|support|admin|freelancer|contractor|"
    r"generalist|principal|partner|fellow|apprentice|technologist|"
    r"investigator|detective|instructor|trainer|mentor|tutor|surgeon|"
    r"resident|vp|ceo|cto|cfo)s?\b"
)

# ==================================================
# GENERIC HELPERS
# ==================================================

def clean_value(value):
    return re.sub(r"\s+", " ", value).strip(" \t:;,-")


def normalize_text(text):
    """Bullets on their own line, tidy odd characters, drop page footers."""
    text = (text.replace("\r", "\n").replace("\u00a0", " ")
                .replace("\u200b", "").replace("\xad", "")
                .replace("’", "'").replace("‘", "'"))
    text = re.sub(r"[ \t]*([" + BULLET_CHARS + r"])[ \t]*", r"\n\1 ", text)
    text = re.sub(r"(?im)^\s*page\s+\d+\s*(?:of|/)\s*\d+\s*$", "", text)
    return re.sub(r"[ \t]+", " ", text)


def _lines(chunk):
    return [ln.strip() for ln in chunk.split("\n") if ln.strip()]


def _is_bullet(line):
    return line[0] in BULLET_CHARS or bool(re.match(r"[-*–]\s", line))


def _strip_bullet(line):
    return re.sub(r"^[" + re.escape(BULLET_CHARS) + r"\-*–]+\s*", "", line)


_BOUNDARY = re.compile(r"(?<=[a-z0-9\)\]])[.;!?]\s+(?=[A-Z])")
_ABBREV = {"inc", "ltd", "pvt", "co", "corp", "llc", "dr", "mr", "mrs",
           "ms", "st", "jr", "sr", "vs", "etc", "dept", "univ", "govt"}


def _sentence_cuts(s):
    cuts = []
    for m in _BOUNDARY.finditer(s):
        word = re.search(r"([A-Za-z]+)$", s[:m.start()])
        if word and word.group(1).lower() in _ABBREV:
            continue
        cuts.append(m)
    return cuts


def last_sentence(s):
    cuts = _sentence_cuts(s)
    return s[cuts[-1].end():].strip() if cuts else s.strip()


def first_sentence(s):
    cuts = _sentence_cuts(s)
    return s[:cuts[0].start() + 1].strip() if cuts else s.strip()


# ---------- labelled fields: "Label: value", "Label - value", "LABEL\nvalue"

LABELS = {
    "title": ["Current Job Title", "Current Position", "Current Role",
              "Job Title", "Designation", "Current Designation",
              "Present Position"],
    "salary": ["Salary Expectations", "Expected Salary", "Salary Expectation",
               "Expected Compensation", "Salary Requirement", "Expected CTC",
               "Desired Salary", "Salary Expected", "Expected Remuneration"],
    "location": ["Current Location", "Location", "Current City", "City",
                 "Based In", "Residing In"],
    "address": ["Current Address", "Present Address", "Address"],
    "education": ["Educational Qualification", "Educational Qualifications",
                  "Education Qualification", "Highest Qualification",
                  "Highest Education", "Highest Degree", "Qualification"],
    "skills": ["Key Technical Skills", "Key Skills", "Technical Skills",
               "Core Skills", "Skills"],
}
_OTHER_LABELS = ["Notice Period", "Date of Birth", "Nationality",
                 "Marital Status", "Father Name", "Contact", "Phone",
                 "Email", "Relevant Experience", "Total Experience",
                 "Years of Experience", "Experience"]


def _nl(s):
    return re.sub(r"[^a-z]+", " ", s.lower()).strip()


ALL_LABELS = {_nl(l) for ls in LABELS.values() for l in ls} | \
             {_nl(l) for l in _OTHER_LABELS}


def find_field(text, labels, max_len=150):
    """'Label: value' / 'Label - value' on one line, or 'LABEL' alone on a
    line with the value on the next non-empty line."""
    lines = [ln.strip() for ln in text.split("\n")]
    for label in labels:
        same = re.compile(rf"(?i)^[{re.escape(BULLET_CHARS)}\-*\s]*"
                          rf"{re.escape(label)}\s*(?:[:\-–—]\s*(.*))?$")
        for i, ln in enumerate(lines):
            m = same.match(ln)
            if not m:
                continue
            value = clean_value(m.group(1) or "")
            if value:
                return value[:max_len]
            for nxt in lines[i + 1:i + 3]:     # label alone: take next line
                if not nxt:
                    continue
                if _nl(nxt) in ALL_LABELS or _SECTION_RE.fullmatch(nxt.strip()):
                    break
                value = clean_value(nxt)
                if value:
                    return value[:max_len]
                break
    return MISSING


# ---------- sections

def split_sections(text):
    found = []
    for m in _SECTION_RE.finditer(text):
        raw = m.group(0)
        word = raw.strip(" \t:")
        line_start = text.rfind("\n", 0, m.start()) + 1
        starts_line = not text[line_start:m.start()].strip()
        nl = text.find("\n", m.end())
        rest = text[m.end(): nl if nl != -1 else len(text)]
        if not word[:1].isupper():
            continue                   # "training" on its own wrapped line
        if re.fullmatch(r"(?i)trainings?|courses", word) and not word.isupper():
            continue                   # "HIPAA Compliance / Training"
        alone = starts_line and not rest.strip()
        with_colon = starts_line and ":" in raw
        upper = False
        if word.isupper():
            prev = re.search(r"([A-Za-z][A-Za-z.']*)\W*$", text[:m.start()])
            upper = not (prev and prev.group(1).isupper()
                         and len(prev.group(1).strip(".'")) >= 2)
        if alone or with_colon or upper:
            found.append((m.lastgroup, m.start(), m.end(), raw))

    sections = []
    for i, (name, h_start, h_end, raw) in enumerate(found):
        b_end = found[i + 1][1] if i + 1 < len(found) else len(text)
        sections.append({"name": name, "h_start": h_start, "b_start": h_end,
                         "b_end": b_end, "heading": raw})
    return sections


def section_text(text, sections, names):
    return "\n".join(text[s["b_start"]:s["b_end"]]
                     for s in sections if s["name"] in names)


def outside_text(text, sections, names):
    """Everything except the headings+bodies of the named sections."""
    out, pos = [], 0
    for s in sorted(sections, key=lambda s: s["h_start"]):
        if s["name"] in names:
            out.append(text[pos:s["h_start"]])
            pos = s["b_end"]
    out.append(text[pos:])
    return "\n".join(out)

# ==================================================
# NAME
# ==================================================

_NAME_OK = re.compile(r"[A-Za-z][A-Za-z.'\-]*(?: [A-Za-z][A-Za-z.'\-]*)*")
_NAME_IGNORE = re.compile(
    r"(?i)resume|curriculum vitae|\bcv\b|email|phone|mobile|linkedin|github|"
    r"address|portfolio|candidate profile|https?://|www\.")


def extract_name(text):
    for line in text.splitlines()[:15]:
        line = clean_value(line)
        if not line or "@" in line or re.search(r"\d", line):
            continue
        if _NAME_IGNORE.search(line) or not _NAME_OK.fullmatch(line):
            continue
        if not 2 <= len(line.split()) <= 4 or len(line) > 60:
            continue
        if _SECTION_RE.search(line) or TITLE_WORDS.search(line):
            continue                                # heading or job title
        return line.title() if line.isupper() else line
    return MISSING

# ==================================================
# EXPERIENCE
# ==================================================

_NUMWORDS = {w: n for n, w in enumerate(
    "one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split(), 1)}
_NUMWORDS.update({"thirty": 30, "forty": 40})
_NUM = r"(?:\d+(?:\.\d+)?|" + "|".join(_NUMWORDS) + r")"
_DUR = (r"(?:" + _NUM + r"\s*\+?\s*(?:years?|yrs?)"
        r"(?:\s*(?:and\s*)?\d+\s*(?:months?|mos?))?"
        r"|\d+\s*\+?\s*months?)")
_EXP_PATTERNS = [
    re.compile(r"(?i)(?:total\s+|relevant\s+|professional\s+|work\s+)?"
               r"experience(?:\s+of)?\s*[:\-–]?\s*(?:over\s+|more\s+than\s+|"
               r"around\s+|approximately\s+|about\s+)?(" + _DUR + r")"),
    re.compile(r"(?i)(" + _DUR + r")'?(?:\s+of)?\s+"
               r"(?:[A-Za-z&/-]+\s+){0,2}?experience"),
]


def parse_duration(s):
    s = s.lower()
    years = months = 0.0
    m = re.search(r"(" + _NUM + r")\s*\+?\s*(?:years?|yrs?)", s)
    if m:
        v = m.group(1)
        years = float(_NUMWORDS[v]) if v in _NUMWORDS else float(v)
    m = re.search(r"(\d+)\s*\+?\s*(?:months?|mos?)", s)
    if m:
        months = float(m.group(1))
    return round(years + months / 12, 1)


def extract_stated_experience(text):
    for pattern in _EXP_PATTERNS:
        for m in pattern.finditer(text):
            value = parse_duration(m.group(1))
            if 0 < value <= 60:
                return value
    return None


def _month_index(token, is_end, today):
    t = token.strip().lower()
    if re.fullmatch(_PRESENT, t):
        return today.year * 12 + today.month
    m = re.fullmatch(r"(0?[1-9]|1[0-2])[/.]((?:19|20)\d{2})", t)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
    else:
        year = int(re.search(r"(?:19|20)\d{2}", t).group())
        word = re.search(MONTH_RE, t, re.IGNORECASE)
        month = MONTH_NUM.get(word.group().lower()[:3]) if word else None
    if month is None:
        return year * 12
    return year * 12 + (month if is_end else month - 1)


def parse_ranges(text, today=None):
    today = today or date.today()
    now_idx = today.year * 12 + today.month
    ranges = []
    for m in RANGE_RE.finditer(text):
        start = _month_index(m.group("s"), False, today)
        end_tok = m.group("e")
        end = min(_month_index(end_tok, True, today), now_idx)
        if end <= start:
            end = start + 1
        ranges.append({
            "start": start, "end": end,
            "current": bool(re.fullmatch(_PRESENT, end_tok.strip().lower())),
            "ok": start < now_idx,
            "m_start": m.start(), "m_end": m.end(),
        })
    return ranges


def title_from_header(header):
    """'Security Guard at ADT, City' / 'Analyst | ABC' / 'Medical Officer in
    Indus Hospital, Lahore' -> the title part."""
    h = header.strip(" \t|•·,;:-–—")
    if not h or len(h.split()) > 14:
        return ""
    at = re.split(r"\s+(?:at|@)\s+", h, maxsplit=1, flags=re.IGNORECASE)
    if len(at) == 2 and at[0].strip():
        return clean_value(at[0])[:100]
    inn = re.split(r"\s+in\s+", h, maxsplit=1, flags=re.IGNORECASE)
    if len(inn) == 2 and TITLE_WORDS.search(inn[0]):
        return clean_value(inn[0])[:100]
    parts = [clean_value(p) for p in
             re.split(r"\s*\|\s*|\s+[-–—]\s+|\s*,\s*|\s{2,}", h)
             if clean_value(p)]
    if not parts:
        return ""
    for part in parts:
        if TITLE_WORDS.search(part):
            return part[:100]
    return parts[0][:100]


def header_before(chunk):
    candidates = []
    for ln in reversed(_lines(chunk)[-3:]):
        bullet = _is_bullet(ln)
        body = _strip_bullet(ln) if bullet else ln
        piece = last_sentence(body)
        if bullet and piece == body.strip():
            break
        if len(piece.split()) > 14:
            break
        candidates.append(piece)
    for cand in candidates:
        title = title_from_header(cand)
        if title and TITLE_WORDS.search(title):
            return title
    return title_from_header(candidates[0]) if candidates else ""


def header_after(chunk):
    candidates = []
    for ln in _lines(chunk)[:3]:
        if _is_bullet(ln):
            break
        piece = first_sentence(ln)
        if len(piece.split()) > 14:
            break
        candidates.append(piece)
    for cand in candidates:
        title = title_from_header(cand)
        if title and TITLE_WORDS.search(title):
            return title
    return title_from_header(candidates[0]) if candidates else ""


def _jobs_from(body, require_title):
    ranges = parse_ranges(body)
    if not ranges:
        return []
    date_first = not body[:ranges[0]["m_start"]].strip()
    jobs = []
    for i, r in enumerate(ranges):
        if date_first:
            nxt = ranges[i + 1]["m_start"] if i + 1 < len(ranges) else len(body)
            title = header_after(body[r["m_end"]:nxt])
        else:
            prev = ranges[i - 1]["m_end"] if i else 0
            title = header_before(body[prev:r["m_start"]])
        if require_title and not TITLE_WORDS.search(title or ""):
            continue
        if r["ok"]:
            jobs.append({"title": title, "start": r["start"], "end": r["end"],
                         "current": r["current"]})
    return jobs


_NOT_JOB = ("experience", "education", "certifications", "references",
            "projects", "summary", "coursework")


def parse_jobs(text, sections=None):
    """Jobs from the Experience section, plus title-bearing date ranges found
    elsewhere (two-column PDFs often spill jobs under other headings)."""
    sections = sections if sections is not None else split_sections(text)
    exp_body = section_text(text, sections, ("experience",))
    rest = outside_text(text, sections, _NOT_JOB)
    jobs = []
    if exp_body.strip():
        jobs += _jobs_from(exp_body, False)
        jobs += _jobs_from(rest, True)
    else:
        jobs += _jobs_from(rest, False)
    for i, j in enumerate(jobs):
        j["order"] = i
    return jobs


def estimate_experience(text, jobs=None):
    jobs = parse_jobs(text) if jobs is None else jobs
    if not jobs:
        return None
    spans = sorted((j["start"], j["end"]) for j in jobs)
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    months = sum(e - s for s, e in merged)
    return round(months / 12, 1) if months else None


def extract_job_title(text, jobs=None):
    stated = find_field(text, LABELS["title"])
    if stated != MISSING:
        return stated
    jobs = [j for j in (parse_jobs(text) if jobs is None else jobs)
            if j["title"]]
    if jobs:
        current = [j for j in jobs if j["current"]]
        if current:
            best = max(current, key=lambda j: (j["start"], -j["order"]))
        else:
            best = max(jobs, key=lambda j: (j["end"], j["start"], -j["order"]))
        return best["title"][:150]
    # fallback: tagline right under the name ("MEDICAL OFFICER")
    for ln in _lines(text)[:8]:
        if (TITLE_WORDS.search(ln) and len(ln.split()) <= 6
                and "@" not in ln and not re.search(r"\d", ln)
                and not _SECTION_RE.fullmatch(ln.strip())):
            return clean_value(ln)[:100]
    return MISSING

# ==================================================
# EDUCATION
# ==================================================

def _levels(s):
    return {n for n, p in EDU_PATTERNS if re.search(p, s)}


def _tidy_entry(s):
    # "(2021)" / "(Mar 2019)" anywhere, then a trailing bare year
    s = re.sub(r"\(\s*(?:" + MONTH_RE + r"\.?\s+)?(?:19|20)\d{2}\s*\)", "", s,
               flags=re.IGNORECASE)
    s = re.sub(r"[\s,(\[]*(?:" + MONTH_RE + r"\.?\s+)?(?:19|20)\d{2}[\s)\]]*$",
               "", s, flags=re.IGNORECASE)
    s = re.sub(r"^[\s)\]:;,.\-–—|]+", "", s)
    s = re.sub(r"[\s(\[:;,\-–—|]+$", "", s)
    s = re.sub(r"\s+,", ",", s)
    return clean_value(s)


def _join(prev, nxt):
    """Wrapped line ('...Protection' + 'Guards, Alexandria') or a new part
    ('MBBS' + 'University of X')?"""
    if (INSTITUTION.search(prev) and not prev.rstrip().endswith(",")
            and not INSTITUTION.search(nxt) and "," in nxt):
        return prev + " " + nxt
    return prev + ", " + nxt


def _entries_from_body(body, patterns, strict, is_cert):
    def qualifies(piece):
        if any(re.search(p, piece) for p in patterns):
            return True
        return (not strict) and bool(CERT_EXTRA.search(piece))

    chunks, prev = [], 0
    for r in parse_ranges(body):
        chunks.append(body[prev:r["m_start"]])
        prev = r["m_end"]
    chunks.append(body[prev:])

    entries = []
    for chunk in chunks:
        pieces = []                      # (text, was_bullet)
        for ln in _lines(chunk):
            if not re.search(r"[A-Za-z]", ln):
                continue                 # stray ")" or "-"
            bullet = _is_bullet(ln)
            line = _strip_bullet(ln) if bullet else ln
            line = line.rstrip(" |")
            piece = last_sentence(line) if (bullet or len(line.split()) > 14) \
                else line
            if bullet and piece == line.strip() and not is_cert:
                continue                 # bullet description
            if len(piece.split()) > 25:
                continue
            if piece:
                pieces.append((piece, bullet))

        i = 0
        while i < len(pieces):
            piece, bullet = pieces[i]
            if qualifies(piece) or (is_cert and bullet):
                taken = 0
                j = i + 1
                while j < len(pieces) and taken < 2 and not is_cert:
                    nxt, nb = pieces[j]
                    if qualifies(nxt) or nb:
                        break
                    j += 1
                    if (EDU_NOISE.match(nxt) or len(nxt.split()) > 10
                            or "@" in nxt or re.search(r"\d{5,}", nxt)):
                        continue         # skip noise, keep looking
                    piece = _join(piece, nxt)
                    taken += 1
                    i = j - 1
                entry = _tidy_entry(piece)
                if entry:
                    entries.append(entry)
            i += 1
    return entries


_PROGRESS = re.compile(
    r"(?i)\b(?:pursuing|finishing|completing|studying\s+for|enrolled\s+in|"
    r"currently\s+(?:pursuing|completing|studying))\s+(?:a|an|the|my)?\s*"
    r"((?:bachelor|master|ph\.?d|doctorate|mba|bs|ms)[^.\n;,]{0,50}?)"
    r"(?=\s+(?:and|with|at|from|but|while)\b|[.,;\n]|$)")


def extract_education(text, sections=None):
    sections = sections if sections is not None else split_sections(text)
    edu = [s for s in sections if s["name"] in ("education", "certifications")]
    if len([s for s in edu if s["name"] == "education"]) > 1:
        edu = [s for s in edu if not LABEL_HEAD.fullmatch(
            s["heading"].strip(" \t\n:"))]

    all_patterns = [p for _, p in EDU_PATTERNS]
    entries = []
    if edu:
        for s in edu:
            entries += _entries_from_body(
                text[s["b_start"]:s["b_end"]], all_patterns, False,
                s["name"] == "certifications")
    else:   # no heading: degrees only, whole text
        entries = _entries_from_body(text, DEGREE_PATTERNS, True, False)

    stated = find_field(text, LABELS["education"])
    if stated != MISSING:
        have = set().union(*[_levels(e) for e in entries]) if entries else set()
        if not (_levels(stated) & have) or _levels(stated) == set():
            entries.insert(0, stated)

    if not any(_levels(e) & {"PhD", "Master's", "Bachelor's"} for e in entries):
        m = _PROGRESS.search(text)
        if m:
            deg = clean_value(m.group(1))
            entries.append(deg[:1].upper() + deg[1:] + " (in progress)")

    seen, out = set(), []
    for e in entries:
        if e.casefold() not in seen:
            seen.add(e.casefold())
            out.append(e)
    return "; ".join(out) if out else MISSING

# ==================================================
# SALARY
# ==================================================

_CURRENCIES = [
    ("USD", r"\$|\busd\b|\bus\s*dollars?\b"),
    ("GBP", r"£|\bgbp\b"),
    ("EUR", r"€|\beur\b"),
    ("AED", r"\baed\b|\bdirhams?\b"),
    ("SAR", r"\bsar\b|\briyals?\b"),
    ("PKR", r"\bpkr\b|\brs\b\.?|\brupees?\b|₨"),
]
_NUM_UNIT = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(lpa|lacs?|lakhs?|million|mn|m|k)?(?![A-Za-z])",
    re.IGNORECASE)
_YEARLY = re.compile(r"(?i)per\s+(?:year|annum)|annual|yearly|p\.?\s?a\b|"
                     r"/\s*(?:yr|year)|\blpa\b")
_MONTHLY = re.compile(r"(?i)per\s+month|monthly|/\s*(?:mo|month)|\bp\.?m\b")


def extract_salary(text):
    value = find_field(text, LABELS["salary"])
    if value != MISSING:
        return value
    m = re.search(
        r"(?i)(?:expected|expecting|desired)\s+(?:salary|ctc|compensation|pay)"
        r"[^\n\d$£€₨]{0,25}((?:pkr|rs\.?|usd|aed|gbp|eur|sar|[$£€₨])?\s*"
        r"\d[\d,\.]*\s*(?:k|lacs?|lakhs?|m|lpa)?(?:\s*(?:-|–|to)\s*"
        r"(?:pkr|rs\.?|[$£€₨])?\s*\d[\d,\.]*\s*(?:k|lacs?|lakhs?|m|lpa)?)?"
        r"(?:\s*(?:pkr|usd|aed|gbp|eur|sar))?)", text)
    return clean_value(m.group(1)) if m else MISSING


def parse_salary(value):
    """-> PKR per month (range = midpoint; foreign currency via FX_TO_PKR;
    yearly figures divided by 12). None if no number found."""
    if not value or value == MISSING:
        return None
    s = str(value)
    cur = "PKR"
    for code, pat in _CURRENCIES:
        if re.search(pat, s, re.IGNORECASE):
            cur = code
            break

    nums = []
    for m in _NUM_UNIT.finditer(s):
        num = float(m.group(1).replace(",", "").rstrip("."))
        unit = (m.group(2) or "").lower()
        nums.append([num, unit])
    nums = [n for n in nums if n[0] > 0][:2]
    if not nums:
        return None
    if len(nums) == 2 and nums[0][1] == "" and nums[1][1]:
        nums[0][1] = nums[1][1]                # "100 - 150k"
    mult = {"k": 1e3, "lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5,
            "lpa": 1e5, "m": 1e6, "mn": 1e6, "million": 1e6, "": 1}
    vals = [n * mult.get(u, 1) for n, u in nums]
    amount = sum(vals) / len(vals)

    if _YEARLY.search(s):
        amount /= 12
    elif not _MONTHLY.search(s) and cur != "PKR" and amount >= 20000:
        amount /= 12                           # 155,000 USD -> yearly
    return round(amount * FX_TO_PKR.get(cur, 1))

# ==================================================
# LOCATION
# ==================================================

_US_CITY = re.compile(
    r"\b([A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,2}),\s*(" + "|".join(US_STATES) +
    r")\b(?:\s+\d{5})?")
_CITY_COUNTRY = re.compile(
    r"\b([A-Z][a-z]+(?:[ -][A-Z][a-z]+){0,2}),\s*(" + COUNTRIES + r")\b")


def extract_pakistan_city(text):
    for city in sorted(PAKISTAN_CITIES, key=len, reverse=True):
        if re.search(rf"(?<!\w){re.escape(city)}(?!\w)", text, re.IGNORECASE):
            return city
    return MISSING


def _place_in(text):
    city = extract_pakistan_city(text)
    if city != MISSING:
        return city
    m = _US_CITY.search(text) or _CITY_COUNTRY.search(text)
    return f"{m.group(1)}, {m.group(2)}" if m else MISSING


def _clean_location(v):
    v = re.sub(r"(?i)\(\s*(?:hybrid|remote|on-?site|relocat\w*)[^)]*\)", "", v)
    return clean_value(v)


def extract_location(text):
    stated = find_field(text, LABELS["location"])
    if stated != MISSING:
        return _clean_location(stated)
    head = "\n".join(_lines(text)[:15])
    place = _place_in(head)
    if place != MISSING:
        return place
    addr = find_field(text, LABELS["address"])
    if addr != MISSING:
        place = _place_in(addr)
        if place != MISSING:
            return place
    return _place_in(text)

# ==================================================
# SKILLS
# ==================================================

def _skill_items(block):
    block = re.sub(r"\n(?=[a-z])", " ", block)          # wrapped lines
    block = "\n".join(_strip_bullet(l) if _is_bullet(l) else l
                      for l in _lines(block))
    if "," in block:                                     # comma list
        raw = re.split(r"[,;|\n]", block.replace("\n", " ")
                       if block.count(",") >= block.count("\n") else block)
    else:
        raw = re.split(r"[;|\n]", block)
    items = []
    for r in raw:
        r = clean_value(r).rstrip(".")
        if (not r or len(r) > 50 or len(r.split()) > 6 or "@" in r
                or re.fullmatch(r"[\d\W]+", r)
                or _SECTION_RE.fullmatch(r) or _nl(r) in ALL_LABELS):
            continue
        items.append(r)
    return items


def extract_skills(text, sections=None):
    sections = sections if sections is not None else split_sections(text)
    items = _skill_items(section_text(text, sections, ("skills",)))
    if not items:
        inline = find_field(text, LABELS["skills"])
        if inline != MISSING:
            items = _skill_items(inline)

    have = " | ".join(items).lower()
    for skill in KNOWN_SKILLS:
        pattern = (r"(?<![A-Za-z0-9+#])" + re.escape(skill)
                   + r"(?![A-Za-z0-9+#])")
        if skill.lower() not in have and re.search(pattern, text, re.IGNORECASE):
            items.append(skill)
            have += " | " + skill.lower()

    seen, out = set(), []
    for it in items:
        if it.casefold() not in seen:
            seen.add(it.casefold())
            out.append(it)
    return ", ".join(out[:40]) if out else MISSING

# ==================================================
# SALARY (numeric) + MAIN ENTRY
# ==================================================

def regex_extract(raw_text):
    text = normalize_text(raw_text)
    sections = split_sections(text)
    jobs = parse_jobs(text, sections)

    experience = extract_stated_experience(text)
    if experience is None:
        experience = estimate_experience(text, jobs)

    salary_text = extract_salary(text)
    return {
        "Candidate Name": extract_name(text),
        "Experience (Years)": experience,
        "Education": extract_education(text, sections),
        "Current Job Title": extract_job_title(text, jobs),
        "Salary Expectations": salary_text,
        "Salary (Numeric)": parse_salary(salary_text),
        "Location": extract_location(text),
        "Key Skills": extract_skills(text, sections),
    }
