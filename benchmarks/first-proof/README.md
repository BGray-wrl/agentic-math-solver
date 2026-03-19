

## Replacements & Substitutions for AI-Processing

1) The one change you must handle (JSON/API)

Every \ must be escaped as \\ inside JSON strings.
Example: \mathbb{R} must be sent as \\mathbb{R} (unless your client library does this for you).

If you don’t do this, the payload can become invalid JSON or arrive mangled.

---

Custom macros (replace with standard text/math):

\aO → \mathcal{O} or plain O
(Your preamble defines it as a fancy/script O. Models don’t “know” your macro definitions.)

\bR → \mathbb{R} or “the real numbers”

\vecop(…) → \operatorname{vec}(…) or “vec(…)” / “vectorize(…)”

Pure formatting/layout (safe to delete):

\smallskip → delete

\setlength\itemsep{...} → delete

\nonumber → delete

{\it ...} → replace with plain text (or Markdown italics *...*)

## Odered List of Likely Source per Question
1) Martin Hairer
2) Paul D. Nelson
3) Lauren Williams
4) Nikhil Srivastava
5) Andrew J. Blumberg
6) Daniel Spielman
7) Shmuel Weinberger
8) Mohammed Abouzaid
9) Joe Kileel
10) Tamara G. Kolda
