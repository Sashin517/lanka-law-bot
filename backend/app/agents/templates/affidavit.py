"""Affidavit template skeleton.

Covers standard Sri Lankan affidavit format used in court proceedings,
applications, and statutory declarations.
"""

AFFIDAVIT_TEMPLATE = """\
## AFFIDAVIT STRUCTURE

Draft an affidavit with the following sections.  Fill each section
using the retrieved legal context and the user's request.
Cite any relevant statutory authority using [LAW-*] anchors.

### 1. TITLE
- Court name (if filed in court proceedings)
- Case number (if applicable)
- "AFFIDAVIT OF [DEPONENT NAME]"

### 2. DEPONENT IDENTIFICATION
- Full name, address, National Identity Card number
- Occupation and capacity

### 3. OATH / AFFIRMATION
- "I, [Name], being duly sworn/affirmed, do hereby state as follows:"

### 4. BODY — NUMBERED PARAGRAPHS
- Each paragraph states one specific fact within the deponent's
  personal knowledge
- Distinguish between facts known personally and facts based on
  information and belief (state the source)
- Reference any exhibits ("marked as 'X1' and annexed hereto")

### 5. EXHIBITS (if applicable)
- List of documents annexed
- Each exhibit marked with a unique identifier

### 6. VERIFICATION
- "I state that the facts set out above are true and correct
  to the best of my knowledge and belief."

### 7. ATTESTATION
- Signature of deponent
- Date and place of signing
- Before whom sworn (Justice of the Peace / Commissioner for Oaths)
- Seal and signature of attesting officer
"""
