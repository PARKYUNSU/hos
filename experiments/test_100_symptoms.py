#!/usr/bin/env python3
"""
100가지 증상 종합 테스트 시스템
- LLM 기능 테스트
- RAG 검색 테스트  
- 크롤링 자동화 테스트
- 전체 시스템 통합 테스트
"""

import os
import sys
import time
import json
import random
from datetime import datetime
from typing import List, Dict, Tuple

# 백엔드 서비스 임포트
sys.path.append('backend')
from services_logging import symptom_logger
from services_auto_crawler import auto_crawl_unhandled_symptoms
from services_advanced_rag import GLOBAL_ADVANCED_RAG, load_disk_passages
from services_gen import generate_advice

# 100가지 증상 목록 (한국어, 영어, 일본어 혼합)
SYMPTOMS_100 = [
    # 발열 관련 (10개)
    "열이 39도입니다", "fever 38.5", "発熱が続きます", "고열이 나요", "체온이 높아요",
    "열감이 있어요", "몸이 뜨거워요", "발열과 두통", "고열과 오한", "열이 안 떨어져요",
    
    # 두통 관련 (10개)
    "두통이 심해요", "headache severe", "頭痛がひどい", "머리가 아파요", "편두통이에요",
    "두통과 구토", "머리가 무거워요", "두통이 계속돼요", "머리가 지끈거려요", "두통과 어지러움",
    
    # 복통 관련 (10개)
    "복통이 심해요", "stomach ache", "腹痛がひどい", "배가 아파요", "위가 아파요",
    "복통과 설사", "배가 부글부글해요", "복통과 구토", "배가 쥐어짜져요", "복부 경련이에요",
    
    # 호흡기 관련 (10개)
    "기침이 심해요", "cough persistent", "咳が止まらない", "가래가 나와요", "목이 아파요",
    "인후통이 심해요", "코가 막혀요", "콧물이 나와요", "숨이 가빠요", "호흡이 어려워요",
    
    # 피부 관련 (10개)
    "발진이 생겼어요", "rash appeared", "発疹が出ました", "가려워요", "피부가 붉어져요",
    "알레르기 반응", "두드러기가 나왔어요", "피부가 따갑습니다", "물집이 생겼어요", "피부가 건조해요",
    
    # 외상 관련 (10개)
    "상처가 났어요", "cut bleeding", "切り傷ができました", "피가 나와요", "다쳤어요",
    "멍이 들었어요", "타박상이에요", "찰과상이에요", "찔렸어요", "부러진 것 같아요",
    
    # 벌레/곤충 관련 (10개)
    "벌레에 물렸어요", "insect bite", "虫に刺されました", "모기에 물렸어요", "말벌에 쏘였어요",
    "벌에 쏘였어요", "개미에 물렸어요", "진드기에 물렸어요", "벌레 물림 부종", "곤충 알레르기",
    
    # 소화기 관련 (10개)
    "설사가 심해요", "diarrhea severe", "下痢がひどい", "구토가 나와요", "토할 것 같아요",
    "속이 메스꺼워요", "소화가 안돼요", "복부 팽만감", "가스가 차요", "배가 더부룩해요",
    
    # 신경계 관련 (10개)
    "어지러워요", "dizziness", "めまいがします", "현기증이 나요", "머리가 어지러워요",
    "의식이 흐려져요", "기절할 것 같아요", "손발이 저려요", "감각이 이상해요", "경련이 일어나요",
    
    # 기타 응급상황 (10개)
    "가슴이 아파요", "chest pain", "胸が痛い", "심장이 두근거려요", "호흡곤란이에요",
    "의식을 잃었어요", "unconscious", "意識を失いました", "대량 출혈이에요", "심한 화상을 입었어요"
]

class SymptomTester:
    def __init__(self):
        self.results = []
        self.rag = GLOBAL_ADVANCED_RAG
        self.start_time = time.time()
        
    def test_single_symptom(self, symptom: str, index: int) -> Dict:
        """단일 증상 테스트"""
        print(f"\n🔍 [{index+1}/100] 테스트 중: '{symptom}'")
        
        result = {
            "index": index + 1,
            "symptom": symptom,
            "timestamp": datetime.now().isoformat(),
            "rag_search": None,
            "llm_advice": None,
            "rule_based_advice": None,
            "success": False,
            "error": None,
            "processing_time": 0
        }
        
        start_time = time.time()
        
        try:
            # 1. RAG 검색 테스트
            print("  📚 RAG 검색 중...")
            hits = self.rag.search(symptom, top_k=3, use_reranking=True)
            result["rag_search"] = {
                "found": len(hits) > 0,
                "count": len(hits),
                "top_titles": [hit[0][:100] + "..." if len(hit[0]) > 100 else hit[0] for hit in hits[:3]]
            }
            
            # 2. LLM 조언 생성 테스트
            print("  🤖 LLM 조언 생성 중...")
            rag_passages = [hit[0] for hit in hits[:3]] if hits else []
            llm_advice = generate_advice(symptom, [], rag_passages)
            result["llm_advice"] = {
                "generated": llm_advice is not None,
                "length": len(llm_advice) if llm_advice else 0,
                "preview": llm_advice[:200] + "..." if llm_advice and len(llm_advice) > 200 else llm_advice
            }
            
            # 3. 규칙 기반 조언 테스트
            print("  📋 규칙 기반 조언 생성 중...")
            from ui.app import simple_text_rules
            rule_result = simple_text_rules(symptom)
            result["rule_based_advice"] = {
                "advice": rule_result["advice"],
                "otc_count": len(rule_result["otc"]),
                "otc_list": rule_result["otc"]
            }
            
            # 4. 성공 여부 판단
            result["success"] = (
                result["rag_search"]["found"] and 
                result["llm_advice"]["generated"] and 
                len(result["llm_advice"]["preview"]) > 50
            )
            
            if result["success"]:
                print(f"  ✅ 성공! RAG: {result['rag_search']['count']}개, LLM: {result['llm_advice']['length']}자")
            else:
                print(f"  ⚠️ 부분 성공 - RAG: {result['rag_search']['found']}, LLM: {result['llm_advice']['generated']}")
                
        except Exception as e:
            result["error"] = str(e)
            print(f"  ❌ 오류: {e}")
            
        result["processing_time"] = time.time() - start_time
        return result
    
    def run_all_tests(self):
        """100가지 증상 전체 테스트 실행"""
        print("🚀 100가지 증상 종합 테스트 시작!")
        print("=" * 60)
        
        for i, symptom in enumerate(SYMPTOMS_100):
            result = self.test_single_symptom(symptom, i)
            self.results.append(result)
            
            # 진행률 표시
            if (i + 1) % 10 == 0:
                success_count = sum(1 for r in self.results if r["success"])
                print(f"\n📊 진행률: {i+1}/100 ({success_count}개 성공)")
                
            # 잠시 대기 (API 제한 방지)
            time.sleep(0.5)
        
        self.generate_report()
    
    def generate_report(self):
        """테스트 결과 리포트 생성"""
        total_time = time.time() - self.start_time
        success_count = sum(1 for r in self.results if r["success"])
        error_count = sum(1 for r in self.results if r["error"])
        
        print("\n" + "=" * 60)
        print("📊 100가지 증상 테스트 결과 리포트")
        print("=" * 60)
        
        print(f"⏱️ 총 소요 시간: {total_time:.2f}초")
        print(f"✅ 성공: {success_count}/100 ({success_count}%)")
        print(f"❌ 오류: {error_count}/100 ({error_count}%)")
        print(f"⚠️ 부분 성공: {100 - success_count - error_count}/100")
        
        # 카테고리별 성공률
        categories = {
            "발열": (0, 10),
            "두통": (10, 20),
            "복통": (20, 30),
            "호흡기": (30, 40),
            "피부": (40, 50),
            "외상": (50, 60),
            "벌레/곤충": (60, 70),
            "소화기": (70, 80),
            "신경계": (80, 90),
            "응급상황": (90, 100)
        }
        
        print("\n📈 카테고리별 성공률:")
        for category, (start, end) in categories.items():
            category_results = self.results[start:end]
            category_success = sum(1 for r in category_results if r["success"])
            print(f"  {category}: {category_success}/{end-start} ({category_success/(end-start)*100:.1f}%)")
        
        # 실패한 증상들
        failed_symptoms = [r for r in self.results if not r["success"]]
        if failed_symptoms:
            print(f"\n❌ 실패한 증상들 ({len(failed_symptoms)}개):")
            for r in failed_symptoms[:10]:  # 상위 10개만 표시
                print(f"  - {r['symptom']} (오류: {r['error'] or '부분성공'})")
        
        # 결과를 JSON 파일로 저장
        report_data = {
            "summary": {
                "total_tests": 100,
                "success_count": success_count,
                "error_count": error_count,
                "total_time": total_time,
                "timestamp": datetime.now().isoformat()
            },
            "results": self.results
        }
        
        with open("test_results_100_symptoms.json", "w", encoding="utf-8") as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 상세 결과가 'test_results_100_symptoms.json'에 저장되었습니다.")
        
        # 자동 크롤링 트리거
        if failed_symptoms:
            print(f"\n🔄 실패한 증상들에 대해 자동 크롤링을 시작합니다...")
            try:
                auto_crawl_unhandled_symptoms()
                print("✅ 자동 크롤링 완료!")
            except Exception as e:
                print(f"❌ 자동 크롤링 오류: {e}")

def main():
    """메인 실행 함수"""
    print("🧪 100가지 증상 종합 테스트 시스템")
    print("=" * 60)
    print("테스트 항목:")
    print("- LLM 기능 테스트")
    print("- RAG 검색 테스트")
    print("- 크롤링 자동화 테스트")
    print("- 전체 시스템 통합 테스트")
    print("=" * 60)
    
    # 환경 확인
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        return
    
    # 테스트 실행
    tester = SymptomTester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()
