"""Lossless bounded source projection; no model, persistence or publication owner."""
from dataclasses import dataclass
from hashlib import sha256


def source_reference(identity, role, text, start=0, end=None):
    end = len(text) if end is None else end
    reference = dict(sourceId=identity, role=role, sourceFingerprint=sha256(text.encode()).hexdigest(),
                     start=start, end=end, sourceLength=len(text))
    validate_reference(reference, text[start:end])
    return reference


def validate_reference(reference, excerpt):
    if not isinstance(reference, dict) or set(reference) != {
        "sourceId", "role", "sourceFingerprint", "start", "end", "sourceLength"
    }:
        raise ValueError("Invalid factual source reference.")
    if not isinstance(reference["sourceId"], str) or not reference["sourceId"].strip():
        raise ValueError("Original source identity required.")
    if reference["role"] not in {"user", "assistant", "tool", "document"}:
        raise ValueError("Original source role required.")
    digest = reference["sourceFingerprint"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Original source fingerprint required.")
    start, end, length = (reference[k] for k in ("start", "end", "sourceLength"))
    if any(type(v) is not int for v in (start, end, length)) or not 0 <= start <= end <= length:
        raise ValueError("Invalid source span offsets.")
    if not isinstance(excerpt, str) or len(excerpt) != end-start or len(excerpt) > 16384:
        raise ValueError("Evidence excerpt does not match its bounded source span.")
    if start == 0 and end == length and sha256(excerpt.encode()).hexdigest() != digest:
        raise ValueError("Whole-source excerpt fingerprint changed.")


@dataclass(frozen=True)
class SourceSpan:
    index: int
    source_id: str
    role: str
    source_fingerprint: str
    start: int
    end: int
    source_length: int
    text: str

    @property
    def reference(self):
        return dict(sourceId=self.source_id, role=self.role, sourceFingerprint=self.source_fingerprint,
                    start=self.start, end=self.end, sourceLength=self.source_length)

    @property
    def formatted(self):
        return (f"[entryIndex={self.index}] [{self.source_id}] "
                f"[sourceSpan={self.start}:{self.end}] {self.role}: {self.text}")


def partition_sources(entries, *, span_characters=12000, window_characters=60000):
    """Every character appears once, with global citations and original offsets.

    Character budgets are conservative input bounds, not model token/latency claims.
    This does not make a legacy reviewer/windowed job automatically complete.
    """
    if type(span_characters) is not int or not 1 <= span_characters <= 16384:
        raise ValueError("Invalid evidence span budget.")
    if type(window_characters) is not int or not 1 <= window_characters <= 100000:
        raise ValueError("Invalid review window budget.")
    windows, current, size, index, seen = [], [], 0, 0, set()
    for identity, role, text in entries:
        if identity in seen:
            raise ValueError("Duplicate source identity.")
        seen.add(identity)
        fingerprint = sha256(text.encode()).hexdigest()
        for start in range(0, max(1, len(text)), span_characters):
            end = min(len(text), start+span_characters)
            span = SourceSpan(index, identity, role, fingerprint, start, end, len(text), text[start:end])
            validate_reference(span.reference, span.text)
            cost = len(span.formatted)+1
            if cost > window_characters:
                raise ValueError("A formatted source span exceeds its window budget.")
            if current and size+cost > window_characters:
                windows.append(tuple(current))
                current, size = [], 0
            current.append(span)
            size += cost
            index += 1
    if current:
        windows.append(tuple(current))
    return tuple(windows)


def validate_coverage(entries, windows):
    """Verify coverage against original text, not a self-reported count."""
    spans = iter(span for window in windows for span in window)
    index, seen = 0, set()
    for identity, role, text in entries:
        if identity in seen:
            raise ValueError("Duplicate original source identity.")
        seen.add(identity)
        position = 0
        while True:
            span = next(spans, None)
            if span is None or span.index != index or span.source_id != identity or span.role != role:
                raise ValueError("Missing or reordered factual source span.")
            validate_reference(span.reference, span.text)
            if (span.start != position or span.source_length != len(text)
                or span.source_fingerprint != sha256(text.encode()).hexdigest()
                or span.text != text[span.start:span.end]
                or (span.end == span.start and text)):
                raise ValueError("Changed, overlapping or fabricated factual source span.")
            position, index = span.end, index+1
            if position == len(text):
                break
    if next(spans, None) is not None:
        raise ValueError("Unexpected factual source span.")
