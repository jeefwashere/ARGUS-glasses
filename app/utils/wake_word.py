import re

WAKE_PHRASE = "Hi Spider"
WAKE_PHRASE_PATTERN = re.compile(
    r"^\s*hi[\s,.:;!?]+spider\b[\s,.:;!?]*",
    re.IGNORECASE,
)


def extract_wake_question(transcript: str) -> tuple[bool, str]:
    spoken_text = transcript.strip()
    match = WAKE_PHRASE_PATTERN.match(spoken_text)
    if match is None:
        return False, ""
    return True, spoken_text[match.end() :].strip()
