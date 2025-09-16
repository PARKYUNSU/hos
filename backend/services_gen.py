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
    "3. **안전 우선**: 위험 신호는 즉시 119 호출 권고\n"
    "4. **실용적 조언**: 일본 약국에서 구매 가능한 OTC 약품(제품명 포함) 추천\n"
    "5. **한국어 출력**: 모든 조언을 한국어로 제공\n"
    "6. **금기사항 명시**: 영유아, 임산부, 기저질환자 주의사항 포함\n"
    "7. **RAG 문서 활용**: 제공된 일본 의료 문서를 참고하여 정확한 조언 제공\n\n"
    "증상이 여러 개인 경우, **증상별 섹션**으로 구조화하세요. 각 증상 섹션은 아래 형식을 따릅니다:\n"
    "- 증상명\n"
    "  1) 응급처치\n"
    "  2) 권장 OTC (일본 제품/성분명 포함)\n"
    "  3) 119 호출 기준\n"
    "  4) 주의/금기 (영유아·임산부·기저질환 포함)\n\n"
    "마지막에 공통 주의사항이 있으면 한 줄로 덧붙이세요."
)


def generate_advice(symptoms: str, findings: str, passages: List, client: Optional[OpenAI] = None, image_bytes: Optional[bytes] = None) -> dict:
    if not client:
        client = get_client()
    
    if not client:
        # 키 없으면 규칙 기반 한국어 요약만 반환
        base = "증상에 대한 일반 조언입니다. 심각하면 119(일본)에 즉시 연락하세요."
        if findings:
            base += " 이미지 단서: " + findings
        return {
            'advice': base,
            'otc': [],
            'is_default_advice': True
        }

    # passages는 (text, score) 튜플 리스트
    passage_texts = [p[0] if isinstance(p, tuple) else p for p in passages]
    
    text_block = (
        "다음 정보를 바탕으로 일본 여행자를 위한 전문 응급처치/OTC 조언을 제공하세요.\n\n"
        f"**증상(원문)**: {symptoms}\n"
        f"**이미지 분석 결과**: {findings if findings else '없음'}\n\n"
        f"**일본 의료 문서 참고자료(요약 일부)**:\n" + 
        ("\n".join([f"- {passage[:200]}..." for passage in passage_texts]) if passage_texts else "참고 문서 없음") + "\n\n"
        "증상이 여러 개인 경우, '증상별 섹션'으로 구조화해 주세요. 각 섹션은\n"
        "[증상명] → 1) 응급처치  2) 권장 OTC(제품/성분)  3) 119 기준  4) 주의/금기\n"
        "마지막에 공통 주의사항이 있으면 한 줄로 덧붙이세요."
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
    
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0.1,  # 0.2 -> 0.1로 낮춰서 일관성 향상
            max_tokens=300,   # 400 -> 300으로 더 줄여서 속도 개선
            timeout=8,        # 타임아웃을 8초로 단축
        )
        advice = completion.choices[0].message.content or ""
        
        # OTC 추출 로직 강화: 정규식/키워드 매핑 기반
        otc: list[str] = []
        text_lower = advice.lower()
        
        patterns = [
            (r"アセトアミノフェン|acetaminophen|타이레놀|아세트아미노펜", "해열진통제 (아세트아미노펜)"),
            (r"イブプロフェン|ibuprofen|이부프로펜|バファリン|ロキソニン|ロキソプロフェン", "진통·소염제 (이부프로펜/로키소프로펜)"),
            (r"抗ヒスタミン|antihistamine|항히스타민|アレグラ|フェキソフェナジン|セチリジン", "항히스타민제"),
            (r"消化薬|健胃|胃薬|制酸|소화제|제산제|ガスター|ファモチジン", "소화제/제산제"),
            (r"鎮咳|去痰|咳止め|기침약|거담|디엠|デキストロメトルファン", "기침약/거담제"),
            (r"ロペラミド|loperamide|지사제|설사|下痢止め", "지사제 (로페라마이드)"),
            (r"ヒドロコルチゾン|하이드로코르티손|스테로이드 外用|ステロイド外用", "스테로이드 외용제 (히드로코르티손)"),
        ]
        
        import re
        for pattern, label in patterns:
            if re.search(pattern, advice, flags=re.IGNORECASE):
                if label not in otc:
                    otc.append(label)
            
        return {
            'advice': advice,
            'otc': otc,
            'is_default_advice': False
        }
    except Exception as e:
        return {
            'advice': f"LLM 오류: {str(e)}",
            'otc': [],
            'is_default_advice': True
        }


