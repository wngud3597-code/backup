from contracts import Evidence, SentenceCitation


def validate_and_filter_citations(
    sentences: list[SentenceCitation], evidence_map: dict[int, Evidence]
) -> tuple[list[SentenceCitation], list[Evidence]]:
    """유효한 인용 번호만 남기고, 실제 인용된 Evidence 객체 목록만 반환"""
    valid_sentences = []
    used_citation_ids = set()

    for s in sentences:
        filtered_cits = [c for c in s.citations if c in evidence_map]
        valid_sentences.append(SentenceCitation(text=s.text, citations=filtered_cits))
        used_citation_ids.update(filtered_cits)

    cited_evidences = [evidence_map[cid] for cid in sorted(used_citation_ids)]
    return valid_sentences, cited_evidences
