#!/usr/bin/env python3
"""
RAG-LLM 차이 분석 및 자동 학습 시스템
- RAG 결과와 LLM 결과 비교
- 차이가 큰 경우 RAG 데이터에 추가
- LLM 생성 데이터를 규칙으로 변환
"""

import os
import sys
import json
import re
from typing import List, Dict, Tuple
from datetime import datetime

# 백엔드 서비스 임포트
sys.path.append('backend')
from services_advanced_rag import GLOBAL_ADVANCED_RAG
from services_gen import generate_advice

class RAGLLMAnalyzer:
    def __init__(self):
        self.rag = GLOBAL_ADVANCED_RAG
        self.differences = []
        self.new_rules = []
        
    def analyze_differences(self, test_results_file: str = "test_results_100_symptoms.json"):
        """100개 테스트 결과에서 RAG-LLM 차이 분석"""
        print("🔍 RAG-LLM 차이 분석 시작...")
        
        with open(test_results_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for result in data['results']:
            if result['success']:
                self._analyze_single_result(result)
        
        self._generate_improvements()
    
    def _analyze_single_result(self, result: Dict):
        """단일 결과 분석"""
        symptom = result['symptom']
        rag_search = result['rag_search']
        llm_advice = result['llm_advice']
        rule_advice = result['rule_based_advice']
        
        # RAG에서 찾은 문서들
        rag_docs = rag_search.get('top_titles', [])
        
        # LLM 조언
        llm_text = llm_advice.get('preview', '')
        
        # 규칙 기반 조언
        rule_text = rule_advice.get('advice', '')
        
        # 차이점 분석
        if self._has_significant_difference(rag_docs, llm_text, rule_text):
            difference = {
                'symptom': symptom,
                'rag_docs': rag_docs,
                'llm_advice': llm_text,
                'rule_advice': rule_text,
                'difference_type': self._classify_difference(rag_docs, llm_text, rule_text),
                'timestamp': datetime.now().isoformat()
            }
            self.differences.append(difference)
    
    def _has_significant_difference(self, rag_docs: List[str], llm_text: str, rule_text: str) -> bool:
        """중요한 차이가 있는지 판단"""
        # 1. RAG 문서가 부족한 경우
        if len(rag_docs) < 2:
            return True
        
        # 2. LLM이 더 구체적인 정보를 제공하는 경우
        if len(llm_text) > len(rule_text) * 1.5:
            return True
        
        # 3. LLM이 일본어 제품명을 포함하는 경우
        japanese_products = re.findall(r'[ア-ン]+', llm_text)
        if japanese_products and not any(product in rule_text for product in japanese_products):
            return True
        
        # 4. LLM이 구체적인 용법을 설명하는 경우
        usage_keywords = ['복용', '용법', '하루', '회', 'mg', '정', '알약']
        if any(keyword in llm_text for keyword in usage_keywords) and not any(keyword in rule_text for keyword in usage_keywords):
            return True
        
        return False
    
    def _classify_difference(self, rag_docs: List[str], llm_text: str, rule_text: str) -> str:
        """차이 유형 분류"""
        if len(rag_docs) < 2:
            return "RAG_DOCS_INSUFFICIENT"
        elif len(llm_text) > len(rule_text) * 1.5:
            return "LLM_MORE_DETAILED"
        elif re.search(r'[ア-ン]+', llm_text):
            return "LLM_HAS_JAPANESE_PRODUCTS"
        else:
            return "LLM_HAS_USAGE_INFO"
    
    def _generate_improvements(self):
        """개선사항 생성"""
        print(f"\n📊 분석 결과: {len(self.differences)}개 차이점 발견")
        
        # 1. RAG 데이터 추가 대상
        rag_candidates = [d for d in self.differences if d['difference_type'] == 'RAG_DOCS_INSUFFICIENT']
        print(f"📚 RAG 데이터 추가 대상: {len(rag_candidates)}개")
        
        # 2. 규칙 추가 대상
        rule_candidates = [d for d in self.differences if d['difference_type'] in ['LLM_MORE_DETAILED', 'LLM_HAS_JAPANESE_PRODUCTS', 'LLM_HAS_USAGE_INFO']]
        print(f"📋 규칙 추가 대상: {len(rule_candidates)}개")
        
        # 3. 개선사항 생성
        self._create_rag_improvements(rag_candidates)
        self._create_rule_improvements(rule_candidates)
    
    def _create_rag_improvements(self, candidates: List[Dict]):
        """RAG 개선사항 생성"""
        print("\n🔧 RAG 개선사항 생성 중...")
        
        for candidate in candidates[:10]:  # 상위 10개만
            symptom = candidate['symptom']
            llm_advice = candidate['llm_advice']
            
            # LLM 조언을 RAG 문서로 변환
            rag_doc = self._convert_llm_to_rag_doc(symptom, llm_advice)
            if rag_doc:
                self._save_rag_doc(rag_doc, symptom)
    
    def _create_rule_improvements(self, candidates: List[Dict]):
        """규칙 개선사항 생성"""
        print("\n🔧 규칙 개선사항 생성 중...")
        
        for candidate in candidates[:10]:  # 상위 10개만
            symptom = candidate['symptom']
            llm_advice = candidate['llm_advice']
            
            # LLM 조언을 규칙으로 변환
            new_rule = self._convert_llm_to_rule(symptom, llm_advice)
            if new_rule:
                self.new_rules.append(new_rule)
    
    def _convert_llm_to_rag_doc(self, symptom: str, llm_advice: str) -> str:
        """LLM 조언을 RAG 문서로 변환"""
        # 증상별 키워드 추출
        keywords = self._extract_keywords(symptom)
        
        # 문서 구조화
        doc = f"""
증상: {symptom}
키워드: {', '.join(keywords)}

상세 조언:
{llm_advice}

출처: AI 생성 (LLM 기반)
생성일: {datetime.now().strftime('%Y-%m-%d')}
"""
        return doc.strip()
    
    def _convert_llm_to_rule(self, symptom: str, llm_advice: str) -> Dict:
        """LLM 조언을 규칙으로 변환"""
        # 증상 키워드 추출
        keywords = self._extract_keywords(symptom)
        
        # OTC 약물 추출
        otc_products = self._extract_otc_products(llm_advice)
        
        # 조언 추출
        advice = self._extract_advice(llm_advice)
        
        return {
            'keywords': keywords,
            'advice': advice,
            'otc': otc_products,
            'symptom': symptom
        }
    
    def _extract_keywords(self, symptom: str) -> List[str]:
        """증상에서 키워드 추출"""
        # 기본 키워드
        keywords = [symptom]
        
        # 언어별 키워드 추가
        if any(char in symptom for char in '가-힣'):
            keywords.extend(['한국어', '증상'])
        if any(char in symptom for char in 'a-zA-Z'):
            keywords.extend(['영어', 'symptom'])
        if any(char in symptom for char in 'ア-ン'):
            keywords.extend(['일본어', '症状'])
        
        return keywords
    
    def _extract_otc_products(self, llm_advice: str) -> List[str]:
        """LLM 조언에서 OTC 제품 추출"""
        products = []
        
        # 일본어 제품명 추출
        japanese_products = re.findall(r'[ア-ン]+', llm_advice)
        products.extend(japanese_products)
        
        # 한국어 제품명 추출
        korean_products = re.findall(r'[가-힣]+(?:제|약|액|연고|크림)', llm_advice)
        products.extend(korean_products)
        
        return list(set(products))
    
    def _extract_advice(self, llm_advice: str) -> str:
        """LLM 조언에서 핵심 조언 추출"""
        # 첫 번째 문장을 핵심 조언으로 사용
        sentences = llm_advice.split('.')
        if sentences:
            return sentences[0].strip() + '.'
        return llm_advice[:100] + '...'
    
    def _save_rag_doc(self, doc: str, symptom: str):
        """RAG 문서 저장"""
        # 파일명 생성
        safe_symptom = re.sub(r'[^\w\s-]', '', symptom).strip()
        filename = f"data/passages/jp/llm_generated_{safe_symptom[:20]}.txt"
        
        # 디렉토리 생성
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # 파일 저장
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(doc)
        
        print(f"  💾 RAG 문서 저장: {filename}")
    
    def save_improvements(self):
        """개선사항 저장"""
        # 1. 차이점 분석 결과 저장
        with open("rag_llm_differences.json", "w", encoding="utf-8") as f:
            json.dump(self.differences, f, ensure_ascii=False, indent=2)
        
        # 2. 새로운 규칙 저장
        with open("new_rules.json", "w", encoding="utf-8") as f:
            json.dump(self.new_rules, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 개선사항 저장 완료:")
        print(f"  - RAG-LLM 차이점: rag_llm_differences.json")
        print(f"  - 새로운 규칙: new_rules.json")

def main():
    """메인 실행 함수"""
    print("🧠 RAG-LLM 차이 분석 및 자동 학습 시스템")
    print("=" * 60)
    
    analyzer = RAGLLMAnalyzer()
    analyzer.analyze_differences()
    analyzer.save_improvements()
    
    print("\n✅ 분석 완료!")

if __name__ == "__main__":
    main()
