"""정책 검색 서비스 — 내장 코퍼스 BM25 + (키 있으면) 온통청년 API 융합.

- 내장 코퍼스 인덱스는 첫 사용 시 한 번 구축(인메모리, 네트워크 0). 작은 코퍼스라 <10ms.
- 서버는 근거·구조화 조건을 반환하고, 최종 안내 문구는 호스트 LLM 이 종합한다.
"""
from __future__ import annotations

from functools import lru_cache

from . import policy_corpus
from .clients import youthcenter
from .retrieval import BM25Index


@lru_cache(maxsize=1)
def _index() -> BM25Index:
    return BM25Index(policy_corpus.all_chunks())


def corpus_search(query: str, region: str | None = None, category: str | None = None, k: int = 6) -> list[dict]:
    """내장 코퍼스에서 질의 관련 정책 top-k(구조화 detail + score)."""
    hits = _index().search(query, max(k * 2, k))
    out: list[dict] = []
    for score, chunk in hits:
        p = policy_corpus.get_policy(chunk.id)
        if p is None:
            continue
        if region:
            r = region.replace(" ", "")
            if p.regions and not any(r in x.replace(" ", "") or x.replace(" ", "") in r for x in p.regions):
                continue
        if category and category not in p.category and category not in p.subcategory:
            continue
        out.append({**p.detail(), "score": score, "origin": "corpus"})
        if len(out) >= k:
            break
    return out


async def search(
    api_key: str | None,
    query: str,
    region: str | None = None,
    category: str | None = None,
    k: int = 6,
) -> dict:
    """온통청년 API(키 있으면) + 내장 코퍼스 BM25 검색을 융합한다.

    - 코퍼스 결과는 항상 포함(근거·구조화 조건 제공, check_eligibility 대상).
    - API 결과는 라이브일 때만 추가(is_mock 인 경우 코퍼스와 중복 → 코퍼스만 사용).
    - policy_id 중복은 코퍼스 우선(구조화 조건이 풍부).
    """
    corpus_hits = corpus_search(query, region, category, k)

    api = await youthcenter.search_policies(
        api_key, query=query, category=category, region=region, page_size=k)

    fused: list[dict] = list(corpus_hits)
    live = not api.get("is_mock", True)
    if live:
        seen = {h["policy_id"] for h in fused}
        for it in api.get("items", []):
            if it.get("policy_id") and it["policy_id"] not in seen:
                fused.append({**it, "origin": "youthcenter_api"})
                seen.add(it["policy_id"])

    return {
        "query": query,
        "results": fused[: max(k, len(corpus_hits))],
        "count": len(fused[: max(k, len(corpus_hits))]),
        "data_source": {
            "corpus": len(corpus_hits),
            "live_api": live,
            "api_note": api.get("note", ""),
        },
        "note": ("각 result 는 정책 요약 + 구조화 자격조건(eligibility_summary)을 담는다. "
                 "특정 정책의 적격 여부는 policy_id 로 check_eligibility 를 호출해 판정하라. "
                 "라이브 API 미연동 시 내장 대표 정책으로 제한된다."),
    }
