"""
Lyrics -> captions and image prompts.

Captions: the line Whisper heard, cleaned of its typical music hallucinations.
Images:   a high-contrast graphic noir woodcut that illustrates the *literal*
          words being sung. No language model, no keyword soup: the sung line
          itself is the subject.
"""
import re

# The look of every image. Bold black and white suits the boombox's tiny B/W CRT.
DEFAULT_STYLE = (
    "high contrast graphic noir woodcut print, bold black ink on white paper, "
    "linocut carving marks, dramatic chiaroscuro, film noir, stark, no text"
)

# Whisper sometimes "hears" these in music or silence. Throw them away.
HALLUCINATIONS = [
    "thanks for watching", "thank you for watching", "subscribe",
    "like and subscribe", "untertitel", "amara.org", "copyright",
    "music", "musik", "applause", "[music]", "(music)", "♪",
    "you", "thank you", "bye", "the end",
]

FILLER = re.compile(r"\b(oh+|ooh+|ah+|uh+|um+|yeah+|na( na)+|la( la)+|whoa+|hey+)\b[,!.]?\s*", re.I)


def clean_lyrics(text):
    """Remove Whisper's typical music hallucinations and tidy up the text."""
    if not text:
        return ""
    t = re.sub(r"[\[\(].*?[\]\)]", " ", text)      # [Music], (applause)
    t = re.sub(r"[♪♫*]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    low = t.lower().strip(" .,!?-")
    if not low:
        return ""
    for h in HALLUCINATIONS:
        if low == h or (h in low and len(low) < len(h) + 12):
            return ""
    # The same few words repeated over and over is another Whisper failure mode
    words = low.split()
    if len(words) >= 6 and len(set(words)) <= 2:
        return ""
    return t


class PromptBuilder:
    def __init__(self, style=DEFAULT_STYLE):
        self.style = style

    def build(self, line):
        """Image prompt for one sung line: the literal words, in woodcut noir."""
        subject = FILLER.sub("", clean_lyrics(line)).strip(" ,.!?") or "an empty street at night"
        if len(subject) > 160:                   # the text encoder only reads ~75 tokens
            subject = subject[:160].rsplit(" ", 1)[0]
        return f"illustration of the words: \"{subject}\". {self.style}"
