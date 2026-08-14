"""Legal notice / letter of demand template skeleton.

Covers common Sri Lankan notice types: letter of demand, notice to quit,
notice of termination, and statutory notices under various acts.
"""

NOTICE_TEMPLATE = """\
## LEGAL NOTICE STRUCTURE

Draft a legal notice / letter of demand with the following sections.
Fill each section using the retrieved legal context and the user's request.
Name each statutory authority and section in the notice text, then append its
[LAW-*] anchor as a source annotation. Never use an anchor in place of the
human-readable authority.

### 1. HEADER
- "LEGAL NOTICE" / "LETTER OF DEMAND" / "NOTICE TO QUIT" (as appropriate)
- Date of the notice
- Reference number (if applicable)

### 2. ADDRESSEE
- Full name and address of the recipient

### 3. SENDER IDENTIFICATION
- Full name and address of the sender
- Capacity (e.g. "through Attorney-at-Law")

### 4. SUBJECT LINE
- Brief description of the subject matter

### 5. BODY — FACTUAL BACKGROUND
- Chronological summary of relevant facts
- Reference to any prior communications or agreements

### 6. BODY — LEGAL BASIS
- Applicable legal provisions and rights (name the instrument and section,
  then append the matching [LAW-*] source annotation)
- Breach or obligation giving rise to the notice

### 7. DEMAND / NOTICE
- Specific demand or notice being given
- Time limit for compliance (e.g. "within 14 days")
- Consequences of non-compliance

### 8. CLOSING
- Statement of intent to pursue legal action if necessary
- Request for acknowledgement

### 9. SIGNATURE
- Signature block
- Attorney-at-law name and enrollment number (if applicable)
"""
