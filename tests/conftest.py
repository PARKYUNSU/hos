import os
import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client():
    # 테스트 환경 변수 설정: 무거운 RAG 로딩 방지, 관리자 계정 지정
    os.environ["FAST_MODE"] = "1"
    os.environ["ADMIN_USER"] = "admin"
    os.environ["ADMIN_PASS"] = "testpass"

    # 애플리케이션 로드/갱신
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
        setattr(main, "generate_advice", _fake_generate_advice)

    return TestClient(main.app)


@pytest.fixture(scope="session")
def admin_auth():
    return (os.getenv("ADMIN_USER", "admin"), os.getenv("ADMIN_PASS", "testpass"))


