"""
Playwright 기반 동적 렌더링 유틸리티

환경 변수:
- USE_PLAYWRIGHT_CRAWLING: "1"/"true"/"on" 이면 Playwright 사용 시도
- PW_HEADLESS: 기본 1 (headless), 0이면 브라우저 표시
- PW_NAV_TIMEOUT_MS: 탐색 타임아웃(ms), 기본 15000
- PW_WAIT_UNTIL: load|domcontentloaded|networkidle (기본 networkidle)
- PW_WAIT_SELECTOR: 선택자 대기 옵션 (없으면 미사용)
"""

from __future__ import annotations

import os
from typing import Optional


def _env_flag(name: str, default: str = "0") -> bool:
    val = os.getenv(name, default)
    return str(val).lower() in ("1", "true", "on", "yes")


def is_playwright_enabled() -> bool:
    """환경 변수로 Playwright 사용 여부를 제어."""
    return _env_flag("USE_PLAYWRIGHT_CRAWLING", "0") and is_playwright_available()


def is_playwright_available() -> bool:
    """Playwright가 설치되어 있고 임포트 가능한지 확인."""
    try:
        # 지연 임포트로 미설치 환경에서도 안전
        from playwright.sync_api import sync_playwright  # type: ignore
        _ = sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


def fetch_html_with_playwright(
    url: str,
    wait_selector: Optional[str] = None,
    wait_until: Optional[str] = None,
    timeout_ms: Optional[int] = None,
) -> Optional[str]:
    """
    주어진 URL을 Playwright로 렌더링 후 HTML을 반환. 실패 시 None 반환.

    - wait_selector가 주어지면 해당 요소가 나타날 때까지 대기
    - wait_until: load|domcontentloaded|networkidle
    - timeout_ms: 탐색 타임아웃(ms)
    """
    if not is_playwright_available():
        return None

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        headless = _env_flag("PW_HEADLESS", "1")
        nav_timeout_ms = int(os.getenv("PW_NAV_TIMEOUT_MS", "15000"))
        if timeout_ms is not None:
            nav_timeout_ms = timeout_ms
        wait_until_opt = (wait_until or os.getenv("PW_WAIT_UNTIL", "networkidle")).lower()
        if wait_until_opt not in ("load", "domcontentloaded", "networkidle"):
            wait_until_opt = "networkidle"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(nav_timeout_ms)
            page.goto(url, wait_until=wait_until_opt, timeout=nav_timeout_ms)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=nav_timeout_ms)
                except Exception:
                    # 선택자 대기는 실패하더라도 HTML은 반환
                    pass
            html = page.content()
            context.close()
            browser.close()
            return html
    except Exception:
        return None


