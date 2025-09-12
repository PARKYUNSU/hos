import os
from typing import List, Optional
import base64
from openai import OpenAI
import streamlit as st


def get_client() -> Optional[OpenAI]:
    # Streamlit Cloud에서는 st.secrets 사용, 로컬에서는 os.getenv 사용
    try:
        api_key = st.secrets['secrets']['OPENAI_API_KEY']
    except:
        api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        return None
    try:
        return OpenAI(api_key=api_key)
    except Exception as e:
        print(f"OpenAI 클라이언트 초기화 오류: {e}")
        return None


SYSTEM_PROMPT = (
    "당신은 일본 여행자를 위한 전문 응급 의료 챗봇입니다. "
    "다음 원칙을 따라 조언하세요:\n\n"
    "1. **의료적 진단 금지**: 진단하지 않고 응급처치와 OTC 조언만 제공\n"
    "2. **일본 의료 시스템 특화**: 일본의 119, 약국, 병원 시스템에 맞춘 조언\n"
    "3. **안전 우선**: 위험한 증상은 즉시 119 호출 권고\n"
    "4. **실용적 조언**: 일본 약국에서 구매 가능한 OTC 약품 추천\n"
    "5. **한국어 출력**: 모든 조언을 한국어로 제공\n"
    "6. **금기사항 명시**: 영유아, 임산부, 기저질환자 주의사항 포함\n"
    "7. **RAG 문서 활용**: 제공된 일본 의료 문서를 참고하여 정확한 조언 제공\n\n"
    "조언 형식:\n"
    "- 응급처치 방법\n"
    "- 권장 OTC 약품 (일본 약국명 포함)\n"
    "- 119 호출 기준\n"
    "- 주의사항 및 금기사항"
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
        "다음 정보를 바탕으로 일본 여행자를 위한 전문 응급처치/OTC 조언을 제공하세요.\n\n"
        f"**증상**: {symptoms}\n"
        f"**이미지 분석 결과**: {', '.join(findings) if findings else '없음'}\n\n"
        f"**일본 의료 문서 참고자료**:\n" + 
        ("\n".join([f"- {passage[:200]}..." for passage in passages]) if passages else "참고 문서 없음") + "\n\n"
        "위 정보를 종합하여 다음 형식으로 조언하세요:\n"
        "1. 응급처치 방법\n"
        "2. 일본 약국 OTC 약품 추천 (약국명 포함)\n"
        "3. 119 호출 기준\n"
        "4. 주의사항 및 금기사항"
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

    # 모델 선택: 이미지가 있으면 gpt-4o, 없으면 gpt-4o-mini
    model = "gpt-4o" if image_bytes else "gpt-4o-mini"
    
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        temperature=0.2,
        max_tokens=500,  # 더 상세한 조언을 위해 토큰 수 증가
    )
    return completion.choices[0].message.content or ""


