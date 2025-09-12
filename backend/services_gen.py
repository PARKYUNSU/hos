import os
from typing import List, Optional
import base64
from openai import OpenAI


def get_client() -> Optional[OpenAI]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        print(f"OpenAI 클라이언트 초기화 오류: {e}")
        return None


SYSTEM_PROMPT = (
    "당신은 해외 응급 환자를 돕는 안전 중심 챗봇입니다. 의료적 진단을 내리지 않고,"
    "일본의 일반 의약품(OTC)과 기본 응급처치, 그리고 119 연락 권고를 중심으로 조언하세요."
    " 모든 출력은 한국어로 제공하세요. 금기/주의, 119 기준을 명확히 표기하세요."
)


def generate_advice(symptoms: str, findings: List[str], passages: List[str], image_bytes: Optional[bytes] = None) -> str:
    client = get_client()
    if not client:
        # 키 없으면 규칙 기반 한국어 요약만 반환 (근거 텍스트는 별도 라벨로 표시)
        base = "증상에 대한 일반 조언입니다. 심각하면 119(일본)에 즉시 연락하세요."
        if findings:
            base += " 이미지 단서: " + ", ".join(findings)
        return base

    text_block = (
        "다음 정보를 바탕으로 안전 중심의 응급처치/OTC 조언을 제공하세요."
        " 반드시 금기/주의(영유아, 임산부, 기저질환) 포함, 119 호출 기준 명시.\n"
        f"증상: {symptoms}\n"
        f"이미지 단서(모델 추정 아님, 사용자 입력 기반): {', '.join(findings) if findings else '없음'}\n"
        f"참고문헌:\n- " + "\n- ".join(passages)
    )

    content: List[dict] = [{"type": "text", "text": text_block}]
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
            }
        )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.2,
        max_tokens=350,
    )
    return completion.choices[0].message.content or ""


