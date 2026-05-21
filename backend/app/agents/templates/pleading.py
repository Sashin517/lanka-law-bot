"""Civil litigation pleading template skeleton.

Covers common Sri Lankan civil pleadings: plaint, answer, petition,
and application structures under the Civil Procedure Code.
"""

PLEADING_TEMPLATE = """\
## PLEADING STRUCTURE

Draft a civil litigation pleading with the following sections.  Fill each
section using the retrieved legal context and the user's request.
Cite the statutory authority (e.g. Civil Procedure Code provisions)
using [LAW-*] anchors.

### 1. CAPTION
- Court name and jurisdiction
- Case number (if available)
- Names and designations of Plaintiff(s) and Defendant(s)

### 2. TITLE OF THE PLEADING
- e.g. "PLAINT", "ANSWER", "PETITION", "APPLICATION"

### 3. PARTIES
- Full names, addresses, and capacities of all parties
- National Identity Card numbers (if applicable)

### 4. JURISDICTION
- Basis for the court's jurisdiction
- Relevant statutory provisions (cite with [LAW-*])

### 5. MATERIAL FACTS
- Numbered paragraphs setting out each material fact
- Chronological order
- Each paragraph should contain one key factual assertion

### 6. CAUSE OF ACTION
- Legal basis for the claim
- Relevant statutes and provisions (cite with [LAW-*])
- Elements of the cause of action

### 7. RELIEF / PRAYER
- Specific relief sought (damages, injunctions, declarations)
- Numbered list of each prayer
- Costs of action

### 8. VERIFICATION
- Statement of truth / verification
- Date and place

### 9. SCHEDULE (if applicable)
- Inventory of documents, property descriptions, etc.

### 10. SIGNATURE
- Signature of party / attorney-at-law
- Attorney-at-law name and enrollment number
"""
