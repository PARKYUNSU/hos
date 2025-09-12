#!/usr/bin/env python3
"""
개선된 시스템 테스트
- 새로운 규칙이 적용된 시스템 테스트
- RAG-LLM 통합 효과 확인
"""

import os
import sys
import time
from datetime import datetime

# 백엔드 서비스 임포트
sys.path.append('backend')
from services_advanced_rag import GLOBAL_ADVANCED_RAG
from services_gen import generate_advice

def test_improved_system():
    """개선된 시스템 테스트"""
    print("🧪 개선된 시스템 테스트")
    print("=" * 50)
    
    # 테스트 증상들
    test_symptoms = [
        "열이 39도입니다",
        "두통이 심해요", 
        "복통과 설사",
        "벌레에 물렸어요",
        "가슴이 아파요"
    ]
    
    rag = GLOBAL_ADVANCED_RAG
    
    for i, symptom in enumerate(test_symptoms, 1):
        print(f"\n🔍 [{i}/5] 테스트: '{symptom}'")
        
        # 1. RAG 검색
        hits = rag.search(symptom, top_k=3, use_reranking=True)
        print(f"  📚 RAG: {len(hits)}개 문서")
        
        # 2. LLM 조언
        rag_passages = [hit[0] for hit in hits[:3]] if hits else []
        llm_advice = generate_advice(symptom, [], rag_passages)
        print(f"  🤖 LLM: {len(llm_advice) if llm_advice else 0}자")
        
        # 3. 규칙 기반 조언 (개선된 버전)
        from ui.app import simple_text_rules
        rule_result = simple_text_rules(symptom)
        print(f"  📋 규칙: {len(rule_result['advice'])}자, OTC {len(rule_result['otc'])}개")
        
        # 4. 조언 품질 비교
        if llm_advice and len(llm_advice) > 100:
            print(f"  ✅ 고품질 조언 생성됨")
        else:
            print(f"  ⚠️ 조언 품질 개선 필요")

if __name__ == "__main__":
    test_improved_system()
