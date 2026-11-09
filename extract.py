"""Pure extraction logic for ClinSaar Voice (Gnani AI challenge demo).

No network, no keys, no dependencies. Deterministic Hindi/English extraction so the
demo runs before the Gnani API credits arrive. Swap `extract()` for an LLM call later.

Hard rule: the output schema has NO diagnosis field, and diagnosis-like input is
stripped before extraction.
"""
import re

ALLOWED_KEYS = {
    "age", "sex", "chief_complaint", "duration", "severity",
    "medications", "allergies", "red_flags",
}

SYMPTOMS = [
    ("fever", ["fever", "बुखार", "बुख़ार", "temperature", "बुख़ार"]),
    ("headache", ["headache", "सिरदर्द", "सिर दर्द", "migraine"]),
    ("cough", ["cough", "खांसी", "खाँसी"]),
    ("sore throat", ["sore throat", "throat pain", "गले में दर्द", "गला खराब"]),
    ("chest pain", ["chest pain", "chest tightness", "सीने में दर्द", "seene mein dard"]),
    ("breathlessness", ["breathless", "shortness of breath", "difficulty breathing", "सांस", "साँस"]),
    ("stomach pain", ["stomach pain", "abdominal pain", "पेट दर्द", "pet dard", "पेट में दर्द"]),
    ("vomiting", ["vomit", "vomiting", "nausea", "उल्टी", "मतली"]),
    ("dizziness", ["dizzy", "dizziness", "चक्कर", "chakkar"]),
]

RED_FLAG_TERMS = [
    "chest pain", "सीने में दर्द", "breathless", "shortness of breath", "difficulty breathing",
    "सांस", "साँस", "bleeding", "खून", "unconscious", "बेहोश", "stroke", "paralysis", "लकवा",
]

INJECTION_MARKERS = [
    "ignore previous", "ignore the above", "system prompt", "you are now",
    "diagnose", "diagnosis", "prescribe", "prescription", "निदान", "दवा लिख",
]

NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10,
}

DURATION_RE = re.compile(
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|एक|दो|तीन|चार|पांच|पाँच|छह|सात|आठ|नौ|दस)"
    r"\s*(day|days|week|weeks|month|months|hour|hours|din|दिन|हफ्ते|हफ़्ते|महीने|महीना|घंटे)",
    re.IGNORECASE,
)
AGE_RE = re.compile(
    r"(\d{1,3})\s*(year|years|yr|yrs|saal|साल|वर्ष)", re.IGNORECASE
)


def _strip_injection(text):
    """Remove sentences that try to steer the model into clinical decisions."""
    warnings = []
    kept = []
    for sentence in re.split(r"(?<=[.!?।])\s+|\n+", text):
        low = sentence.lower()
        if any(m in low for m in INJECTION_MARKERS):
            warnings.append("Removed an instruction-like sentence from the transcript.")
            continue
        kept.append(sentence)
    return " ".join(kept).strip(), warnings


def _normalise_unit(unit):
    u = unit.lower()
    if u in ("day", "days", "din", "दिन"):
        return "days"
    if u in ("week", "weeks", "हफ्ते", "हफ़्ते"):
        return "weeks"
    if u in ("month", "months", "महीने", "महीना"):
        return "months"
    if u in ("hour", "hours", "घंटे"):
        return "hours"
    return u


def _duration(text):
    m = DURATION_RE.search(text)
    if not m:
        return None
    raw, unit = m.group(1), m.group(2)
    n = NUM_WORDS.get(raw.lower(), None)
    if n is None:
        try:
            n = int(raw)
        except ValueError:
            n = raw
    return f"{n} {_normalise_unit(unit)}"


def _severity(text):
    low = text.lower()
    if any(t in low for t in ["severe", "तेज़", "तेज", "गंभीर", "bad", "unbearable"]):
        return "severe"
    if any(t in low for t in ["moderate", "मध्यम"]):
        return "moderate"
    if any(t in low for t in ["mild", "हल्का", "slight"]):
        return "mild"
    return None


def _sex(text):
    low = text.lower()
    if any(t in low for t in ["female", "woman", "girl", "महिला", "औरत", "लड़की"]):
        return "female"
    if any(t in low for t in ["male", "man", "boy", "पुरुष", "आदमी", "लड़का"]):
        return "male"
    return None


def _after(text, triggers):
    """Return the short phrase following the first trigger, if any."""
    low = text.lower()
    for trig in triggers:
        i = low.find(trig)
        if i >= 0:
            tail = text[i + len(trig):].strip(" :,-।.")
            words = re.split(r"\s+", tail)
            if words and words[0]:
                return " ".join(words[:4]).strip(" .,।")
    return None


def extract(transcript):
    """Return (fields, warnings). fields only ever contains ALLOWED_KEYS."""
    text, warnings = _strip_injection(transcript or "")
    low = text.lower()

    fields = {}

    complaints = [label for label, terms in SYMPTOMS if any(t in low for t in terms)]
    if complaints:
        fields["chief_complaint"] = ", ".join(complaints)

    d = _duration(text)
    if d:
        fields["duration"] = d

    sev = _severity(text)
    if sev:
        fields["severity"] = sev

    age = AGE_RE.search(text)
    if age:
        fields["age"] = int(age.group(1))

    sx = _sex(text)
    if sx:
        fields["sex"] = sx

    meds = _after(text, ["taking ", "medicine ", "medicines ", "दवा ", "दवाई "])
    if meds:
        fields["medications"] = meds

    allergies = _after(text, ["allergic to ", "allergy to ", "एलर्जी "])
    if allergies:
        fields["allergies"] = allergies

    red = [t for t in RED_FLAG_TERMS if t in low]
    fields["red_flags"] = sorted(set(red))

    fields = {k: v for k, v in fields.items() if k in ALLOWED_KEYS}
    return fields, warnings


def validate(fields):
    """Reject anything outside the schema. Never coerce unexpected keys."""
    if not isinstance(fields, dict):
        raise ValueError("fields must be a dict")
    bad = set(fields) - ALLOWED_KEYS
    if bad:
        raise ValueError(f"out-of-schema keys: {sorted(bad)}")
    if "age" in fields and not isinstance(fields["age"], int):
        raise ValueError("age must be an int")
    if "red_flags" in fields and not isinstance(fields["red_flags"], list):
        raise ValueError("red_flags must be a list")
    return fields


if __name__ == "__main__":
    import json
    import sys
    text = " ".join(sys.argv[1:]) or "मुझे तीन दिन से बुखार और सिरदर्द है, हल्का है"
    print(json.dumps(extract(text), ensure_ascii=False, indent=2))
