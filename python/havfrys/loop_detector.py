"""detect_loop() primitive — hash-sequence oscillation detection for LLM self-diagnostic."""

import hashlib
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class LoopResult:
    status: str = "success"
    oscillation: bool = False
    pattern: Optional[str] = None
    confidence: float = 0.0
    hash_sequence: list = None
    operation_id: str = ""


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode()).hexdigest()[:16]


def detect_loop(text: str) -> LoopResult:
    op_id = f"dl_{uuid.uuid4().hex[:8]}"

    if not text:
        return LoopResult(
            status="success", oscillation=False,
            hash_sequence=[], operation_id=op_id,
        )

    chunks = text.split("\n")
    chunk_size = max(1, len(chunks) // 20)
    hashes = []

    for i in range(0, len(chunks), chunk_size):
        block = "\n".join(chunks[i : i + chunk_size])
        hashes.append(_hash_text(block))

    oscillation = False
    pattern = None
    confidence = 0.0

    if len(hashes) >= 4:
        last4 = hashes[-4:]
        if last4[0] == last4[2] and last4[1] == last4[3] and last4[0] != last4[1]:
            oscillation = True
            pattern = "A-B-A-B"
            confidence = round(min(0.5 + 0.1 * len(hashes), 0.95), 2)

    if not oscillation and len(hashes) >= 6:
        last6 = hashes[-6:]
        if last6[0] == last6[3] and last6[1] == last6[4] and last6[2] == last6[5]:
            oscillation = True
            pattern = "A-B-C-A-B-C"
            confidence = 0.7

    if not oscillation and len(hashes) >= 2:
        if len(set(hashes[-3:])) <= 1 and len(hashes) >= 3:
            oscillation = True
            pattern = "identical_output"
            confidence = 0.6

    return LoopResult(
        status="success",
        oscillation=oscillation,
        pattern=pattern,
        confidence=confidence,
        hash_sequence=hashes,
        operation_id=op_id,
    )
