"""온통청년 청년정책 OPEN API 클라이언트 (공공데이터포털 15143273 / 한국고용정보원).

⚠️ 키 발급 후 라이브 검증 필요.
  - 공식 문서 페이지(youthcenter.go.kr/cmnFooter/openapiIntro/oaiDoc, data.go.kr/data/15143273)는
    파라미터·응답 필드 표를 JS로 렌더링해 정적 스크래핑으로 확정하지 못했다(2026-07 조사).
  - 아래 엔드포인트·필드 매핑은 2025년 개편된 신규 청년정책 API(getPlcy 계열)의 '알려진 최선' 규격이다.
    실제 응답과 대조해 _ENDPOINT / _map_item() 필드명을 최종 조정할 것.
  - 조사 출처: 공공데이터포털 15143273, youthcenter.go.kr OPEN API 이용안내/마이페이지.

정직성 원칙(기존 레포 계승): 키가 없거나 호출이 실패하면 조용히 가짜 데이터를 흘리지 않는다.
내장 코퍼스를 mock 폴백으로 쓰되 응답에 is_mock=True 와 note 로 명시한다.
"""
from __future__ import annotations

import httpx

from .. import cache
from ..policy_corpus import POLICIES, Policy
from ..retrieval import bm25_search

# 2025 개편 신규 API(JSON 지원). 키 발급 후 실제 host/경로 재확인 필요.
_ENDPOINT = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
_TIMEOUT = 6.0
_CACHE_TTL = 300.0  # 라이브 성공 결과만 5분 캐시


def _map_item(item: dict) -> dict:
    """API 응답 아이템 → 내부 표준 dict. 필드명은 라이브 검증 후 조정(위 주석 참조)."""
    def g(*keys: str) -> str:
        for k in keys:
            v = item.get(k)
            if v not in (None, ""):
                return str(v)
        return ""

    def gi(*keys: str):
        v = g(*keys)
        try:
            return int(v) if v != "" else None
        except ValueError:
            return None

    return {
        "policy_id": g("plcyNo", "bizId", "polyBizSecd"),
        "name": g("plcyNm", "polyBizSttus"),
        "summary": g("plcyExplnCn", "polyItcnCn"),
        "support_content": g("plcySprtCn", "sporCn"),
        "category": g("lclsfNm", "polyBizTy"),
        "subcategory": g("mclsfNm"),
        "age_min": gi("sprtTrgtMinAge", "ageInfo"),
        "age_max": gi("sprtTrgtMaxAge"),
        "income_note": g("earnCndSeCd", "earnEtcCn", "earnCn"),
        "region_code": g("zipCd", "polyRlmCd"),
        "employment_text": g("jobCd", "empmSttsCn"),
        "education_text": g("schoolCd", "accrRqisCn"),
        "marital_text": g("mrgSttsCd"),
        "extra_qualification": g("addAplyQlfcCndCn", "etct"),
        "apply_url": g("aplyUrlAddr", "rfcSiteUrlAddr1"),
        "apply_period": g("aplyYmd", "bizPrdCn"),
        "agency": g("sprvsnInstCdNm", "rgtrInstCdNm", "cnsgNmor"),
    }


def _mock_search(query: str | None, region: str | None, category: str | None, page_size: int) -> dict:
    """내장 코퍼스 기반 mock. 키 없음/호출 실패 시 폴백. is_mock=True 명시."""
    pool: list[Policy] = POLICIES
    if region:
        r = region.replace(" ", "")
        pool = [p for p in pool if (not p.regions) or any(r in x.replace(" ", "") or x.replace(" ", "") in r for x in p.regions)]
    if category:
        pool = [p for p in pool if category in p.category or category in p.subcategory]

    if query and query.strip():
        hits = bm25_search(query, [p.to_chunk() for p in pool], k=page_size)
        by_id = {p.id: p for p in pool}
        items = [{**by_id[c.id].detail(), "score": s} for s, c in hits if c.id in by_id]
    else:
        items = [p.detail() for p in pool[:page_size]]

    return {
        "items": items,
        "count": len(items),
        "is_mock": True,
        "source": "내장 청년정책 코퍼스 (온통청년 API 키 미설정 → mock 폴백)",
        "note": ("YOUTHCENTER_API_KEY 미설정 또는 API 호출 실패로 내장 코퍼스로 응답했습니다. "
                 "라이브 데이터가 아니며, 정책 목록은 큐레이션된 대표 정책으로 제한됩니다."),
    }


async def search_policies(
    key: str | None,
    *,
    query: str | None = None,
    category: str | None = None,
    region: str | None = None,
    page_num: int = 1,
    page_size: int = 6,
) -> dict:
    """청년정책 검색. 키 None 이면 즉시 mock 폴백. 호출 실패 시에도 mock 으로 폴백(명시)."""
    if not key:
        return _mock_search(query, region, category, page_size)

    ck = ("youthcenter", query, category, region, page_num, page_size)
    cached = cache.get(ck, _CACHE_TTL)
    if cached is not None:
        return cached

    params: dict[str, str | int] = {
        "apiKeyNm": key,          # 키 발급 후 실제 파라미터명 확인 필요(예: apiKeyNm)
        "pageNum": page_num,
        "pageSize": page_size,
        "rtnType": "json",
    }
    if query:
        params["plcyKywdNm"] = query
    if category:
        params["lclsfNm"] = category

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        fallback = _mock_search(query, region, category, page_size)
        fallback["note"] = (f"온통청년 API 호출 실패({type(e).__name__}) → 내장 코퍼스로 폴백. "
                            "네트워크/키/필드 매핑을 확인하세요.")
        fallback["api_error"] = str(e)
        return fallback

    # 응답 구조(result.youthPolicyList 등)는 라이브 검증 후 확정 — 방어적으로 탐색.
    raw_items = _extract_items(data)
    items = [_map_item(it) for it in raw_items]
    result = {
        "items": items,
        "count": len(items),
        "is_mock": False,
        "source": "온통청년 청년정책 API (한국고용정보원, 공공데이터포털 15143273)",
        "note": "라이브 API 응답입니다. 필드 매핑은 clients/youthcenter.py 에서 관리합니다.",
    }
    if items:  # 성공 결과만 캐시
        cache.set(ck, result)
    return result


def _extract_items(data) -> list[dict]:
    """다양한 응답 래핑에서 정책 리스트를 방어적으로 추출한다."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    # 흔한 래핑 후보들을 순서대로 시도.
    for path in (("result", "youthPolicyList"), ("result", "plcyLst"),
                 ("youthPolicyList",), ("plcyLst",), ("data",), ("items",)):
        node = data
        ok = True
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                ok = False
                break
        if ok:
            if isinstance(node, list):
                return [x for x in node if isinstance(x, dict)]
            if isinstance(node, dict):
                return [node]
    return []
