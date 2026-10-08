"""
Builds the research library: finds meta-analyses and randomised trials on
PubMed for each topic, has Claude draft a plain-English card strictly from the
abstract, checks the DOI, and saves the card as NOT approved.

Nothing here can show a card to a user. Approval is a separate human step
(routers/evidence_admin.py), and only approved cards are ever read by the app.

Claude is given one abstract and may use nothing else. Its draft is then held to
the checks in utils/evidence_checks.py (every number must appear in the abstract,
no advice wording). The draft is never trusted on its own.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import httpx

from utils.evidence_checks import (
    allowed_numbers,
    medication_count,
    normalise_doi,
    parse_pubmed_xml,
    study_type_from,
    text_checks,
    title_similarity,
)
from utils.evidence_topics import Topic

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.getenv("EVIDENCE_MODEL", "claude-sonnet-4-6")
CONTACT_EMAIL = "hello@causalme.com"

MIN_ABSTRACT_CHARS = 400
EARLIEST_YEAR = 2010
SEARCH_RESULTS = 15
SUPPLEMENT_CAUTION = "Supplements can interact with medicines and aren't right for everyone. Talk to a doctor or pharmacist before starting one."
GENERIC_CAUTION = "These are averages across groups of people, so results for any one person can differ."

SYSTEM_PROMPT = """You turn one published research abstract into a short card for a health app.

You may use ONLY information stated in the abstract you are given. Never add numbers, results, populations or claims that are not in it. Copy every number exactly as it is written in the abstract: the same digits and decimals. Never round, convert, combine or work out a new number (no averages, differences or totals). If the abstract says "7 randomized controlled trials and 1 quasi-experimental study", write exactly that, never "8 studies". Write plain English for a general reader. Describe what the research found. Never give advice, instructions or recommendations, and never address the reader. Do not use these words anywhere: you, your, we, our, should, must, recommend, advise, cure, prevent, treat, heal, boost, prove, proven, guarantee.

Return a single JSON object and nothing else."""

USER_TEMPLATE = """Topic: {topic}
Study type: {study_type}
Journal: {journal} ({year})

Abstract:
{abstract}

Return JSON with exactly these keys:
- "skip": true if the abstract has no clear result, is only about people with serious disease, is about a drug or medicine, or is otherwise a poor fit for everyday health. Otherwise false.
- "skip_reason": a few words, or null.
- "title": a plain topic title of 4 to 10 words, no numbers.
- "plain_summary": 2 or 3 sentences saying what was studied and what it showed, no jargon.
- "finding": 1 or 2 sentences that include the word "found" and give the key result using only numbers that appear in the abstract. For a meta-analysis start like "Across the studies pooled, research found". For a single trial start like "In this trial, researchers found".
- "population": who was studied, as a short phrase taken from the abstract.
- "sample_size": the total number of participants if the abstract states it, otherwise null (an integer).
- "caution_notes": 1 or 2 sentences on limits stated or implied by the abstract (study type, small samples, short duration, mixed quality, a specific group). If the abstract states none, say the results are averages across groups and individual results can differ.
- "experiment_label": if the thing studied is a simple everyday behaviour someone could try for 14 days (a walk, a screen-free hour before bed, a regular bedtime), a short noun phrase for it, such as "A screen-free hour before bed". Use only quantities mentioned in the abstract, or none. Otherwise null. Always null for supplements, medicines, diets, fasting or anything medical."""


@dataclass
class SeedStatus:
    running: bool = False
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_topic: str = ""
    topics_total: int = 0
    topics_done: int = 0
    added: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "running": self.running, "started_at": self.started_at, "finished_at": self.finished_at,
            "current_topic": self.current_topic, "topics_total": self.topics_total, "topics_done": self.topics_done,
            "added": self.added, "skipped": self.skipped, "errors": self.errors[-15:],
        }


STATUS = SeedStatus()


def _sb_url(table: str) -> str:
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/rest/v1/{table}"


def _sb_headers(prefer: str = "") -> dict:
    key = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    h = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def build_term(query: str) -> str:
    return (
        f"({query}) AND (meta-analysis[pt] OR randomized controlled trial[pt]) "
        f'AND humans[mh] AND english[la] AND hasabstract AND ("{EARLIEST_YEAR}"[dp] : "3000"[dp])'
    )


def _ncbi_params(extra: dict) -> dict:
    params = {"tool": "thegap", "email": CONTACT_EMAIL, **extra}
    key = os.getenv("NCBI_API_KEY", "").strip()
    if key:
        params["api_key"] = key
    return params


async def search_pubmed(client: httpx.AsyncClient, topic: Topic) -> list[str]:
    resp = await client.get(ESEARCH_URL, params=_ncbi_params({"db": "pubmed", "term": build_term(topic.query), "retmax": str(SEARCH_RESULTS), "retmode": "json", "sort": "relevance"}))
    resp.raise_for_status()
    return resp.json().get("esearchresult", {}).get("idlist", [])


async def fetch_pubmed(client: httpx.AsyncClient, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    resp = await client.get(EFETCH_URL, params=_ncbi_params({"db": "pubmed", "id": ",".join(ids), "retmode": "xml"}))
    resp.raise_for_status()
    return parse_pubmed_xml(resp.text)


def rank_candidates(articles: list[dict]) -> list[dict]:
    """Usable articles, meta-analyses before single trials, newer first."""
    usable = []
    for a in articles:
        study_type = study_type_from(a["pub_types"])
        if not study_type or len(a["abstract"]) < MIN_ABSTRACT_CHARS or not a.get("year") or a["year"] < EARLIEST_YEAR:
            continue
        # Medicines and weight-loss drugs are outside what this library is for.
        if medication_count(a["title"]) or medication_count(a["abstract"]) >= 3:
            continue
        usable.append({**a, "study_type": study_type})
    usable.sort(key=lambda a: (a["study_type"] != "meta-analysis", -(a["year"] or 0)))
    return usable


async def check_doi(client: httpx.AsyncClient, doi: Optional[str], pubmed_title: str) -> dict:
    """Does the DOI resolve at doi.org, and does what it points to carry the same title as PubMed's record?"""
    doi = normalise_doi(doi)
    result: dict = {"doi_ok": False, "title_match": False, "doi": doi}
    if not doi:
        return result
    try:
        handle = await client.get(f"https://doi.org/api/handles/{doi}")
        result["doi_ok"] = handle.status_code == 200 and handle.json().get("responseCode") == 1
    except Exception as exc:
        logger.info("DOI handle lookup failed for %s: %s", doi, exc)
    try:
        crossref = await client.get(f"https://api.crossref.org/works/{doi}", params={"mailto": CONTACT_EMAIL})
        if crossref.status_code == 200:
            titles = crossref.json().get("message", {}).get("title") or []
            if titles:
                score = title_similarity(titles[0], pubmed_title)
                result["title_match"] = score >= 0.7
                result["title_score"] = round(score, 2)
    except Exception as exc:
        logger.info("Crossref lookup failed for %s: %s", doi, exc)
    return result


def parse_draft(text: str) -> Optional[dict]:
    """The JSON object in Claude's reply, or None."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def draft_card(client: httpx.AsyncClient, article: dict, topic: Topic) -> Optional[dict]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set on the server.")
    prompt = USER_TEMPLATE.format(
        topic=topic.query.replace('"', ""), study_type=article["study_type"], journal=article["journal"], year=article["year"], abstract=article["abstract"]
    )
    resp = await client.post(
        ANTHROPIC_API_URL,
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 900, "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": prompt}]},
        timeout=90,
    )
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json().get("content", []) if b.get("type") == "text")
    return parse_draft(text)


def build_rows(article: dict, topic: Topic, draft: dict, doi_check: dict) -> tuple[dict, dict]:
    """(evidence_cards row, evidence_sources row) for a drafted article."""
    sample = draft.get("sample_size")
    if not isinstance(sample, int) or isinstance(sample, bool) or str(sample) not in allowed_numbers(article["abstract"]):
        sample = None  # only a figure printed in the abstract is kept

    caution = (draft.get("caution_notes") or "").strip() or GENERIC_CAUTION
    if topic.supplement and SUPPLEMENT_CAUTION not in caution:
        caution = f"{caution} {SUPPLEMENT_CAUTION}"

    experiment = (draft.get("experiment_label") or "").strip() or None
    if topic.supplement:
        experiment = None  # never suggest self-testing a supplement

    card = {
        "category": topic.category,
        "title": (draft.get("title") or article["title"]).strip(),
        "plain_summary": (draft.get("plain_summary") or "").strip(),
        "finding": (draft.get("finding") or "").strip(),
        "metric_tags": list(topic.tags),
        "study_type": article["study_type"],
        "sample_size": sample,
        "population": (draft.get("population") or "").strip() or None,
        "year": article["year"],
        "journal": article["journal"] or None,
        "doi": doi_check.get("doi"),
        "pubmed_id": article["pubmed_id"],
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{article['pubmed_id']}/",
        "caution_notes": caution,
        "experiment_label": experiment,
        "experiment_days": 14,
        "weight_related": topic.weight_related,
        "verified": False,
        "rejected": False,
    }
    checks = {**text_checks(card, article["abstract"]), "doi_ok": doi_check["doi_ok"], "title_match": doi_check["title_match"], "title_score": doi_check.get("title_score")}
    source = {
        "pubmed_title": article["title"],
        "abstract": article["abstract"],
        "checks": checks,
        "drafted_by": MODEL,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    return card, source


async def _existing_ids(client: httpx.AsyncClient, pubmed_ids: list[str]) -> set[str]:
    if not pubmed_ids:
        return set()
    resp = await client.get(_sb_url("evidence_cards"), headers=_sb_headers(), params={"pubmed_id": f"in.({','.join(pubmed_ids)})", "select": "pubmed_id"})
    resp.raise_for_status()
    return {r["pubmed_id"] for r in resp.json() or []}


async def _save(client: httpx.AsyncClient, card: dict, source: dict) -> bool:
    resp = await client.post(
        _sb_url("evidence_cards"),
        headers=_sb_headers("return=representation,resolution=ignore-duplicates"),
        params={"on_conflict": "pubmed_id"},
        json=card,
    )
    resp.raise_for_status()
    rows = resp.json() or []
    if not rows:
        return False
    source_resp = await client.post(
        _sb_url("evidence_sources"), headers=_sb_headers("return=minimal,resolution=merge-duplicates"), params={"on_conflict": "card_id"}, json={"card_id": rows[0]["id"], **source}
    )
    source_resp.raise_for_status()
    return True


async def seed_topic(client: httpx.AsyncClient, topic: Topic, per_topic: int) -> tuple[int, int]:
    """(added, skipped) for one topic."""
    ids = await search_pubmed(client, topic)
    await asyncio.sleep(0.4)
    articles = rank_candidates(await fetch_pubmed(client, ids))
    await asyncio.sleep(0.4)
    known = await _existing_ids(client, [a["pubmed_id"] for a in articles])
    added = skipped = 0
    for article in [a for a in articles if a["pubmed_id"] not in known][:per_topic]:
        try:
            draft = await draft_card(client, article, topic)
        except Exception as exc:
            STATUS.errors.append(f"{topic.query[:40]}: drafting failed ({exc})")
            skipped += 1
            continue
        if not draft or draft.get("skip") or not draft.get("finding") or not draft.get("plain_summary"):
            skipped += 1
            continue
        doi_check = await check_doi(client, article.get("doi"), article["title"])
        card, source = build_rows(article, topic, draft, doi_check)
        try:
            if await _save(client, card, source):
                added += 1
        except Exception as exc:
            STATUS.errors.append(f"{topic.query[:40]}: saving failed ({exc})")
            skipped += 1
    return added, skipped


async def run_seed(topics: list[Topic], per_topic: int = 2) -> None:
    """Runs the whole collection in the background, reporting progress through STATUS."""
    if STATUS.running:
        return
    STATUS.running, STATUS.errors = True, []
    STATUS.started_at, STATUS.finished_at = datetime.now(timezone.utc).isoformat(), None
    STATUS.topics_total, STATUS.topics_done, STATUS.added, STATUS.skipped = len(topics), 0, 0, 0
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for topic in topics:
                STATUS.current_topic = topic.query[:60]
                try:
                    added, skipped = await seed_topic(client, topic, per_topic)
                    STATUS.added += added
                    STATUS.skipped += skipped
                except Exception as exc:
                    STATUS.errors.append(f"{topic.query[:40]}: {exc}")
                    logger.warning("Evidence seed failed for %s: %s", topic.query, exc)
                STATUS.topics_done += 1
    finally:
        STATUS.running = False
        STATUS.current_topic = ""
        STATUS.finished_at = datetime.now(timezone.utc).isoformat()
        logger.info("EVIDENCE_SEED_DONE added=%d skipped=%d errors=%d", STATUS.added, STATUS.skipped, len(STATUS.errors))
