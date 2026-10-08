"""
Automatic checks on a research card, run before a person ever looks at it and
again whenever it is edited. A card can only be approved when all of them pass.

The rule behind them: nothing on a card may be invented. The app shows what a
published study found, in plain words, so every number must come from the
study's own abstract, the DOI must lead to that study, and the wording must
describe what research found rather than tell anyone what to do.

Pure functions (no network), so they are fully covered by tests. The network
checks (does the DOI resolve? does it match the PubMed title?) happen in
utils/evidence_seed.py and are stored in the same `checks` record.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

# Words that turn "research found" into advice, a promise or a medical claim.
BANNED_WORDS = re.compile(
    r"\b(should|must|ought|need to|needs to|have to|recommend\w*|advise\w*|"
    r"you|your|yours|we|our|"
    r"cure[sd]?|cures|prevent(?:s|ed|ing)?|treat(?:s|ing)?|diagnos\w*|heal(?:s|ed|ing)?|"
    r"guarantee\w*|prove[sdn]?|proven|miracle|breakthrough|detox\w*|boost(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)
EVIDENCE_VERB = re.compile(r"\b(found|reported|showed|observed|concluded|identified|linked|associated|pooled)\b", re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w])\d[\d,]*(?:\.\d+)?")
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")

# The fields that make claims, and so are held to the rules above.
CLAIM_FIELDS = ("title", "plain_summary", "finding", "population", "caution_notes")


def numbers_in(text: Optional[str]) -> set[str]:
    """Every number in a piece of text, written plainly ("1,200" -> "1200", "0.50" -> "0.5")."""
    found: set[str] = set()
    for raw in NUMBER.findall(text or ""):
        cleaned = raw.replace(",", "").rstrip(".")
        if not cleaned:
            continue
        if "." in cleaned:
            cleaned = cleaned.rstrip("0").rstrip(".")
        found.add(cleaned)
    return found


def sentence_count(text: Optional[str]) -> int:
    return len(SENTENCE_END.findall((text or "").strip()))


def text_checks(card: dict, abstract: str) -> dict:
    """The checks that depend only on the card's own words and the abstract it came from."""
    allowed = numbers_in(abstract)
    claimed: set[str] = set()
    for field in CLAIM_FIELDS:
        claimed |= numbers_in(card.get(field))
    if card.get("sample_size") is not None:
        claimed.add(str(int(card["sample_size"])))
    unsupported = sorted(n for n in claimed if n not in allowed)

    banned: list[str] = []
    for field in CLAIM_FIELDS:
        banned += [m.group(0).lower() for m in BANNED_WORDS.finditer(card.get(field) or "")]
    banned = sorted(set(banned))

    finding = (card.get("finding") or "").strip()
    wording_problems = []
    if not EVIDENCE_VERB.search(finding):
        wording_problems.append('The finding should say what research "found" or "reported".')
    summary_sentences = sentence_count(card.get("plain_summary"))
    if not 2 <= summary_sentences <= 4:
        wording_problems.append(f"The summary has {summary_sentences} sentences; it should have 2 to 4.")
    if not finding:
        wording_problems.append("The finding is empty.")

    problems: list[str] = []
    if unsupported:
        problems.append("Numbers not in the abstract: " + ", ".join(unsupported))
    if banned:
        problems.append("Wording that tells people what to do or makes a claim: " + ", ".join(banned))
    problems += wording_problems

    return {
        "numbers_ok": not unsupported,
        "unsupported_numbers": unsupported,
        "wording_ok": not banned and not wording_problems,
        "banned_found": banned,
        "problems": problems,
    }


def can_approve(checks: dict) -> bool:
    """True only when every automatic check passed (a missing network check counts as not passed)."""
    return bool(
        checks.get("numbers_ok")
        and checks.get("wording_ok")
        and checks.get("doi_ok")
        and checks.get("title_match")
    )


def blocking_problems(checks: dict) -> list[str]:
    problems = list(checks.get("problems") or [])
    if not checks.get("doi_ok"):
        problems.append("The DOI doesn't resolve.")
    if not checks.get("title_match"):
        problems.append("The DOI's title doesn't match the PubMed record.")
    return problems


# ── PubMed ───────────────────────────────────────────────────────────────────

def study_type_from(pub_types: list[str]) -> Optional[str]:
    """Only meta-analyses and randomised trials are used."""
    lowered = {t.lower() for t in pub_types}
    if "meta-analysis" in lowered:
        return "meta-analysis"
    if "randomized controlled trial" in lowered:
        return "RCT"
    return None


def normalise_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = doi.strip()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.IGNORECASE)
    return doi if doi.startswith("10.") else None


def title_similarity(a: str, b: str) -> float:
    """Share of words two titles have in common (0..1), ignoring case and punctuation."""
    def words(t: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", (t or "").lower()))

    wa, wb = words(a), words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def _text(elem: Optional[ET.Element]) -> str:
    return "".join(elem.itertext()).strip() if elem is not None else ""


def parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Articles from PubMed's efetch XML: id, title, abstract, journal, year, DOI and publication types."""
    root = ET.fromstring(xml_text)
    articles = []
    for node in root.iter("PubmedArticle"):
        pmid = _text(node.find("./MedlineCitation/PMID"))
        article = node.find("./MedlineCitation/Article")
        if article is None or not pmid:
            continue
        parts = []
        for section in article.findall("./Abstract/AbstractText"):
            label = section.attrib.get("Label")
            body = _text(section)
            if body:
                parts.append(f"{label.capitalize()}: {body}" if label else body)
        year = _text(article.find("./Journal/JournalIssue/PubDate/Year"))
        if not year:
            medline = _text(article.find("./Journal/JournalIssue/PubDate/MedlineDate"))
            m = re.search(r"(19|20)\d{2}", medline)
            year = m.group(0) if m else _text(article.find("./ArticleDate/Year"))
        doi = None
        for aid in node.findall("./PubmedData/ArticleIdList/ArticleId"):
            if aid.attrib.get("IdType") == "doi":
                doi = normalise_doi(_text(aid))
        articles.append(
            {
                "pubmed_id": pmid,
                "title": _text(article.find("./ArticleTitle")).rstrip("."),
                "abstract": " ".join(parts),
                "journal": _text(article.find("./Journal/Title")),
                "year": int(year) if year.isdigit() else None,
                "doi": doi,
                "pub_types": [_text(p) for p in article.findall("./PublicationTypeList/PublicationType")],
            }
        )
    return articles
