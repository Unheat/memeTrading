# `app/sec/pull.py` Specification

## Status

Completed on 2026-09-02. Scope: controlled acquisition of already-selected SEC documents into one case-local corpus.

## Goal

Provide the future `pull_sec_filings` tool implementation. The outer agent selects exact accession/document records discovered earlier; this module downloads only those records, stores them with receipts, and returns a `PulledCorpus` that the later verifier can use without any network access.

## Public contract

```python
@dataclass(frozen=True)
class SelectedSecDocument:
    filing: FilingMetadata
    document_name: str
    source_url: str

@dataclass(frozen=True)
class PullError:
    code: Literal[
        "INVALID_INPUT", "INVALID_SELECTION", "UNAVAILABLE",
        "SIZE_LIMIT", "STORAGE_FAILURE", "DEPENDENCY_UNAVAILABLE"
    ]
    message: str
    retryable: bool

@dataclass(frozen=True)
class FilingPullResult:
    corpus: PulledCorpus | None
    error: PullError | None

def pull_sec_filings(
    cases_root: Path,
    case_id: str,
    selections: Iterable[SelectedSecDocument],
    downloader: Callable[[str], bytes] | None = None,
) -> FilingPullResult:
    ...
```

`SelectedSecDocument` is the precise hand-off from discovery to acquisition. Its `filing` contains ticker, CIK, form, date, accession, and filing URL. `document_name` must be that filing's primary document or one of its discoverable exhibits when those fields are present. `source_url` is the exact SEC document URL. A future outer agent serializes these selections rather than allowing a pull tool to choose documents by form or limit.

## Requirements

1. Validate `case_id` through `case_path`; do not create paths outside `cases_root`.
2. Require one or more selections for exactly one ticker and CIK. Reject duplicate `(accession, document_name)` selections.
3. Validate each selection: a non-empty safe document name, HTTPS `sec.gov` host, and identity match between the selection and its filing receipt. When `primary_document` or `exhibits` are present, name must be one of those declared values.
4. Use `downloader(url) -> bytes` when injected. The production default may request only an HTTPS SEC URL and must require a configured declared SEC user-agent identity. It has a named timeout and reads at most the named document-byte limit.
5. Set named conservative limits before network I/O: maximum selections per corpus and bytes per document. Never silently truncate a source.
6. Write each document under `cases/<case_id>/sec/documents/` using a deterministic safe filename derived from accession plus sanitized document name. Preserve original document name only in `DownloadedDocument` receipt data.
7. Compute a lower-case SHA-256 digest from exact stored bytes. Create validated `DownloadedDocument` records whose paths are relative to the case directory.
8. Build one `PulledCorpus` and atomically write its manifest using `write_corpus_manifest` only after all downloads and writes succeed.
9. On fetch, validation, or storage failure, remove only files created by this invocation. Do not delete a pre-existing corpus or its document files.
10. If a target file already exists with matching digest for the same selection, reuse it without invoking the downloader. A mismatch returns an error; never overwrite a previous receipt silently.
11. Return safe structured failures. Do not leak provider, filesystem, or HTTP exception text through `PullError`.

## Non-goals

- No filing discovery, autonomous selection, ticker switching, parsing, chunking, vector creation, BM25, FAISS, reranking, LLM, LangGraph, web search, article retrieval, or outer agent.
- No directory listing or document discovery at pull time.
- No live network tests.
- No source download by SEC verifier code.

## Error semantics

| Code | Meaning | Retryable |
| --- | --- | --- |
| `INVALID_INPUT` | Case root, ID, or selection iterable invalid | no |
| `INVALID_SELECTION` | Mixed company, duplicate, unsafe, undeclared, or non-SEC selection | no |
| `UNAVAILABLE` | SEC source/transport temporarily unavailable | yes |
| `SIZE_LIMIT` | Declared or received source exceeds configured limit | no |
| `STORAGE_FAILURE` | Local write or manifest persistence failed | yes |
| `DEPENDENCY_UNAVAILABLE` | Default downloader lacks SEC identity configuration | no |

## Acceptance criteria

- A fake downloader can create a `PulledCorpus`, receipt records, locally stored bytes, and readable manifest without network access.
- Exact selection validation rejects mixed ticker/CIK, duplicate records, unsafe names, non-SEC URLs, and undeclared document names.
- Success persists only case-local document paths, accurate SHA-256 values, and an atomic manifest.
- Source failure and size violation return structured errors and leave no files created by that attempt.
- Repeating an identical completed request does not redownload or overwrite the existing file.
- All tests in `tests/sec/test_pull.py`, all project tests, and Python compilation pass.

## References

- SEC official access policy: declared user agent, rate limit of ten requests per second, and retrieve only required data. <https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data>
- `reference/edgartools/` supplies discovery metadata only in this slice; no donor transport code is copied.

## Donor code provenance

No donor implementation was copied or adapted into this module. All `SelectedSecDocument`, pull-result, validation, local-write, checksum, and standard-library HTTP behavior is local code. Edgartools supplies upstream filing metadata before this module is called and is a black-box dependency, not a source-code donor here.

## Execution record

The module uses the Python standard library for the small, bounded production downloader. It requires `SEC_USER_AGENT` for live SEC requests, reads at most 10 MiB per document, waits 0.11 seconds between default requests, and accepts an injected downloader for all unit tests. Exact document selections are checked against discovered primary/exhibit names when those names are available.

Initial red run: `pytest tests/sec/test_pull.py -q` failed with six import errors because `app.sec.pull` did not exist. Final verification: 7 pull tests and 23 project tests passed; `python3 -m compileall -q app` passed. No live SEC smoke request was run because no SEC identity is configured.
