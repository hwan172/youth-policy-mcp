"""환경설정 로딩.

API 키는 환경변수(.env)에서만 읽는다 — 소스에 하드코딩 금지.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# 프로젝트 루트의 .env 를 로드한다(있을 경우). 없으면 조용히 넘어간다.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    # 온통청년 청년정책 API 키 (공공데이터포털 15143273 / 한국고용정보원).
    # 미설정이면 None → 클라이언트는 내장 코퍼스 기반 mock 으로 폴백.
    youthcenter_api_key: str | None
    # 서버 실행 설정
    transport: str
    host: str
    port: int


def _env(name: str) -> str | None:
    # 빈 문자열도 미설정으로 취급
    return os.environ.get(name) or None


def load_settings() -> Settings:
    return Settings(
        youthcenter_api_key=_env("YOUTHCENTER_API_KEY"),
        transport=os.environ.get("MCP_TRANSPORT", "stdio").lower(),
        host=os.environ.get("MCP_HOST", "0.0.0.0"),
        # 클라우드가 PORT를 주입하는 경우(Git 소스 배포)도 수용
        port=int(os.environ.get("MCP_PORT") or os.environ.get("PORT") or "8000"),
    )


settings = load_settings()
