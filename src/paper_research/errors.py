"""Error codes for paper_research. Every failure carries a stable code and a message."""


class PaperError(Exception):
    CODES = {
        "PATH_NOT_ALLOWED": "file is outside the caller's allowed roots",
        "REMOTE_NOT_ALLOWED": "URLs are not fetched; give a local file",
        "FILE_NOT_FOUND": "file does not exist",
        "FILE_TOO_LARGE": "file exceeds the size limit",
        "UNSUPPORTED_FORMAT": "no parser for this file type",
        "MACRO_DOCUMENT_REFUSED": "macro-enabled documents are not opened",
        "ENCRYPTED": "document is encrypted",
        "PARSE_FAILED": "file is malformed or cannot be parsed",
        "NO_TEXT_LAYER": "no extractable text (e.g. scanned PDF); OCR is not performed",
        "SCHEMA_INVALID": "structure does not match the versioned schema",
        "PROVENANCE_INVALID": "an evidence quote is not found at its cited location",
        "VERSION_UNSUPPORTED": "schema version not supported",
        "TEMPLATE_UNSUPPORTED_OPERATOR": "the deterministic template does not cover this operator (trusted IR executor)",
    }

    def __init__(self, code: str, message: str = ""):
        if code not in self.CODES:
            raise ValueError(f"unknown error code {code}")
        super().__init__(f"{code}: {message or self.CODES[code]}")
        self.code = code
        self.message = message or self.CODES[code]
