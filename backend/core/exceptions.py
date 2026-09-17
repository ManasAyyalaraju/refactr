class TailoringGenerationError(Exception):
    """Raised when the LLM tailoring call fails or returns an unusable result.

    Callers must not fall back to silently returning the untailored resume -
    this exists so that failure is a visible, catchable signal instead.
    """
    pass


class UnreadablePdfError(Exception):
    """Raised when a PDF has no extractable text (e.g. a scanned/flattened
    image PDF) - parsing it would otherwise silently produce a blank resume
    instead of a visible, catchable failure.
    """
    pass
