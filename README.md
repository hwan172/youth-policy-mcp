# Youth Policy Navigator (청년 정책 내비게이터)

카카오 PlayMCP 공모전용 MCP 서버. **청년 정책·지원금을 검색·매칭하고, 사용자 상황 대비
자격 여부를 조건별로 판정(적격/부적격/정보부족)해 '이유'와 함께 반환**한다.

단순 조회가 아니라 **'판단'이 핵심 차별점**이다. 자격 판정 결과의 `missing_info`(되물어야 할 질문)가
호스트 LLM의 후속 질문을 유도해, "물어보고 → 저장하고 → 재판정"하는 에이전틱 루프를 만든다.

## 컨셉

- **검색**: 온통청년(한국고용정보원) 청년정책 API + 내장 대표 정책 코퍼스를 Contextual BM25로 융합.
- **판정(★킬러)**: 정책의 구조화 조건(연령·지역·소득·취업상태)을 사용자 프로필과 대조해
  조건별 `pass / fail / unknown / manual` → 종합 `eligible / ineligible / needs_more_info / manual_review`.
- **개인화**: SQLite 메모리에 사용자 상황을 저장하고 질의 관련 항목을 BM25로 회상.
- 설계 원칙: 서버는 **결정론적 데이터 + 판정 도구**만 제공한다. 자연어 해석·최종 안내 문구는 호스트 LLM 몫.

## 툴 5개

| 툴 | 설명 | 종류 |
|---|---|---|
| `search_youth_policies(query, region?, category?, k=6)` | 청년정책 검색(API+코퍼스 융합) | read-only |
| `check_eligibility(policy_id, user_key?, profile?)` ★ | 정책 조건 vs 프로필 자격 판정 | read-only |
| `get_policy_detail(policy_id)` | 신청방법·기간·서류·URL·주관기관 | read-only |
| `remember_user_profile(user_key, note)` | 사용자 상황 저장 | mutating |
| `recall_user_profile(user_key, query?, k=6)` | 저장된 상황 회상 | read-only |

### 판정 루프 예시

1. `search_youth_policies("월세 지원")` → `youth-monthly-rent` 등 후보 + 구조화 조건.
2. `check_eligibility("youth-monthly-rent", profile={"age": 40})` → `ineligible`, 이유: "나이 40세가 대상 연령(만 19~34세) 범위를 벗어납니다."
3. 정보가 부족하면(`needs_more_info`) 반환된 `questions`로 사용자에게 되묻고,
   `remember_user_profile`로 답을 저장한 뒤 `check_eligibility`를 재호출.

## 실행

```bash
uv sync --extra dev          # 의존성 설치(+ 테스트용)
uv run pytest -q             # 테스트 (전부 네트워크 불필요)

uv run policy-mcp                          # 로컬 stdio (MCP Inspector)
MCP_TRANSPORT=http uv run policy-mcp       # 원격 http → http://<host>:8000/mcp
```

Docker(카카오 KC 배포용, linux/amd64 필수):

```bash
docker build --platform linux/amd64 -t policy-mcp .
```

## API 키 발급

키가 없어도 **내장 코퍼스 기반 mock으로 동작**한다(응답에 `is_mock=True` 명시).
라이브 데이터를 쓰려면:

1. <https://www.youthcenter.go.kr> 로그인 → **마이페이지 → OPEN API → 인증키 발급 신청**
   (공공데이터포털 `한국고용정보원_온통청년_청년정책API`, 목록ID 15143273)
2. 프로젝트 루트에 `.env` 생성 후:

   ```
   YOUTHCENTER_API_KEY=발급받은_인증키
   ```

> ⚠️ 온통청년 API의 엔드포인트/파라미터/응답 필드는 공식 문서가 JS로 렌더링되어 정적 확인이
> 어려웠다. `src/policy_mcp/clients/youthcenter.py`는 2025 개편 신규 API(getPlcy 계열)의 알려진
> 최선 규격으로 작성돼 있으며, **키 발급 후 실제 응답과 대조해 필드 매핑을 최종 검증**해야 한다.
> 파일 상단 주석 참고.

## 데이터 기준일

내장 코퍼스의 정책 조건(연령·소득·금액)은 **2026-07 기준 사실확인** 후 각 정책에 `source`·`as_of`를
명시했다. 수치는 공고마다 변동될 수 있으므로 신청 전 각 정책의 `apply_url` 최신 공고를 확인할 것.

## 구조

```
src/policy_mcp/
  server.py          # FastMCP 서버 + 툴 5개
  policies.py        # 검색 서비스(API+코퍼스 융합)
  eligibility.py     # ★ 자격 판정 엔진(순수/결정론)
  policy_corpus.py   # 내장 대표 정책 10선(검색 근거 + 구조화 조건)
  memory.py          # 개인화 메모리(SQLite + BM25 회상)
  retrieval.py       # Contextual BM25 엔진
  cache.py           # in-memory TTL 캐시
  config.py          # 환경설정
  clients/youthcenter.py  # 온통청년 API 클라이언트(+mock 폴백)
tests/               # 네트워크 불필요 단위테스트 (48개)
```
