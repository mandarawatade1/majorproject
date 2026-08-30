"""C5's verifier: one LLM call that names the unsupported sentences.

Three deliberate choices, each answering something C4 taught us.

**One call, not one per sentence.** A per-sentence check is easier to defend
and roughly four times the cost; on the project's hardware that turns a
90-minute evaluation into a three-hour one. The whole answer is numbered and
shown once.

**A one-line contract, exactly as `decide.py` uses.** C4's decide step produced
zero unparseable outputs across twenty questions against the same quantized 7B
model, which is direct evidence that this format discipline holds. Reusing the
shape rather than inventing a second one also means one parser idiom to trust.

**Checking, not planning.** C4 asked the model to decompose a question and name
a missing fact, and it rephrased the question twelve times out of twelve.
Verification asks whether a sentence follows from a passage — entailment rather
than generation — which small models do markedly better. That is the reason to
expect C5 to behave differently from C4, and it is a claim the results will
either support or refute.

The verifier never edits an answer. It reports, and the pipeline decides.
"""

from __future__ import annotations

import re
import time

from rag.generation.base import Generator
from rag.generation.prompts import AssembledContext
from rag.verification.base import VerificationResult, Verdict

MAX_ANSWER_CHARS = 4000
MAX_CONTEXT_CHARS = 6000


VERIFY_SYSTEM = (
    "You check whether each sentence of an answer is supported by the numbered "
    "context passages it was written from.\n\n"
    "A sentence is SUPPORTED if the context states it, or plainly implies it.\n"
    "A sentence is UNSUPPORTED only if it states a fact that the context does "
    "not contain. Judge only what the sentence asserts.\n"
    "Sentences that state no fact — greetings, signposts, advice to contact "
    "someone, or a statement that the context lacks information — are never "
    "unsupported. Do not list them.\n\n"
    "Reply with EXACTLY ONE line, in one of these two forms and nothing else:\n"
    "  SUPPORTED\n"
    "  UNSUPPORTED: <sentence numbers, comma separated>\n\n"
    "Do not explain. Do not quote the sentences. Do not add anything before or "
    "after the line."
)


class ClaimVerifier:
    """Asks the generator's own model whether its answer follows from context."""

    name = "claim_check"

    def __init__(self, generator: Generator) -> None:
        self.generator = generator

    def verify(
        self, question: str, answer: str, context: AssembledContext
    ) -> VerificationResult:
        sentences = split_sentences(answer)
        # Only claim-bearing sentences are shown to the verifier at all. The
        # prompt has always said that a signpost or a statement about what the
        # context lacks can never be "unsupported" — the model ignored that
        # instruction on the first 20-question run and flagged them anyway, so
        # the rule is now enforced in code, where a model cannot disobey it.
        claims = [s for s in sentences if is_claim(s)]

        result = VerificationResult(sentences=len(sentences), original_answer=answer)

        # Nothing to check against, or nothing that asserts anything. Recorded
        # as SKIPPED rather than passed off as SUPPORTED: an unexamined answer
        # is not a verified one, and C5's whole claim is about what was
        # examined. Crucially this is also what makes a refusal impossible for
        # an answer that only says the context lacks information — there is no
        # claim there to be unfounded.
        if context.is_empty or not claims:
            result.verdict = Verdict.SKIPPED
            return result

        system, prompt = build_verify_prompt(question, claims, context)

        started = time.perf_counter()
        generated = self.generator.generate(prompt, system=system)
        result.latency_ms = (time.perf_counter() - started) * 1000

        unsupported, parsed = parse_verdict(generated.answer, len(claims))
        result.raw = (generated.answer or "").strip()

        if not parsed:
            # A verdict nobody can read must not change the answer. C4 set the
            # precedent: an unreadable decision stops the loop and is recorded,
            # never silently treated as a decision.
            result.verdict = Verdict.UNPARSEABLE
            return result

        # `unsupported` indexes the claims shown to the model, not the original
        # sentences, so the support rate is over what was actually judged.
        result.checked = len(claims)
        result.unsupported = unsupported
        result.unsupported_text = [claims[i - 1] for i in unsupported]

        if not unsupported:
            result.verdict = Verdict.SUPPORTED
        elif len(unsupported) < len(claims):
            result.verdict = Verdict.PARTIALLY_SUPPORTED
        else:
            result.verdict = Verdict.UNSUPPORTED
            # Every claim is unsupported — but that alone is not enough to
            # withhold the answer, and the difference matters.
            #
            # Excluding non-claims shrinks the denominator, so an answer that
            # is mostly an honest "the context does not specify X" plus one
            # hedged observation can reduce to a single claim; if that claim is
            # flagged, "all claims unsupported" becomes true and a refusal
            # would replace a largely truthful answer with a blunter one. Two
            # answers in the first C5 run had exactly that shape.
            #
            # So a refusal requires the answer to be *nothing but* unfounded
            # assertion. If it contains any hedge, absence statement or
            # signpost, it is not a fabrication and the annotation is enough.
            result.refused = len(claims) == len(sentences)

        return result


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def build_verify_prompt(
    question: str, sentences: list[str], context: AssembledContext
) -> tuple[str, str]:
    """Return (system, prompt) for one verification pass."""
    numbered = "\n".join(
        f"  {index}. {sentence}" for index, sentence in enumerate(sentences, start=1)
    )[:MAX_ANSWER_CHARS]

    body = (
        f"Context passages:\n{context.text[:MAX_CONTEXT_CHARS]}\n\n"
        f"Question: {question}\n\n"
        f"Answer, one sentence per line:\n{numbered}\n\n"
        f"Which of these {len(sentences)} sentences state a fact the context "
        f"does not support?\n"
        f"Reply with one line: SUPPORTED, or UNSUPPORTED: <numbers>"
    )
    return VERIFY_SYSTEM, body


# ---------------------------------------------------------------------------
# Which sentences assert anything
# ---------------------------------------------------------------------------

# A sentence whose subject is the context itself, asserting that it lacks
# something: "The context provided does not contain information about X."
# This is a statement about the retrieval, not about the world, and it is
# exactly what a well-behaved grounded answer says when it has nothing. The
# first C5 run flagged these as unsupported on 3 of 19 answers and, on q18,
# refused an answer composed entirely of them — replacing a correct, specific
# "I don't have that, here's what I do have" with a generic refusal. That is
# the worst outcome C5 can produce, so the rule is enforced here rather than
# asked for in a prompt.
_ABOUT_CONTEXT = re.compile(
    r"\b(context|excerpts?|passages?|sources?|documents?|"
    r"(provided|given) (text|information)|the text)\b",
    re.IGNORECASE,
)
_ASSERTS_ABSENCE = re.compile(
    r"\b(do(es)?\s+not|don'?t|doesn'?t|did\s+not|lacks?|"
    r"no\s+(information|details?|mention|reference)|"
    r"not\s+(contain|include|specify|mention|provide|available|present))\b",
    re.IGNORECASE,
)

# Advice to look elsewhere. Asserts nothing about the institution, so it can
# be neither supported nor unsupported.
_SIGNPOST = re.compile(
    r"\b(you (might|may|can|should)\s+want|please\s+(contact|refer|visit|check)|"
    r"for (more|further|detailed|complete|additional)\s+\w+|"
    r"(might|may|can|should)\s+(want\s+to\s+)?(contact|refer|visit|check|consult|look)|"
    r"refer\s+to\s+the|contact\s+the|visit\s+the\s+official)\b",
    re.IGNORECASE,
)


def is_claim(sentence: str) -> bool:
    """Does this sentence assert something about the institution?

    Only claim-bearing sentences are worth verifying, and only they belong in
    the support rate — a signpost counted as "supported" inflates the score
    just as surely as one counted "unsupported" deflates it.

    Deliberately narrow. A sentence that describes what the context *does*
    contain ("The text discusses the SAFAR project") stays a claim, because it
    is checkable and could be wrong. Only absence-statements and signposts are
    excluded, which is the smallest exclusion that covers the false positives
    actually observed.
    """
    text = sentence.strip()
    if not text:
        return False
    if _ABOUT_CONTEXT.search(text) and _ASSERTS_ABSENCE.search(text):
        return False
    return not _SIGNPOST.search(text)


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

_ABBREVIATIONS = {
    "dr",
    "mr",
    "mrs",
    "ms",
    "prof",
    "sr",
    "jr",
    "st",
    "no",
    "vs",
    "etc",
    "e.g",
    "i.e",
    "approx",
    "dept",
    "univ",
    "inst",
    "b.e",
    "m.e",
    "b.tech",
    "m.tech",
    "ph.d",
    "phd",
}

_BOUNDARY = re.compile(r"(?<=[.!?])[\"')\]]*\s+")


def split_sentences(text: str) -> list[str]:
    """Split an answer into sentences, numbered for the verifier.

    Naive splitting on ". " breaks this corpus badly: it is full of "Dr.",
    "B.E.", "M.Tech." and "Ph.D.", and a mis-split sentence would be judged as
    a fragment — a fragment is trivially unsupported, so bad splitting inflates
    the hallucination rate rather than erroring. Citation markers like [S2] are
    left in place, because the verifier is told which passage the sentence
    claims to come from.
    """
    text = (text or "").strip()
    if not text:
        return []

    pieces = _BOUNDARY.split(text)
    sentences: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if sentences and _ends_with_abbreviation(sentences[-1]):
            sentences[-1] = f"{sentences[-1]} {piece}"
        else:
            sentences.append(piece)

    return [s for s in sentences if _has_letters(s)]


def _ends_with_abbreviation(sentence: str) -> bool:
    """Is this apparent sentence end actually an abbreviation or an initial?

    Single letters count, because this corpus is largely faculty pages:
    "Sowmya P.", "Suhas J. Lawand", "K. Charumathi", "Y. I. Jinesh Melvin".
    Splitting those produces a subjectless fragment, and a fragment is
    trivially unsupported — so a splitting error would raise the measured
    hallucination rate without anything erroring.

    The trade-off is accepted knowingly and in one direction. A sentence that
    genuinely ends in a single letter ("...accredited by NAAC with grade A.")
    is merged with the one after it, which gives the verifier one longer
    sentence to judge — a mild loss. The opposite error manufactures a false
    hallucination. Merging is the safer mistake, so the rule prefers it.
    """
    match = re.search(r"([A-Za-z.]+)\.$", sentence.strip())
    if not match:
        return False
    token = match.group(1).lower().strip(".")
    return len(token) == 1 or token in _ABBREVIATIONS


def _has_letters(sentence: str) -> bool:
    """Drop fragments that are only punctuation or a bare citation marker."""
    return bool(re.search(r"[A-Za-z]", re.sub(r"\[S\d+\]", "", sentence)))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_SUPPORTED = re.compile(r"^\W*(all\s+)?supported\b", re.IGNORECASE)
_UNSUPPORTED = re.compile(r"^\W*unsupported\s*[:\-]?\s*(.*)$", re.IGNORECASE)
_NONE = re.compile(r"^\W*(none|no|nil|n/?a)\b", re.IGNORECASE)


def parse_verdict(text: str, sentence_count: int) -> tuple[list[int], bool]:
    """Read the one-line verdict. Returns (unsupported numbers, parsed).

    Out-of-range numbers are dropped rather than failing the parse: a model
    that says "4" about a three-sentence answer has miscounted, not refused to
    answer, and the sentences it did identify are still usable. An
    `UNSUPPORTED:` whose numbers are *all* out of range yields an empty list
    with `parsed=True` — read as "nothing this verifier could point at", which
    is the conservative reading, since the alternative is refusing an answer on
    the strength of a number that indexes nothing.
    """
    raw = (text or "").strip()
    if not raw:
        return [], False

    for line in _candidate_lines(raw):
        if _SUPPORTED.match(line):
            return [], True

        match = _UNSUPPORTED.match(line)
        if match:
            tail = match.group(1).strip()
            if not tail or _NONE.match(tail):
                return [], True
            numbers = sorted(
                {
                    n
                    for n in (int(x) for x in re.findall(r"\d+", tail))
                    if 1 <= n <= sentence_count
                }
            )
            return numbers, True

        if _NONE.match(line):
            return [], True

    return [], False


def _candidate_lines(raw: str) -> list[str]:
    lines: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip().strip("*_` ").strip()
        cleaned = re.sub(
            r"^(answer|verdict|decision|result)\s*[:\-]\s*", "", cleaned, flags=re.I
        )
        if cleaned:
            lines.append(cleaned)
    return lines


__all__ = [
    "VERIFY_SYSTEM",
    "ClaimVerifier",
    "build_verify_prompt",
    "is_claim",
    "parse_verdict",
    "split_sentences",
]
