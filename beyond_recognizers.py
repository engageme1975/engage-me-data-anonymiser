"""
Beyond Housing – Production Presidio Recognizers
Tuned for UK social housing repair / contact comments.
Includes research-backed UK NINO, phone and postcode patterns.
"""

from typing import List, Dict, Any, Optional, Set
from pathlib import Path
import sys
from presidio_analyzer import (
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
    AnalyzerEngine,
    EntityRecognizer,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider, NlpArtifacts
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
    "UK_ADDRESS",
}

# Generic role/status words that spaCy's NER occasionally misclassifies as
# PERSON in UK social-housing text. Passed to AnalyzerEngine.analyze() as an
# allow_list so they're never redacted, and also passed into
# scan_missed_proper_nouns (beyond_recognizers.py) so the same words don't
# flood the Residual Flags sheet as false-positive "possible missed name"
# noise - in a 12k-row test, "Tuesday" alone accounted for 1,796 of 2,785
# residual flags (64%), all false positives. Day names are unambiguous
# (nobody is named "Tuesday"); month names are deliberately NOT included
# here even though some showed up in the same testing, since several
# (May, April, June, August) are genuine common English first names and
# blanket-suppressing them would cost real recall, not just cut noise.
PERSON_FALSE_POSITIVE_ALLOW_LIST = [
    "Landlord", "Landlords", "Landlady", "Landladies",
    "Tenant", "Tenants", "Workman", "Workmen",
    "Contractor", "Contractors", "Occupant", "Occupants",
    "Resident", "Residents", "Neighbour", "Neighbours",
    "Multiple", "Mutliple",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
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

# Mirrors NAME_LABEL_PATTERN for website-form "Address: <value>" fields -
# catches the whole address value as one high-confidence block, which also
# covers town/county names inside it that spaCy's LOCATION recall misses.
ADDRESS_LABEL_PATTERN = r"(?<=Address: )[^\r\n]+"

# UK street address (house number + street name + a common street-type
# suffix), e.g. "33 Waveney Rd", "44 Greenland Avenue", "7 The Green",
# "34 herbert drive". Found via real Beyond Housing sample output: full
# street addresses were passing through completely unredacted, since
# UK_POSTCODE only matches the postcode itself and spaCy's LOCATION/GPE
# recall on informal address prose is unreliable (same known weak spot as
# PERSON - see beyond_recognizers module docs). Requires a recognisable
# street-type word since a bare "number + capitalised word" (e.g. "12
# Parkside", which has no suffix) is too easily confused with quantities,
# list items, or dates to match safely without one.
UK_STREET_SUFFIXES = (
    r"Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Court|Ct|Close|Lane|Ln|Way|"
    r"Green|Rise|Gardens|Grove|Crescent|Cres|Place|Pl|Terrace|Walk|Row|"
    r"Hill|Park|View|Mews|Square|Sq|Gate|Fields|Meadow|Common|Circus|"
    r"Parade|Wharf|Yard"
)
# A word (or "The") is required immediately before the suffix - without
# this, "digit + bare suffix" (e.g. "3 Court dates", "10 Bank holidays",
# "2 Park visits") would false-positive on ordinary English sentences,
# since several suffixes (Park, Green, Bank, Common, View, Way, Hill) are
# everyday words as well as street-name endings.
UK_STREET_ADDRESS_PATTERN = (
    r"\b\d{1,4}[A-Za-z]?[ ,]+"
    r"(?:(?:The[ ]+)|(?:[A-Za-z][a-zA-Z'’-]*[ ]+){1,3})"
    rf"(?:{UK_STREET_SUFFIXES})\b"
)

# UK street address with NO recognisable suffix (e.g. "12 Parkside", "45
# Setters Hill Estate") - previously a known, accepted gap: matching bare
# "number + word(s)" safely needs a real gazetteer, not a regex, since most
# short capitalised words after a number are quantities/list items/dates,
# not addresses ("3 Court dates", "10 Bank holidays" - see
# UK_STREET_ADDRESS_PATTERN above).
#
# Closed using OS Open Names (Ordnance Survey's free, open GB gazetteer -
# https://www.ordnancesurvey.co.uk/products/os-open-names): 372,801 unique
# "Named Road" entries, of which 69,143 (~18.5%) have no recognised street-
# type suffix word. Bundled locally as uk_road_names.txt (derived, ~5.9MB;
# the source ~106MB CSV download is not shipped).
#
# Auto-redaction is restricted to MULTI-WORD gazetteer matches (2-3 words,
# e.g. "Nikkavord Lea", "North Toogs", "Setters Hill Estate" - 54,851 of the
# 69,143 no-suffix names). A number followed by that exact multi-word
# sequence coinciding with ordinary prose by chance is negligible risk.
# Single-word matches (14,292 names, e.g. "Bank", "Camp", "Glen", "Roadside")
# are NOT auto-redacted - too many are ordinary short English words, and
# "4 Bank" wrongly eating "4 Bank holidays" is a worse trade than leaving it
# for manual review. Those are instead surfaced via residual_scan's
# gazetteer check below (POSSIBLE_UK_ADDRESS_GAZETTEER) so they're still
# flagged, not silently dropped.
def _load_road_gazetteer_files() -> tuple[Set[str], Set[str]]:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    gazetteer_path = base_dir / "uk_road_names.txt"
    multi_word: Set[str] = set()
    single_word: Set[str] = set()
    if not gazetteer_path.exists():
        return multi_word, single_word
    with gazetteer_path.open("r", encoding="utf-8") as f:
        for line in f:
            name = line.strip()
            if not name:
                continue
            key = name.lower()
            if " " in key:
                multi_word.add(key)
            else:
                single_word.add(key)
    return multi_word, single_word


UK_ROAD_GAZETTEER_MULTI_WORD, UK_ROAD_GAZETTEER_SINGLE_WORD = _load_road_gazetteer_files()

# House number + 1-3 capitalised words, used to find candidate phrases to
# check against the gazetteer sets above. Deliberately looser than
# UK_STREET_ADDRESS_PATTERN (no suffix requirement) since the gazetteer
# lookup itself - not a suffix word - is what confirms it's a real address.
UK_ADDRESS_CANDIDATE_PATTERN = re.compile(
    r"\b\d{1,4}[A-Za-z]?[ ,]+"
    r"(?:[A-Z][a-zA-Z'’-]*(?:[ ]+(?=[A-Z]))?){1,3}"
)


class UkGazetteerAddressRecognizer(EntityRecognizer):
    """
    Auto-redacts addresses with no street-type suffix by checking house-
    number-prefixed candidate phrases against the OS Open Names gazetteer -
    see the comment above UK_ROAD_GAZETTEER_MULTI_WORD for why this is
    restricted to multi-word matches only.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["UK_ADDRESS"],
            name="Beyond UK Gazetteer Address (no suffix)",
            supported_language="en",
        )

    def load(self) -> None:  # pragma: no cover - nothing to load
        pass

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
        if "UK_ADDRESS" not in entities and "ALL" not in entities:
            return []
        if not UK_ROAD_GAZETTEER_MULTI_WORD:
            return []

        results = []
        for match in UK_ADDRESS_CANDIDATE_PATTERN.finditer(text):
            matched = match.group()
            number_match = re.match(r"\d{1,4}[A-Za-z]?", matched)
            words_start = number_match.end()
            words_blob = matched[words_start:].strip(" ,")
            words = words_blob.split()
            if len(words) < 2:
                continue
            # Try the longest word-count phrase first (3 then 2 words) so a
            # 3-word gazetteer entry isn't missed in favour of a shorter one.
            for n in range(min(len(words), 3), 1, -1):
                phrase = " ".join(words[:n]).lower()
                if phrase in UK_ROAD_GAZETTEER_MULTI_WORD:
                    phrase_start = match.start() + matched.index(words[0], words_start)
                    phrase_end = phrase_start + len(" ".join(words[:n]))
                    results.append(
                        RecognizerResult(
                            entity_type="UK_ADDRESS",
                            start=match.start(),
                            end=phrase_end,
                            score=0.8,
                        )
                    )
                    break
        return results


# UK title + name, used in free-flowing complaint prose (e.g. "Miss Cole
# received a letter", "Mr & Mrs Judge of 8 Waterlow Road"). spaCy's NER
# inconsistently detects these short informal mentions, and in at least one
# case ("Munday") mistakes the surname for a misspelled day-of-week and
# tags it DATE_TIME instead of PERSON. Whitespace is restricted to spaces/
# tabs (not newlines) so it can't span into an unrelated capitalised word
# on the next line, such as an "Address:" or "Importance:" field label.
TITLE_NAME_PATTERN = (
    r"\b(?:Mr|Mrs|Miss|Ms|Mx)\.?[ \t]+"
    r"(?:&[ \t]+(?:Mr|Mrs|Miss|Ms|Mx)\.?[ \t]+)?"
    r"[A-Z][a-zA-Z'’-]*(?:[ \t]+[A-Z][a-zA-Z'’-]*){0,2}"
)




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
            # Bare reference numbers (e.g. "Tenancy Reference: 1578004013")
            # have no letter prefix to match on, unlike the styles above -
            # relies entirely on the "tenancy"/"reference" context words
            # below to clear the redaction threshold, the same low-base-
            # score-plus-context-boost approach ACCESS_CODE uses for bare
            # digits.
            Pattern("Bare long reference number", r"\b\d{6,12}\b", 0.3),
        ],
        context=[
            "property", "ref", "reference", "job", "repair", "tenancy",
            "tenant", "customer", "order", "works order", "bh-", "rep-", "ten-",
        ],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    # UK street addresses in free-flowing prose - see UK_STREET_ADDRESS_PATTERN
    # for why this needs its own recognizer (real sample data showed these
    # passing through completely unredacted).
    street_address_recognizer = PatternRecognizer(
        supported_entity="UK_ADDRESS",
        name="Beyond UK Street Address",
        patterns=[Pattern("Street address", UK_STREET_ADDRESS_PATTERN, 0.75)],
        context=[
            "address", "property", "flat", "house", "street", "road",
            "lane", "avenue", "moved", "tenant of", "tenancy",
        ],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    address_label_recognizer = PatternRecognizer(
        supported_entity="UK_ADDRESS",
        name="Beyond Address Label Field",
        patterns=[Pattern("Address: label", ADDRESS_LABEL_PATTERN, 0.90)],
        context=["address:"],
        supported_language="en",
        global_regex_flags=re.IGNORECASE,
    )

    gazetteer_address_recognizer = UkGazetteerAddressRecognizer()

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

    title_name_recognizer = PatternRecognizer(
        supported_entity="PERSON",
        name="Beyond Title + Name",
        patterns=[Pattern("Title name", TITLE_NAME_PATTERN, 0.75)],
        supported_language="en",
    )

    # Register custom recognizers (they take priority)
    registry.add_recognizer(housing_ref)
    registry.add_recognizer(postcode_recognizer)
    registry.add_recognizer(nino_recognizer)
    registry.add_recognizer(phone_recognizer)
    registry.add_recognizer(access_code)
    registry.add_recognizer(name_label_recognizer)
    registry.add_recognizer(title_name_recognizer)
    registry.add_recognizer(street_address_recognizer)
    registry.add_recognizer(address_label_recognizer)
    registry.add_recognizer(gazetteer_address_recognizer)

    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["en"],
        default_score_threshold=score_threshold,
    )
    return analyzer


# A match that is exactly a redaction tag (e.g. "<PERSON>", "<REDACTED>") is
# something the anonymiser already handled, not a leftover. Patterns that
# scan "the rest of the line" (NAME_LABEL_PATTERN) need this guard or every
# successfully redacted "Name: <PERSON>" line would falsely flag itself.
REDACTION_TAG_PATTERN = re.compile(r"^<[A-Z_]+>$")


def residual_scan(text: str) -> List[Dict[str, Any]]:
    """
    Residual safety net after the main Presidio pass.
    Flags possible leftover postcodes, phones, NINOs, long digit sequences,
    or person names (titled, untitled-but-in-a-call-log-phrase, or in a
    "Name:" field) that survived redaction. Untitled name recall is handled
    by scan_missed_proper_nouns (POS-tag based) instead of guessed phrasing -
    an earlier verb-phrase regex list here was removed after independent
    (Faker-generated) test data showed it barely generalised beyond the
    exact wording it was written against.
    """
    case_insensitive_patterns = [
        (UK_POSTCODE_PATTERN, "POSSIBLE_UK_POSTCODE"),
        (UK_MOBILE_PATTERN, "POSSIBLE_UK_MOBILE"),
        (UK_LANDLINE_PATTERN, "POSSIBLE_UK_PHONE"),
        (UK_NINO_PATTERN, "POSSIBLE_NINO"),
        (r"\b\d{8,}\b", "LONG_DIGIT_SEQUENCE"),
        (UK_STREET_ADDRESS_PATTERN, "POSSIBLE_UK_ADDRESS"),
        (ADDRESS_LABEL_PATTERN, "POSSIBLE_ADDRESS_LABEL"),
    ]

    # These rely on [A-Z] to mean "actually capitalised" as their proper-noun
    # signal - matching them case-insensitively (as the patterns above are)
    # would let [A-Z] match lowercase too and flood the audit sheet with
    # false positives on ordinary lowercase prose.
    case_sensitive_patterns = [
        (TITLE_NAME_PATTERN, "POSSIBLE_PERSON_TITLE"),
        (NAME_LABEL_PATTERN, "POSSIBLE_NAME_LABEL"),
    ]

    findings = []
    for pattern, label in case_insensitive_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matched_text = match.group()
            if REDACTION_TAG_PATTERN.match(matched_text.strip()):
                continue
            findings.append({
                "start": match.start(),
                "end": match.end(),
                "text": matched_text,
                "label": label,
            })

    for pattern, label in case_sensitive_patterns:
        for match in re.finditer(pattern, text):
            matched_text = match.group()
            if REDACTION_TAG_PATTERN.match(matched_text.strip()):
                continue
            findings.append({
                "start": match.start(),
                "end": match.end(),
                "text": matched_text,
                "label": label,
            })

    # Single-word OS Open Names gazetteer matches (e.g. "4 Bank", "12
    # Roadside") are deliberately not auto-redacted by
    # UkGazetteerAddressRecognizer - too many are ordinary short English
    # words to redact on a number + exact-match alone. Flagged here instead
    # so they still reach manual review rather than disappearing silently.
    if UK_ROAD_GAZETTEER_SINGLE_WORD:
        for match in UK_ADDRESS_CANDIDATE_PATTERN.finditer(text):
            matched_text = match.group()
            number_match = re.match(r"\d{1,4}[A-Za-z]?", matched_text)
            words_start = number_match.end()
            words_blob = matched_text[words_start:].strip(" ,")
            words = words_blob.split()
            if len(words) != 1:
                continue
            if words[0].lower() not in UK_ROAD_GAZETTEER_SINGLE_WORD:
                continue
            findings.append({
                "start": match.start(),
                "end": match.end(),
                "text": matched_text,
                "label": "POSSIBLE_UK_ADDRESS_GAZETTEER",
            })
    return findings


def scan_missed_proper_nouns(
    nlp_artifacts: Any,
    redaction_targets: List[Any],
    allow_list: List[str],
) -> List[Dict[str, Any]]:
    """
    Model-grounded residual check: flags spaCy proper-noun (POS=PROPN)
    tokens on the ORIGINAL text that fall outside every redacted span.

    Unlike TITLE_NAME_PATTERN / NAME_LABEL_PATTERN / UNTITLED_NAME_PATTERNS
    above (which guess at specific phrasings), this reads the model's own
    part-of-speech tagging directly - it has no assumptions about sentence
    structure, so it isn't tied to any particular test dataset's phrasing.

    It also catches cases the label-based analyzer pipeline cannot: Presidio's
    SpacyRecognizer only surfaces a handful of spaCy's raw NER labels
    (PERSON, ORG, DATE_TIME, LOCATION, NRP) via analyze() - a token spaCy
    tags with an unmapped label (e.g. PRODUCT) is invisible to analyze()
    even though spaCy's own tagger correctly recognised it as a proper
    noun. nlp_artifacts.entities holds spaCy's full raw entity list
    (pre-filtering), so that label is still visible here for a genuine
    off-label detection - included in the finding text so the reviewer
    can see what confused the model, not just that something was missed.
    """
    doc = nlp_artifacts.tokens
    raw_entity_by_span = {(ent.start_char, ent.end_char): ent.label_ for ent in nlp_artifacts.entities}

    flagged_tokens = []
    for token in doc:
        if token.pos_ != "PROPN":
            continue
        if not token.text or not token.text[0].isupper():
            continue
        # ALL-CAPS tokens (PII, REP, NINO, BH) are almost always acronyms
        # or reference-code prefixes, not names written in running prose -
        # names are Title Case. Single-letter tokens are initials, already
        # covered by TITLE_NAME_PATTERN when attached to a title.
        if len(token.text) > 1 and token.text.isupper():
            continue
        if token.text in allow_list:
            continue

        start, end = token.idx, token.idx + len(token.text)
        if any(start >= target.start and end <= target.end for target in redaction_targets):
            continue

        flagged_tokens.append((start, end))

    if not flagged_tokens:
        return []

    # Merge tokens separated only by whitespace (e.g. "R", "A", "Poile")
    # into a single finding instead of three adjacent rows.
    merged_spans = [flagged_tokens[0]]
    for start, end in flagged_tokens[1:]:
        prev_start, prev_end = merged_spans[-1]
        if start - prev_end <= 1:
            merged_spans[-1] = (prev_start, end)
        else:
            merged_spans.append((start, end))

    findings = []
    for start, end in merged_spans:
        off_label = raw_entity_by_span.get((start, end))
        label = f"POSSIBLE_MISSED_NAME (model tagged {off_label})" if off_label else "POSSIBLE_MISSED_NAME"
        findings.append({
            "start": start,
            "end": end,
            "text": doc.text[start:end],
            "label": label,
        })
    return findings