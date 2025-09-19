import os
import sys
import importlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    # 테스트 환경 변수 설정: 무거운 RAG 로딩 방지, 관리자 계정 지정
    os.environ["FAST_MODE"] = "1"
    os.environ["ADMIN_USER"] = "admin"
    os.environ["ADMIN_PASS"] = "testpass"

    # 애플리케이션 로드/갱신
    # 프로젝트 루트를 import 경로에 추가 (CI에서 tests 디렉토리만 잡히는 경우 대비)
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    import main  # type: ignore
    importlib.reload(main)

    # OpenAI 의존성 우회
    main.app.dependency_overrides[main.get_openai_client] = lambda: object()

    # generate_advice 모킹 (외부 API 호출 방지)
    def _fake_generate_advice(symptoms, findings, passages, image_bytes, client):  # noqa: ANN001
        return {
            "advice": "[테스트] 이 조언은 테스트 목적으로 생성되었습니다.",
            "otc": [],
            "is_default_advice": False,
        }

    try:
        import services_gen  # type: ignore

        setattr(services_gen, "generate_advice", _fake_generate_advice)
    except Exception:
        # main 모듈에 직접 바인딩된 심볼도 교체
        pass

    # main 모듈이 from services_gen import generate_advice 로 바인딩한 참조도 교체
    try:
        setattr(main, "generate_advice", _fake_generate_advice)
    except Exception:
        pass

    return TestClient(main.app)


@pytest.fixture(scope="session")
def admin_auth():
    return (os.getenv("ADMIN_USER", "admin"), os.getenv("ADMIN_PASS", "testpass"))


@pytest.fixture(scope="session", autouse=True)
def seed_crawling_job():
    # 테스트용 크롤링 작업 1건 시드 (존재하면 무시)
    try:
        import main  # type: ignore
        logger = getattr(main, "symptom_logger", None)
        if logger is None:
            return
        job_id = logger.create_crawling_job(["テスト", "응급"], ["jrc", "mhlw_health"])  # type: ignore[attr-defined]
        # 완료 처리로 마크
        logger.update_crawling_job(job_id, status="completed", results_count=1, error_message=None)  # type: ignore[attr-defined]
    except Exception:
        pass


