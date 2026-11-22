# Native-table review and HTML extraction, November 21, 2026

Control: EvidenceMill 5d1676072822365f3eda6fca46a3775a726bcd16, PyMuPDF 1.26.6, Tesseract 5.5.0, Python 3.12. Earlier pilot and comparative commands are preserved in [CSS_DATABASE #851](https://github.com/jwtablemaker-hue/CSS_DATABASE/pull/851).

## Native table

[ED2301 capture](https://minimotors.oss-eu-central-1.aliyuncs.com/upload/2023thunder3%28PRODUCT%20MANUAL.pdf), 12 sheets, SHA-256 7a7218c5b71f185af12e41b1fd1e1df50d5444c71cefc2549e24545c4b00e02a. Sheet 5 has a missing rule under the value column, but distinct labels in its adjacent column. Control, PyMuPDF4LLM 0.0.27 and pdfplumber 0.11.9 all associated the wheelbase value with the preceding rider-height row. The optional review command recovered one correct association, Wheelbase → Approx.970mm, with source hash and word coordinates. Zero false suggestions on this sheet. Baseline full document: 5.603 seconds, 263,676 KiB maximum RSS. Alternatives full document: 2.698 seconds/104,504 KiB and 2.642 seconds/107,952 KiB respectively. Optional sheet review: 0.251 seconds/45,212 KiB in CSS pilot. These are distinct scopes, not a speedup ratio. None adds a runtime dependency.

```sh
python -m evidencemill.cli ed2301.pdf --ocr --facts-only
python -m evidencemill.review_table_rows ed2301.pdf --sheet 5
python -m unittest discover -s tests -p test_review_table_rows.py
```

The helper is an opt-in recovery pass. It emits unverified row suggestions and retains the default extractor's behavior. Two focused tests exercise the motivating geometry and rejection of a word crossing the inferred row boundary.

## Manufacturer support HTML

[Apollo E1/F1 support](https://apolloscooters.co/help/e1-error-code), captured November 21, 2026 Central, SHA-256 9d251c8c6e58ea8a3226640d37d4aa319fc4c944a5f42b85a38f5ab652d92a9c. Retrieved for CSS Verification Desk gap 818-error. The capture is a mutable page. Use identical bytes for comparisons and label changed bytes as a different capture.

| Extractor | Observed result on the same capture | Decision |
| --- | --- | --- |
| EvidenceMill HTML | 136 candidates and stable locator text-39:s1 for the article's E1/F1 explanation. Generic HTML also includes unrelated navigation. | Keep existing parser. |
| [Trafilatura](https://github.com/adbar/trafilatura) 2.3.1, Apache-2.0 | 0.0168 s after import. Cleaner 2,369-character output retained the explanation and removed the Dash navigation mention. Returned text lacks the control's granular locator. Zero additional verified applicable claims on this gap. | Defer as an optional article-region hint until more sources justify the dependencies. |
| [extruct](https://github.com/scrapinghub/extruct) 0.18.0, BSD | 0.0020 s after import. Two JSON-LD records and zero microdata records. No Dash-specific applicability. Zero additional verified applicable claims on this gap. | Defer for a product page where structured metadata provides actual additional specs. |

Use `python -m evidencemill.cli apollo-e1.html --facts-only`, `trafilatura.extract(html)` and `extruct.extract(html, syntaxes=['json-ld','microdata'])`. Trafilatura and extruct were isolated exploratory installs. No alternative dependency or code was adopted. Timings are one warm in-process observation. CPU and RSS were not instrumented for the HTML comparisons. Zero paid API calls. Code agreement on one page is not independent corroboration.

Further candidates remain unbenchmarked. [Unstructured](https://github.com/Unstructured-IO/unstructured) duplicates established dispatch and introduces layout dependencies, so defer until an uncovered format is demonstrated. Docling, Marker, and prior PDF tool assessments remain recorded in the earlier pilot. Scope judgments are CSS_DATABASE's responsibility.
