#!/usr/bin/env python3
"""
새로운 규칙을 시스템에 통합하는 스크립트
- LLM 생성 데이터를 규칙으로 변환
- ui/app.py의 simple_text_rules 함수 업데이트
"""

import json
import re
from typing import List, Dict

def load_new_rules():
    """새로운 규칙 로드"""
    with open("new_rules.json", "r", encoding="utf-8") as f:
        return json.load(f)

def generate_rule_code(new_rules: List[Dict]) -> str:
    """새로운 규칙 코드 생성"""
    rule_code = "\n    # ==================== LLM 기반 자동 생성 규칙 ====================\n"
    
    for i, rule in enumerate(new_rules[:20]):  # 상위 20개만
        keywords = rule['keywords']
        advice = rule['advice']
        otc = rule['otc']
        symptom = rule['symptom']
        
        # 키워드 리스트 생성
        keyword_list = []
        for keyword in keywords:
            if keyword not in ['한국어', '영어', '일본어', '증상', 'symptom', '症状']:
                keyword_list.append(f'"{keyword}"')
        
        if not keyword_list:
            continue
            
        # 규칙 코드 생성
        rule_code += f"""
    # {symptom} 관련 규칙
    if any(k in t for k in [{', '.join(keyword_list)}]):
        advice = "{advice}"
        otc.extend({otc})
"""
    
    return rule_code

def update_app_py():
    """ui/app.py 업데이트"""
    print("🔧 ui/app.py 업데이트 중...")
    
    # 새로운 규칙 로드
    new_rules = load_new_rules()
    print(f"📋 새로운 규칙 {len(new_rules)}개 로드됨")
    
    # 규칙 코드 생성
    rule_code = generate_rule_code(new_rules)
    
    # ui/app.py 읽기
    with open("ui/app.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # simple_text_rules 함수 찾기
    pattern = r'(def simple_text_rules\(symptoms_text: str\) -> dict:.*?return \{"advice": advice, "otc": otc\})'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        old_function = match.group(1)
        
        # 새로운 규칙 추가
        new_function = old_function.replace(
            'return {"advice": advice, "otc": otc}',
            f'{rule_code}\n    return {{"advice": advice, "otc": otc}}'
        )
        
        # 파일 업데이트
        new_content = content.replace(old_function, new_function)
        
        with open("ui/app.py", "w", encoding="utf-8") as f:
            f.write(new_content)
        
        print("✅ ui/app.py 업데이트 완료!")
    else:
        print("❌ simple_text_rules 함수를 찾을 수 없습니다.")

def main():
    """메인 실행 함수"""
    print("🔧 새로운 규칙 통합 시스템")
    print("=" * 50)
    
    update_app_py()
    
    print("\n✅ 통합 완료!")

if __name__ == "__main__":
    main()
