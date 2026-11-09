"""Extract location phrases from common fire-monitoring search requests."""
import re
import unicodedata


def location_query(text: str) -> str:
    text = ' '.join(unicodedata.normalize('NFKC', text).strip().split())
    # Only strip anchored request wording, preserving names such as Fire Island.
    text = re.sub(r'^(?:please\s+)?(?:show(?:\s+me)?|find|search(?:\s+for)?|explore|tell\s+me\s+about)\s+', '', text, flags=re.I)
    text = re.sub(r'^(?:(?:the|recent|current|historical|active|latest)\s+)*(?:wildfires?|fires?|hotspots?|fire\s+(?:activity|history|risk|detections?|trends?))\s+(?:in|near|around|at|for)\s+', '', text, flags=re.I)
    text = re.sub(r'^(?:in|near|around)\s+', '', text, flags=re.I)
    text = re.sub(r'\s+(?:today|yesterday|this\s+(?:week|month|year)|last\s+(?:week|month|year)|over\s+the\s+(?:last|past)\s+\d+\s+days?)\s*[?.!]*$', '', text, flags=re.I)
    return text.strip(' ?!.')
