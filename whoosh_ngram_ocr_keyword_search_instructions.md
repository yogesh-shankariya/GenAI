# Build Whoosh N-Gram OCR Keyword Search Fallback

## Goal

Build a keyword search pipeline for OCR text where normal exact/regex search can fail because OCR text is noisy.

Example problem:

```text
OCR text : brElectrnically signed
Keyword  : electronically signed
```

Normal regex fails because `electronically` is misspelled as `electrnically` and has an extra prefix `br`.

The solution should use Whoosh n-gram search as a fallback to find candidate pages/chunks, then validate those candidates using a custom threshold and RapidFuzz.

---

## Important Requirement

Use Whoosh native n-gram support.

Whoosh supports native n-gram field types:

```python
whoosh.fields.NGRAM
whoosh.fields.NGRAMWORDS
```

For this use case, prefer:

```python
NGRAMWORDS
```

Reason: `NGRAMWORDS` first extracts words and then creates n-grams inside each word. This is better for OCR keyword search than creating n-grams across spaces and punctuation.

---

## What to Build

Build a reusable OCR keyword search module with this flow:

```text
1. Load OCR text page-wise or chunk-wise
2. Load keywords from JSON
3. Create Whoosh index with normal field + n-gram field
4. First try exact/regex search
5. If not found, try normal Whoosh search
6. If still not found, try Whoosh n-gram fallback search
7. Validate n-gram candidates using n-gram coverage + RapidFuzz
8. Return matched page/chunk, matched window, score, and match type
```

---

## Why N-Gram Is Needed

For this OCR text:

```text
brElectrnically signed
```

And keyword:

```text
electronically signed
```

Use 4-gram.

Keyword n-grams:

```text
electronically → elec, lect, ectr, ctro, tron, roni, onic, nica, ical, call, ally
signed         → sign, igne, gned
```

Total keyword n-grams:

```text
14
```

OCR n-grams:

```text
brElectrnically → brel, rele, elec, lect, ectr, ctrn, trni, rnic, nica, ical, call, ally
signed          → sign, igne, gned
```

Matching n-grams:

```text
elec, lect, ectr, nica, ical, call, ally, sign, igne, gned
```

Matched:

```text
10 out of 14 = 71.43%
```

So even though regex fails, n-gram can still identify this as a likely match.

---

## Recommended Index Design

Create one Whoosh document per OCR page or OCR chunk.

Recommended fields:

```text
doc_id          ID / stored
page_no         NUMERIC / stored
chunk_id        ID / stored
content_normal  TEXT
content_ngram   NGRAMWORDS
content_stored  STORED
metadata        STORED optional
```

Store the same OCR text in both searchable fields:

```text
content_normal = original OCR text
content_ngram  = original OCR text
content_stored = original OCR text
```

Use `content_stored` to return the matched window to the user.

---

## N-Gram Configuration

Use fixed 4-grams for the first version.

```text
minsize = 4
maxsize = 4
```

Reason:

```text
3-gram = more tolerant but more false positives
4-gram = good balance for OCR keyword search
5-gram = stricter but may miss noisy OCR
```

Do not use 1-gram or 2-gram because it will create too many weak matches.

---

## Search Flow

### Step 1: Normalize Text

Create a common normalization function for both OCR text and keywords.

Minimum normalization:

```text
- lowercase
- normalize unicode if needed
- collapse multiple spaces into one space
- strip leading/trailing spaces
```

Do not aggressively remove characters in the first version. Avoid special rules like removing `br`, because that can create wrong behavior.

---

### Step 2: Exact / Regex Search First

Before Whoosh n-gram fallback, try simple direct matching.

Use this logic:

```text
If normalized keyword exists inside normalized OCR text:
    accept as exact_substring match
```

Also support whitespace-flexible regex:

```text
electronically signed
```

should match:

```text
electronically    signed
electronically\nsigned
electronically signed
```

Match type:

```text
exact_or_regex
```

Confidence:

```text
1.0
```

---

### Step 3: Normal Whoosh Search

Search the keyword in `content_normal`.

This catches normal clean text cases.

Example:

```text
Electronically signed by customer
```

Match type:

```text
whoosh_normal
```

---

### Step 4: N-Gram Fallback Search

If exact/regex and normal Whoosh search fail, search in `content_ngram`.

Important:

Use OR-style query grouping for the n-gram fallback. Do not require all n-grams to match, because OCR may be damaged.

Reason:

For this keyword:

```text
electronically signed
```

OCR may miss some n-grams:

```text
brElectrnically signed
```

If all n-grams are required, this candidate may be missed.

N-gram search should return top candidate chunks/pages only.

Recommended initial setting:

```text
top_k = 20
```

---

## Validation Logic for N-Gram Candidate

Do not directly accept Whoosh n-gram results.

Whoosh n-gram should only shortlist candidate pages/chunks.

For each candidate, calculate:

```text
1. ngram_coverage
2. rapidfuzz_score
3. best matched text window
```

---

## N-Gram Coverage Formula

Generate keyword n-grams and candidate-window n-grams using the same n-gram size.

Use this formula:

```text
ngram_coverage = matched_keyword_ngrams / total_keyword_ngrams
```

Example:

```text
matched_keyword_ngrams = 10
total_keyword_ngrams   = 14
coverage               = 10 / 14 = 0.7143
```

Important:

Calculate coverage against the keyword n-grams, not against the full OCR chunk n-grams.

---

## Best Matched Window

Do not calculate RapidFuzz on the full OCR page if the page is very large.

Instead, extract candidate windows from the chunk.

Recommended first version:

```text
1. Normalize candidate chunk
2. Create sliding character windows
3. Window length = keyword length + 40 characters
4. Window step = 10 to 20 characters
5. Calculate RapidFuzz score between keyword and each window
6. Keep the highest scoring window
```

Example:

```text
OCR chunk:
This document was brElectrnically signed by the customer.

Keyword:
electronically signed

Best window:
brElectrnically signed
```

Return this as:

```text
matched_window
```

---

## Recommended Thresholds

Use these initial thresholds:

```text
ngram_coverage_threshold = 0.65
rapidfuzz_threshold      = 80
```

Accept n-gram match only when both are true:

```text
ngram_coverage >= 0.65
rapidfuzz_score >= 80
```

Optional review bucket:

```text
0.55 <= ngram_coverage < 0.65
or
75 <= rapidfuzz_score < 80
```

Return these as low-confidence candidates, but do not mark them as final match unless business wants review mode.

---

## Result Object

Return results in a structured format.

Recommended output fields:

```json
{
  "keyword_id": "string",
  "keyword": "electronically signed",
  "doc_id": "string",
  "page_no": 1,
  "chunk_id": "string",
  "match_type": "ngram_fallback",
  "matched": true,
  "confidence_score": 0.86,
  "ngram_coverage": 0.7143,
  "rapidfuzz_score": 86,
  "matched_window": "brElectrnically signed",
  "reason": "Matched using Whoosh n-gram fallback and validated with RapidFuzz"
}
```

Allowed match types:

```text
exact_or_regex
whoosh_normal
ngram_fallback
no_match
```

---

## Handling Short Keywords

Do not apply n-gram fallback blindly for very short keywords.

Recommended rule:

```text
If keyword length after removing spaces is less than 6 characters:
    skip n-gram fallback
    use exact/regex only
```

Reason:

Short keywords create too many false positives with n-gram search.

---

## Chunking Recommendation

If OCR page text is small, index page-wise.

If OCR page text is long, create chunks.

Recommended chunking:

```text
chunk_size = 1000 to 1500 characters
overlap    = 100 to 150 characters
```

Keep page number on every chunk.

Reason:

This allows the system to return the correct page and a focused matched window.

---

## Testing Requirements

Add unit tests for these examples.

### Test 1: Exact substring with prefix

```text
OCR     : brElectronically signed
Keyword : electronically signed
Expected: match
Type    : exact_or_regex
```

### Test 2: OCR spelling issue

```text
OCR     : brElectrnically signed
Keyword : electronically signed
Expected: match
Type    : ngram_fallback
```

### Test 3: Joined words

```text
OCR     : brElectronicallysigned
Keyword : electronically signed
Expected: match or candidate depending RapidFuzz score
Type    : ngram_fallback
```

### Test 4: No match

```text
OCR     : payment completed successfully
Keyword : electronically signed
Expected: no_match
```

### Test 5: Large page text

```text
OCR     : long OCR text containing brElectrnically signed in the middle
Keyword : electronically signed
Expected: match with matched_window around brElectrnically signed
```

---

## Acceptance Criteria

Implementation is complete when:

```text
1. Whoosh index is created with content_normal and content_ngram fields
2. content_ngram uses Whoosh native NGRAMWORDS
3. Exact/regex search runs before n-gram search
4. N-gram fallback uses OR-style matching to allow partial noisy OCR matches
5. N-gram results are validated using custom ngram_coverage
6. RapidFuzz validates the best matched text window
7. Output includes page_no, chunk_id, match_type, matched_window, ngram_coverage, and rapidfuzz_score
8. Unit tests pass for the examples above
9. No custom logic is added to remove `br` manually
```

---

## Do Not Build

Do not build custom `br` removal logic.

Avoid logic like:

```text
if token starts with br:
    remove br
```

Reason:

This is fragile and can break valid words.

The solution should be generic:

```text
Use n-gram fallback to handle OCR prefixes, suffixes, joined words, and small spelling errors.
```

---

## Final Recommended Pipeline

```text
OCR page/chunk text
        ↓
Normalize text
        ↓
Exact / regex search
        ↓ if no match
Whoosh normal search
        ↓ if no match
Whoosh NGRAMWORDS fallback search
        ↓
Calculate ngram_coverage
        ↓
Find best matched window
        ↓
RapidFuzz validation
        ↓
Return final match result
```
