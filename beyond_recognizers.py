"""
Beyond Housing – Production Presidio Recognizers
Tuned for UK social housing repair / contact comments.
Includes research-backed UK NINO, phone and postcode patterns.
"""

from typing import List, Dict, Any
from presidio_analyzer import (
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
    AnalyzerEngine,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider
import re


# Only these entity types will be redacted
REDACTABLE_ENTITY_TYPES = {
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "UK_NINO",
    "UK_POSTCODE",
    "HOUSING_REF",
    "ACCESS_CODE",
}

# Generic role/status words that spaCy's NER occasionally misclassifies as
# PERSON in UK social-housing text. Passed to AnalyzerEngine.analyze() as an
# allow_list so they're never redacted, regardless of which recognizer or
# entity type flagged them.
PERSON_FALSE_POSITIVE_ALLOW_LIST = [
    "Landlord", "Landlords", "Landlady", "Landladies",
    "Tenant", "Tenants", "Workman", "Workmen",
    "Contractor", "Contractors", "Occupant", "Occupants",
    "Resident", "Residents", "Neighbour", "Neighbours",
    "Multiple", "Mutliple",
]


# ------------------------------------------------------------------
# Research-backed patterns
# ------------------------------------------------------------------

# Official-style UK postcode (includes GIR 0AA)
UK_POSTCODE_PATTERN = (
    r"\b(?:GIR ?0AA|"
    r"(?:[A-PR-UWYZ][0-9][0-9A-HJKMNPR-Y]?|"
    r"[A-PR-UWYZ][A-HK-Y][0-9][0-9ABEHMNPRV-Y]?) ?"
    r"[0-9][ABD-HJLNP-UW-Z]{2})\b"
)

# Strict UK NINO following HMRC rules
UK_NINO_PATTERN = (
    r"\b(?!BG|GB|KN|NK|NT|TN|ZZ)"
    r"[A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z]"
    r"\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b"
)
# Slightly more flexible fallback for recall
UK_NINO_FLEX_PATTERN = r"\b(?!BG|GB|KN|NK|NT|TN|ZZ)[A-Z]{2}\s?\d{6}\s?[A-D]\b"

# Flexible UK mobile (handles spaces, dashes, +44)
UK_MOBILE_PATTERN = (
    r"\b(?:"
    r"(?:\+44[\s\-]?7\d{3}[\s\-]?\d{6})|"
    r"(?:0?7\d{3}[\s\-]?\d{6})|"
    r"(?:\+44[\s\-]?7(?:[\s\-]?\d){9})|"
    r"(?:07(?:[\s\-]?\d){9})"
    r")\b"
)

# Flexible UK landline
UK_LANDLINE_PATTERN = r"\b(?:(?:\+44[\s\-]?|0)\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}|0\d{9,10})\b"

# Website-form "Name: <value>" field. spaCy's NER frequently misses titled
# names with initials (e.g. "Mr R A Poile"), so this structural label match
# catches the whole value up to end of line as a high-confidence fallback.
NAME_LABEL_PATTERN = r"(?<=Name: )[^\r\n]+"


def create_beyond_analyzer(score_threshold: float = 0.4) -> AnalyzerEngine:
    """
    Creates a ready-to-use AnalyzerEngine with:
    - All standard + UK recognizers
    - Strong custom UK postcode, NINO and phone patterns
    - Domain-specific housing references
    - Context-boosted key-safe / access codes
    """

    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_md"}],
    }
    provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
    nlp_engine = provider.create_engine()

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine)

    # ---------- Custom high-quality recognizers ----------

    postcode_recognizer = PatternRecognizer(
        supported_entity="UK_POSTCODE",
        name="Beyond UK Postcode",
        patterns=[Pattern("UK postcode", UK_POSTCODE_PATTERN, 0.92)],
        context=[
            "postcode", "post code", "address", "flat", "house",
            "street", "road", "lane", "avenue", "borough", "district",
        ],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    nino_recognizer = PatternRecognizer(
        supported_entity="UK_NINO",
        name="Beyond UK National Insurance Number",
        patterns=[
            Pattern("UK NINO strict", UK_NINO_PATTERN, 0.95),
            Pattern("UK NINO flexible", UK_NINO_FLEX_PATTERN, 0.78),
        ],
        context=[
            "national insurance", "nino", "ni number", "ni no",
            "insurance number", "national insurance number", "ni",
        ],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    phone_recognizer = PatternRecognizer(
        supported_entity="PHONE_NUMBER",
        name="Beyond UK Phone Number",
        patterns=[
            Pattern("UK mobile", UK_MOBILE_PATTERN, 0.94),
            Pattern("UK landline", UK_LANDLINE_PATTERN, 0.88),
        ],
        context=[
            "phone", "call", "mobile", "telephone", "tel", "contact",
            "ring", "number", "mobile number", "contact number",
        ],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    # Housing / Property / Repair / Tenancy references
    housing_ref = PatternRecognizer(
        supported_entity="HOUSING_REF",
        name="Beyond Housing Reference",
        patterns=[
            Pattern("BH style", r"\bBH[- ]?\d{3,6}\b", 0.70),
            Pattern("REP style", r"\bREP[- ]?(?:20)?\d{2}[- ]?\d{3,6}\b", 0.75),
            Pattern("TEN style", r"\bTEN(?:ANCY)?[- ]?\d{4,8}\b", 0.70),
            Pattern("CUS / Customer", r"\b(?:CUS|CUSTOMER)[- ]?\d{4,8}\b", 0.65),
            Pattern("JOB / REF / WO", r"\b(?:JOB|REF|PROP|WO|WORK)[- ]?\d{4,8}\b", 0.55),
        ],
        context=[
            "property", "ref", "reference", "job", "repair", "tenancy",
            "tenant", "customer", "order", "works order", "bh-", "rep-", "ten-",
        ],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    # Key-safe / Access codes
    access_code = PatternRecognizer(
        supported_entity="ACCESS_CODE",
        name="Key Safe / Access Code",
        patterns=[
            Pattern(
                "with explicit label",
                r"(?i)(?:key\s*safe|keysafe|access\s*code|pin\s*code|code|combination)[:\s#-]*(\d{4,6})\b",
                0.85,
            ),
            Pattern("standalone digits", r"\b\d{4,6}\b", 0.25),  # relies on context
        ],
        context=[
            "key safe", "keysafe", "access code", "access", "code",
            "pin", "combination", "leave key", "key with", "neighbour",
        ],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    name_label_recognizer = PatternRecognizer(
        supported_entity="PERSON",
        name="Beyond Name Label Field",
        patterns=[Pattern("Name: label", NAME_LABEL_PATTERN, 0.90)],
        context=["name:"],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    # Register custom recognizers (they take priority)
    registry.add_recognizer(housing_ref)
    registry.add_recognizer(postcode_recognizer)
    registry.add_recognizer(nino_recognizer)
    registry.add_recognizer(phone_recognizer)
    registry.add_recognizer(access_code)
    registry.add_recognizer(name_label_recognizer)

    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["en"],
        default_score_threshold=score_threshold,
    )
    return analyzer


def residual_scan(text: str) -> List[Dict[str, Any]]:
    """
    Residual safety net after the main Presidio pass.
    Flags possible leftover postcodes, phones, NINOs or long digit sequences.
    """
    patterns = [
        (UK_POSTCODE_PATTERN, "POSSIBLE_UK_POSTCODE"),
        (UK_MOBILE_PATTERN, "POSSIBLE_UK_MOBILE"),
        (UK_LANDLINE_PATTERN, "POSSIBLE_UK_PHONE"),
        (UK_NINO_PATTERN, "POSSIBLE_NINO"),
        (r"\b\d{8,}\b", "LONG_DIGIT_SEQUENCE"),
    ]

    findings = []
    for pattern, label in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            findings.append({
                "start": match.start(),
                "end": match.end(),
                "text": match.group(),
                "label": label,
            })
    return findings