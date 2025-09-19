import os
import time
import threading
import importlib
import requests
import pytest


def _start_server(port: int = 8010):
    os.environ["FAST_MODE"] = "1"
    os.environ["ADMIN_USER"] = "admin"
    os.environ["ADMIN_PASS"] = "testpass"

    import main  # type: ignore

    importlib.reload(main)

    try:
        # OpenAI 의존성 제거용 오버라이드
        main.app.dependency_overrides[main.get_openai_client] = lambda: object()
    except Exception:
        pass

    import uvicorn

    config = uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # 헬스 체크 대기
    base = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            r = requests.get(base + "/api/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.2)

    return server, thread, base


@pytest.mark.e2e
def test_admin_and_home_loads():
    try:
        server, thread, base = _start_server()

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                http_credentials={"username": "admin", "password": "testpass"}
            )
            page = context.new_page()

            # 홈 페이지 로드
            page.goto(base + "/", timeout=30000)
            assert page.title() is not None

            # 관리자 페이지 로드 (Basic Auth)
            page.goto(base + "/admin", timeout=30000)
            page.wait_for_selector("text=대시보드", timeout=10000)
            page.wait_for_selector("text=크롤링", timeout=10000)

            # 크롤링 탭 클릭 및 테이블 존재 확인
            page.click("text=크롤링")
            page.wait_for_selector("#crawlJobsTable", timeout=10000)

            context.close()
            browser.close()
    finally:
        try:
            server.should_exit = True  # type: ignore[attr-defined]
        except Exception:
            pass
        if 'thread' in locals():
            thread.join(timeout=5)


