import asyncio

import pytest
from fastapi import HTTPException

from routers import evidence_admin
from utils import evidence, evidence_seed
from utils.evidence_checks import (
    blocking_problems,
    can_approve,
    normalise_doi,
    numbers_in,
    parse_pubmed_xml,
    study_type_from,
    text_checks,
    title_similarity,
)
from utils.evidence_topics import CATEGORY_KEYS, TOPICS, topics_for

ABSTRACT = (
    "Background: Poor sleep is common. Methods: We pooled 24 randomized trials with 1,847 adults. "
    "Results: Evening screen use was linked to 0.5 hours less sleep (95% CI 0.2 to 0.8). "
    "Conclusions: Effects were small and varied between studies."
)

GOOD = {
    "title": "Evening screens and sleep time",
    "plain_summary": "Researchers pooled the results of many trials on evening screen use. They looked at how long adults slept. Studies varied a lot in how they measured it.",
    "finding": "Across the studies pooled, research found about 0.5 hours less sleep after evening screen use.",
    "population": "Adults across 24 trials",
    "sample_size": 1847,
    "caution_notes": "Effects were small and varied between studies.",
}


# ── the automatic checks ─────────────────────────────────────────────────────

def test_numbers_are_compared_in_plain_form():
    assert numbers_in("1,847 adults, 0.50 hours, 95% CI 0.2 to 0.8") == {"1847", "0.5", "95", "0.2", "0.8"}


def test_a_card_built_from_the_abstract_passes():
    checks = text_checks(GOOD, ABSTRACT)
    assert checks["numbers_ok"] and checks["wording_ok"], checks["problems"]


def test_a_number_that_is_not_in_the_abstract_is_caught():
    bad = {**GOOD, "finding": "Across the studies pooled, research found about 1.5 hours less sleep."}
    checks = text_checks(bad, ABSTRACT)
    assert not checks["numbers_ok"] and "1.5" in checks["unsupported_numbers"]


def test_a_made_up_sample_size_is_caught():
    checks = text_checks({**GOOD, "sample_size": 2500}, ABSTRACT)
    assert "2500" in checks["unsupported_numbers"]


@pytest.mark.parametrize("word", ["you", "your", "should", "must", "recommend", "cure", "prevent", "boost", "proven", "treat"])
def test_advice_and_claim_words_are_caught(word):
    bad = {**GOOD, "plain_summary": f"Researchers studied screens. People {word} this. It was measured in trials."}
    checks = text_checks(bad, ABSTRACT)
    assert not checks["wording_ok"] and word in checks["banned_found"]


def test_ordinary_research_words_are_not_flagged():
    ok = {**GOOD, "plain_summary": "Researchers compared a treatment group with a control group. They measured sleep. The prevention of insomnia was not tested."}
    assert text_checks(ok, ABSTRACT)["wording_ok"] is True  # "treatment" and "prevention" are different words from "treat" and "prevent"


def test_the_finding_must_say_what_research_found():
    checks = text_checks({**GOOD, "finding": "Evening screen use means 0.5 hours less sleep."}, ABSTRACT)
    assert not checks["wording_ok"]


def test_the_summary_must_be_two_to_four_sentences():
    assert not text_checks({**GOOD, "plain_summary": "One sentence only."}, ABSTRACT)["wording_ok"]


def test_approval_needs_every_check():
    passing = {**text_checks(GOOD, ABSTRACT), "doi_ok": True, "title_match": True}
    assert can_approve(passing)
    assert not can_approve({**passing, "doi_ok": False})
    assert not can_approve({**passing, "title_match": False})
    assert not can_approve({**passing, "numbers_ok": False})
    assert not can_approve({})  # no checks recorded counts as not passed
    assert any("DOI" in p for p in blocking_problems({**passing, "doi_ok": False}))


# ── PubMed records ───────────────────────────────────────────────────────────

XML = """<?xml version="1.0"?>
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation>
   <PMID Version="1">123456</PMID>
   <Article>
    <Journal><JournalIssue><PubDate><Year>2021</Year></PubDate></JournalIssue><Title>Sleep Medicine Reviews</Title></Journal>
    <ArticleTitle>Evening screen use and <i>sleep</i> duration: a meta-analysis.</ArticleTitle>
    <Abstract>
     <AbstractText Label="BACKGROUND">Poor sleep is common.</AbstractText>
     <AbstractText Label="RESULTS">We pooled 24 trials.</AbstractText>
    </Abstract>
    <PublicationTypeList><PublicationType>Meta-Analysis</PublicationType><PublicationType>Systematic Review</PublicationType></PublicationTypeList>
   </Article>
  </MedlineCitation>
  <PubmedData><ArticleIdList><ArticleId IdType="pubmed">123456</ArticleId><ArticleId IdType="doi">10.1016/j.smrv.2021.101234</ArticleId></ArticleIdList></PubmedData>
 </PubmedArticle>
</PubmedArticleSet>"""


def test_a_pubmed_record_is_read_correctly():
    [article] = parse_pubmed_xml(XML)
    assert article["pubmed_id"] == "123456" and article["year"] == 2021
    assert article["title"] == "Evening screen use and sleep duration: a meta-analysis"
    assert article["abstract"] == "Background: Poor sleep is common. Results: We pooled 24 trials."
    assert article["doi"] == "10.1016/j.smrv.2021.101234" and article["journal"] == "Sleep Medicine Reviews"
    assert study_type_from(article["pub_types"]) == "meta-analysis"


def test_only_meta_analyses_and_trials_are_used():
    assert study_type_from(["Randomized Controlled Trial"]) == "RCT"
    assert study_type_from(["Review"]) is None
    assert study_type_from(["Systematic Review"]) is None  # a review without a pooled analysis isn't enough


def test_dois_are_normalised_and_titles_compared():
    assert normalise_doi("https://doi.org/10.1000/xyz123") == "10.1000/xyz123"
    assert normalise_doi("doi: 10.1000/xyz123") == "10.1000/xyz123"
    assert normalise_doi("not a doi") is None and normalise_doi(None) is None
    assert title_similarity("Evening screens and sleep", "Evening Screens and Sleep.") == 1.0
    assert title_similarity("Evening screens and sleep", "Cholesterol in mice") < 0.2


# ── drafting a card ──────────────────────────────────────────────────────────

ARTICLE = {"pubmed_id": "123456", "title": "Evening screens and sleep", "abstract": ABSTRACT, "journal": "Sleep Reviews", "year": 2021, "study_type": "meta-analysis", "doi": "10.1000/x", "pub_types": ["Meta-Analysis"]}
DRAFT = {**GOOD, "skip": False, "experiment_label": "A screen-free hour before bed"}
DOI_OK = {"doi": "10.1000/x", "doi_ok": True, "title_match": True, "title_score": 0.95}


def test_a_new_card_starts_unapproved_and_keeps_its_abstract_privately():
    card, source = evidence_seed.build_rows(ARTICLE, TOPICS[0], DRAFT, DOI_OK)
    assert card["verified"] is False and card["rejected"] is False
    assert source["abstract"] == ABSTRACT and "abstract" not in card
    assert card["url"] == "https://pubmed.ncbi.nlm.nih.gov/123456/"
    assert can_approve(source["checks"])


def test_a_sample_size_that_is_not_printed_in_the_abstract_is_dropped():
    card, _ = evidence_seed.build_rows(ARTICLE, TOPICS[0], {**DRAFT, "sample_size": 99999}, DOI_OK)
    assert card["sample_size"] is None
    card, _ = evidence_seed.build_rows(ARTICLE, TOPICS[0], DRAFT, DOI_OK)
    assert card["sample_size"] == 1847


def test_supplement_cards_carry_a_caution_and_never_offer_an_experiment():
    supplement = next(t for t in TOPICS if t.supplement)
    card, _ = evidence_seed.build_rows(ARTICLE, supplement, DRAFT, DOI_OK)
    assert card["experiment_label"] is None and "doctor or pharmacist" in card["caution_notes"]
    behaviour = next(t for t in TOPICS if not t.supplement)
    assert evidence_seed.build_rows(ARTICLE, behaviour, DRAFT, DOI_OK)[0]["experiment_label"] == "A screen-free hour before bed"


def test_a_card_that_failed_the_doi_check_cannot_be_approved():
    _, source = evidence_seed.build_rows(ARTICLE, TOPICS[0], DRAFT, {"doi": None, "doi_ok": False, "title_match": False})
    assert not can_approve(source["checks"])


def test_candidates_prefer_meta_analyses_then_newer_trials():
    long_abstract = "x" * 500
    pool = [
        {**ARTICLE, "pubmed_id": "1", "abstract": long_abstract, "pub_types": ["Randomized Controlled Trial"], "year": 2024},
        {**ARTICLE, "pubmed_id": "2", "abstract": long_abstract, "pub_types": ["Meta-Analysis"], "year": 2018},
        {**ARTICLE, "pubmed_id": "3", "abstract": "too short", "pub_types": ["Meta-Analysis"], "year": 2024},
        {**ARTICLE, "pubmed_id": "4", "abstract": long_abstract, "pub_types": ["Review"], "year": 2024},
        {**ARTICLE, "pubmed_id": "5", "abstract": long_abstract, "pub_types": ["Meta-Analysis"], "year": 2005},
    ]
    assert [a["pubmed_id"] for a in evidence_seed.rank_candidates(pool)] == ["2", "1"]


def test_claudes_reply_is_read_even_when_wrapped_in_code_fences():
    assert evidence_seed.parse_draft('```json\n{"skip": false, "finding": "x"}\n```') == {"skip": False, "finding": "x"}
    assert evidence_seed.parse_draft("no json here") is None


def test_the_search_asks_only_for_meta_analyses_and_trials_in_people():
    term = evidence_seed.build_term('"sleep hygiene"')
    assert "meta-analysis[pt]" in term and "randomized controlled trial[pt]" in term and "humans[mh]" in term


def test_every_category_has_topics_and_tags_are_real_goal_metrics():
    from utils.goal_catalog import GOAL_METRICS

    assert {t.category for t in TOPICS} == set(CATEGORY_KEYS)
    for t in TOPICS:
        assert t.tags and all(tag in GOAL_METRICS for tag in t.tags), t
    assert all(t.category == "sleep" for t in topics_for(["sleep"]))


# ── only approved cards are ever read for display ────────────────────────────

def test_reads_for_display_always_filter_to_approved_cards():
    params = evidence.verified_params({"id": "eq.1"})
    assert params["verified"] == "eq.true" and params["rejected"] == "eq.false"
    assert "abstract" not in params["select"] and "checks" not in params["select"]


# ── the admin routes ─────────────────────────────────────────────────────────

def test_admin_routes_are_hidden_until_a_secret_is_set_and_need_it(monkeypatch):
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    with pytest.raises(HTTPException) as err:
        evidence_admin.require_admin("anything")
    assert err.value.status_code == 404
    monkeypatch.setenv("ADMIN_SECRET", "s3cret")
    with pytest.raises(HTTPException) as err:
        evidence_admin.require_admin("wrong")
    assert err.value.status_code == 401
    assert evidence_admin.require_admin("s3cret") is None


class _Resp:
    def __init__(self, rows=None):
        self._rows = rows if rows is not None else []

    def raise_for_status(self):
        pass

    def json(self):
        return self._rows


def _fake_admin_db(monkeypatch, card, source):
    patches = []

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def patch(self, url, headers=None, params=None, json=None):
            patches.append((url.rsplit("/", 1)[-1], json))
            return _Resp([{}])

    async def get_card(client, card_id):
        return card, source

    monkeypatch.setattr(evidence_admin.httpx, "AsyncClient", lambda **kw: _Client())
    monkeypatch.setattr(evidence_admin, "_get_card_with_source", get_card)
    return patches


def _stored(card, **checks):
    return {"abstract": ABSTRACT, "checks": {"doi_ok": True, "title_match": True, **checks}}


def test_approving_a_card_that_passes_marks_it_verified(monkeypatch):
    card = {"id": "c1", **GOOD}
    patches = _fake_admin_db(monkeypatch, card, _stored(card))
    response = asyncio.run(evidence_admin.approve("c1"))
    assert response.status_code == 200
    update = next(p for table, p in patches if table == "evidence_cards")
    assert update["verified"] is True and update["verified_at"]


def test_a_card_that_fails_the_checks_cannot_be_approved(monkeypatch):
    card = {"id": "c1", **GOOD, "finding": "Research found 9.9 hours less sleep."}
    patches = _fake_admin_db(monkeypatch, card, _stored(card))
    response = asyncio.run(evidence_admin.approve("c1"))
    assert response.status_code == 409
    assert not any(table == "evidence_cards" for table, _ in patches)


def test_a_card_whose_doi_failed_cannot_be_approved_even_if_the_words_are_fine(monkeypatch):
    card = {"id": "c1", **GOOD}
    _fake_admin_db(monkeypatch, card, _stored(card, doi_ok=False))
    assert asyncio.run(evidence_admin.approve("c1")).status_code == 409


def test_editing_a_card_reruns_the_checks_and_can_clear_a_problem(monkeypatch):
    card = {"id": "c1", **GOOD, "finding": "Research found 9.9 hours less sleep."}
    patches = _fake_admin_db(monkeypatch, card, _stored(card))
    body = evidence_admin.EditBody(finding="Across the studies pooled, research found about 0.5 hours less sleep.")
    result = asyncio.run(evidence_admin.edit_card("c1", body))
    assert b'"can_approve":true' in result.body.replace(b" ", b"")
    assert any(table == "evidence_sources" for table, _ in patches)


def test_an_approved_card_must_be_unapproved_before_it_can_be_edited(monkeypatch):
    card = {"id": "c1", **GOOD, "verified": True}
    _fake_admin_db(monkeypatch, card, _stored(card))
    with pytest.raises(HTTPException) as err:
        asyncio.run(evidence_admin.edit_card("c1", evidence_admin.EditBody(title="New title")))
    assert err.value.status_code == 409


# ── false alarms seen on real PubMed abstracts ───────────────────────────────

REAL_ABSTRACT = (
    "Twenty randomised controlled trials (RCTs) comprising 15\u2009782 participants met inclusion criteria. "
    "Lean mass constituted 25%-39% of total weight lost (35.2% [95% CI: 31.5-38.9]; p\u2009=\u20090.42). "
    "Lifestyle plus resistance training demonstrated the most favourable profile (17.5% [14.2-20.8]). Heterogeneity was moderate (I2\u2009=\u200968%)."
)


def _card(**fields):
    return {**GOOD, **fields}


def test_a_thousands_separator_written_as_a_thin_space_is_read_as_one_number():
    assert numbers_in("15\u2009782 participants") == {"15782"}
    card = _card(finding="Across the studies pooled, research found results in 15,782 participants.", population="Adults", sample_size=15782)
    assert text_checks(card, REAL_ABSTRACT)["numbers_ok"]


def test_a_number_spelled_out_in_the_abstract_may_be_written_as_digits():
    card = _card(finding="Across the studies pooled, research found results from 20 trials.", population="Adults in 20 trials", sample_size=None)
    assert text_checks(card, REAL_ABSTRACT)["numbers_ok"]
    assert "21" in __import__("utils.evidence_checks", fromlist=["x"]).allowed_numbers("Twenty-one trials")


def test_a_rounded_figure_is_still_caught():
    card = _card(finding="Across the studies pooled, research found lean mass loss of 17% with resistance training.", population="Adults", sample_size=None)
    checks = text_checks(card, REAL_ABSTRACT)  # the abstract says 17.5%
    assert not checks["numbers_ok"] and "17" in checks["unsupported_numbers"]


def test_describing_who_was_studied_with_diagnosed_is_allowed():
    card = _card(population="Older adults diagnosed with sarcopenia", sample_size=None)
    assert text_checks(card, REAL_ABSTRACT)["wording_ok"]


def test_medicine_names_are_flagged():
    from utils.evidence_checks import mentions_medication

    assert mentions_medication("Tirzepatide and lean mass", "semaglutide, GLP-1 agonists") == ["glp-1", "semaglutide", "tirzepatide"]
    assert mentions_medication("Resistance training and sleep") == []


def test_drug_studies_are_not_collected():
    base = {**ARTICLE, "abstract": "x" * 500, "pub_types": ["Meta-Analysis"], "year": 2024}
    drug_title = {**base, "pubmed_id": "7", "title": "Tirzepatide and lean mass"}
    drug_body = {**base, "pubmed_id": "8", "abstract": "semaglutide " * 3 + "x" * 500}
    fine = {**base, "pubmed_id": "9", "abstract": "A mention of insulin therapy once. " + "x" * 500}
    assert [a["pubmed_id"] for a in evidence_seed.rank_candidates([drug_title, drug_body, fine])] == ["9"]


def test_a_failed_number_check_says_where_the_number_is():
    card = _card(finding="Across the studies pooled, research found that 8 of the trials showed a benefit.", population="Adults", sample_size=None)
    checks = text_checks(card, REAL_ABSTRACT)
    assert not checks["numbers_ok"]
    message = " ".join(checks["problems"])
    assert "8 (in the finding:" in message and "8 of the trials" in message


def test_the_saved_participant_count_is_named_when_it_is_the_problem():
    checks = text_checks(_card(population="Adults", sample_size=8), REAL_ABSTRACT)
    assert "participant count" in " ".join(checks["problems"])
