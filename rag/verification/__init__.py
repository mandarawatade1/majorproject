"""C5: post-answer verification.

The last configuration in the ablation. C4 changed how candidates were
gathered; C5 changes nothing about how the answer is produced and instead
checks it afterwards, so the single variable is the check itself.
"""

from rag.verification.base import VerificationResult, Verdict, Verifier
from rag.verification.claim_check import (
    VERIFY_SYSTEM,
    ClaimVerifier,
    build_verify_prompt,
    is_claim,
    parse_verdict,
    split_sentences,
)

__all__ = [
    "VERIFY_SYSTEM",
    "ClaimVerifier",
    "VerificationResult",
    "Verdict",
    "Verifier",
    "build_verify_prompt",
    "is_claim",
    "parse_verdict",
    "split_sentences",
]
