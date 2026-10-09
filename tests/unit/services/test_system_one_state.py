import pytest
from pydantic import TypeAdapter

from schemas.system_one_schemas import Question
from services.system_one_state import (
    build_state, parse_budget_error, question_overhead_chars, reduce_state, shrink_factor, truncate_at_word,
)

Q = TypeAdapter(Question).validate_python
QUESTIONS = [Q({"key": "u", "type": "noul", "instructions": "Is this urgent?"})]


def test_build_state_adds_file_texts_with_names():
    s = build_state("hello", [{"filename": "a.pdf", "content": "PDF TEXT", "type": "pdf"}])
    assert s.startswith("hello") and "a.pdf" in s and "PDF TEXT" in s


def test_build_state_without_text_uses_only_files():
    s = build_state("", [{"filename": "a.txt", "content": "body", "type": "text"}])
    assert s.startswith("--- a.txt ---") and s.endswith("body")


def test_build_state_skips_files_without_extractable_text():
    assert build_state("", [{"filename": "scan.pdf", "content": "  \n", "type": "pdf"}]) == ""
    assert build_state("   ", []) == ""


def test_build_state_rejects_images():
    with pytest.raises(ValueError, match="text"):
        build_state("x", [{"filename": "i.png", "content": "b64", "type": "image"}])


def test_parse_budget_error_and_shrink():
    msg = "Longest prompt has 40159 tokens; limit is 8192. Nothing was truncated."
    assert parse_budget_error(msg) == (40159, 8192)
    assert parse_budget_error("other") is None
    assert 0 < shrink_factor(40159, 8192) < 0.2
    assert shrink_factor(0, 8192) == 0.5          # nonsense input never divides by zero


def test_truncate_at_word_boundary():
    assert truncate_at_word("alpha beta gamma", 12) == "alpha beta"
    assert truncate_at_word("short", 100) == "short"
    assert truncate_at_word("x" * 50, 10) == "x" * 10        # no whitespace: hard cut


@pytest.mark.asyncio
async def test_fits_is_untouched():
    r = await reduce_state("tiny", QUESTIONS, 6000, None)
    assert (r.mode, r.text, r.original_chars) == ("none", "tiny", 4)


@pytest.mark.asyncio
async def test_too_long_without_llm_truncates():
    r = await reduce_state("word " * 5000, QUESTIONS, 1000, None)
    assert r.mode == "truncated" and r.original_chars == 25000
    assert 0 < len(r.text) <= 1000 - question_overhead_chars(QUESTIONS)


@pytest.mark.asyncio
async def test_too_long_with_llm_summarizes():
    seen = {}

    async def summarize(text, questions, budget):
        seen["budget"], seen["questions"] = budget, questions
        return "short summary"

    r = await reduce_state("word " * 5000, QUESTIONS, 1000, summarize)
    assert (r.mode, r.text) == ("summarized", "short summary")
    assert seen["questions"] == QUESTIONS and seen["budget"] == 1000 - question_overhead_chars(QUESTIONS)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "   ", "x" * 5000])
async def test_bad_summary_falls_back_to_truncation(bad):
    async def summarize(text, questions, budget):
        return bad

    r = await reduce_state("word " * 5000, QUESTIONS, 1000, summarize)
    assert r.mode == "truncated" and (r.text == "" or 0 < len(r.text) <= 1000) and r.text != ""


@pytest.mark.asyncio
async def test_failing_summary_falls_back_to_truncation():
    async def summarize(text, questions, budget):
        raise RuntimeError("llm down")

    r = await reduce_state("word " * 5000, QUESTIONS, 1000, summarize)
    assert r.mode == "truncated" and r.text


@pytest.mark.asyncio
async def test_summary_is_not_called_when_the_text_fits():
    async def summarize(text, questions, budget):
        raise AssertionError("must not be called")

    r = await reduce_state("fits", QUESTIONS, 6000, summarize)
    assert r.mode == "none"


@pytest.mark.asyncio
async def test_question_overhead_is_discounted():
    long_q = [Q({"key": "u", "type": "noul", "instructions": "x" * 900})]
    r = await reduce_state("a " * 400, long_q, 1000, None)     # 800 chars fit raw, but only ~200 are available
    assert r.mode == "truncated" and len(r.text) <= 200


def test_overhead_counts_the_longest_question_including_options():
    short = Q({"key": "a", "type": "noul", "instructions": "short"})
    big = Q({"key": "b", "type": "choice", "instructions": "pick",
             "criteria": [{"key": "k" * 100, "description": "d" * 100}, {"key": "z"}]})
    assert question_overhead_chars([short, big]) >= 204
    assert question_overhead_chars([short]) < question_overhead_chars([short, big])
