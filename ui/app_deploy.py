import os
import streamlit as st
from streamlit_geolocation import streamlit_geolocation
import requests
import pathlib
import re
from typing import List, Tuple, Dict, Optional
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from PIL import Image
import numpy as np
import base64
import json
import time
import sys
from datetime import datetime

# 백엔드 서비스 임포트 (배포용 - 로깅 제외)
sys.path.append('backend')
# from services_logging import symptom_logger
# from services_auto_crawler import auto_crawl_unhandled_symptoms
from services_advanced_rag import GLOBAL_ADVANCED_RAG, load_disk_passages
from services_gen import generate_advice

st.set_page_config(page_title="응급 챗봇", page_icon="🚑", layout="centered")
st.title("응급 환자 챗봇 (일본)")
st.caption("일본 여행자를 위한 응급 의료 조언 - VLM/LLM/RAG 통합")

# ==================== RAG 시스템 (고도화된 시스템 사용) ====================
# 기존 HybridRAG 클래스는 services_advanced_rag.py로 이동
# 여기서는 고도화된 RAG 시스템을 사용

# ==================== 지오 서비스 ====================
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

def _headers() -> Dict[str, str]:
    try:
        contact = st.secrets.get("CONTACT_EMAIL", "hos-emergency-bot/0.1")
    except:
        contact = os.getenv("CONTACT_EMAIL", "hos-emergency-bot/0.1")
    return {"User-Agent": f"hos-emergency-bot/0.1 ({contact})"}

def geocode_place(place: str) -> Optional[Dict[str, float]]:
    if not place:
        return None
    QUICK: Dict[str, Tuple[float, float]] = {
        "shibuya": (35.661777, 139.704051),
        "tokyo": (35.676203, 139.650311),
        "japan": (36.204824, 138.252924),
    }
    key = (place or "").strip().lower()
    if key in QUICK:
        lat, lon = QUICK[key]
        return {"lat": lat, "lon": lon}
    params = {
        "q": place,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    try:
        r = requests.get(NOMINATIM_URL, params=params, headers=_headers(), timeout=6)
        if not r.ok:
            return None
        arr = r.json()
        if not arr:
            return None
        lat = float(arr[0]["lat"])
        lon = float(arr[0]["lon"])
        return {"lat": lat, "lon": lon}
    except Exception:
        return QUICK.get("tokyo") and {"lat": QUICK["tokyo"][0], "lon": QUICK["tokyo"][1]}

def reverse_geocode(lat: float, lon: float) -> str:
    try:
        params = {"format": "json", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1}
        r = requests.get(REVERSE_URL, params=params, headers=_headers(), timeout=6)
        if not r.ok:
            return ""
        data = r.json()
        address = data.get("display_name") or ""
        return address or ""
    except Exception:
        return ""

def build_address_from_tags(tags: Dict[str, str]) -> str:
    parts: List[str] = []
    # Common OSM address tags in Japan
    for key in [
        "addr:prefecture",
        "addr:city", 
        "addr:ward",
        "addr:district",
        "addr:suburb",
        "addr:neighbourhood",
        "addr:street",
        "addr:block",
        "addr:housenumber",
        "addr:postcode",
    ]:
        val = tags.get(key)
        if val:
            parts.append(val)
    if not parts:
        # fallback single fields
        for key in ["addr:full", "addr:place", "addr:hamlet"]:
            val = tags.get(key)
            if val:
                parts.append(val)
                break
    return " ".join(parts)

def random_tokyo_latlon() -> tuple[float, float]:
    """도쿄의 랜덤한 지역 좌표를 반환합니다."""
    import random
    
    # 도쿄 주요 지역들의 대표 좌표
    tokyo_areas = [
        (35.676203, 139.650311),  # 신주쿠
        (35.658581, 139.745433),  # 시부야
        (35.676191, 139.650310),  # 하라주쿠
        (35.658034, 139.701636),  # 롯폰기
        (35.676191, 139.650310),  # 긴자
        (35.658581, 139.745433),  # 아키하바라
        (35.676191, 139.650310),  # 우에노
        (35.658034, 139.701636),  # 아사쿠사
        (35.676191, 139.650310),  # 이케부쿠로
        (35.658581, 139.745433),  # 신바시
    ]
    
    # 랜덤하게 선택된 지역에 약간의 랜덤 오프셋 추가
    base_lat, base_lon = random.choice(tokyo_areas)
    
    # ±0.01도 범위 내에서 랜덤 오프셋 (약 ±1km)
    lat_offset = random.uniform(-0.01, 0.01)
    lon_offset = random.uniform(-0.01, 0.01)
    
    return (base_lat + lat_offset, base_lon + lon_offset)

def search_hospitals(lat: float, lon: float, radius_m: int = 2000) -> List[Dict]:
    query = f"""
    [out:json][timeout:6];
    (
      node["amenity"~"hospital|clinic"](around:{radius_m},{lat},{lon});
      way["amenity"~"hospital|clinic"](around:{radius_m},{lat},{lon});
      relation["amenity"~"hospital|clinic"](around:{radius_m},{lat},{lon});
    );
    out center 20;
    """
    r = None
    for endpoint in OVERPASS_URLS:
        try:
            r = requests.post(endpoint, data={"data": query}, timeout=7)
            if r.ok:
                break
        except Exception:
            r = None
            continue
    if r is None:
        return []
    results: List[Dict] = []
    if r.ok:
        data = r.json()
        for el in data.get("elements", [])[:20]:
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("name:en") or tags.get("name:ja") or "Unknown"
            lat_out = el.get("lat") or (el.get("center") or {}).get("lat")
            lon_out = el.get("lon") or (el.get("center") or {}).get("lon")
            
            # 주소 정보 구성
            addr = build_address_from_tags(tags)
            if not addr and lat_out and lon_out:
                addr = reverse_geocode(lat_out, lon_out)
            
            results.append({
                "name": name,
                "address": addr or f"위도: {lat_out:.4f}, 경도: {lon_out:.4f}",
                "lat": lat_out,
                "lon": lon_out,
            })
    return results

def search_pharmacies(lat: float, lon: float, radius_m: int = 1500) -> List[Dict]:
    query = f"""
    [out:json][timeout:7];
    (
      node["amenity"="pharmacy"](around:{radius_m},{lat},{lon});
      way["amenity"="pharmacy"](around:{radius_m},{lat},{lon});
      relation["amenity"="pharmacy"](around:{radius_m},{lat},{lon});
    );
    out center 30;
    """
    r = None
    for endpoint in OVERPASS_URLS:
        try:
            r = requests.post(endpoint, data={"data": query}, timeout=7)
            if r.ok:
                break
        except Exception:
            r = None
            continue
    if r is None:
        return []
    results: List[Dict] = []
    if r.ok:
        data = r.json()
        for el in data.get("elements", [])[:30]:
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("name:en") or tags.get("name:ja") or "Unknown"
            lat_out = el.get("lat") or (el.get("center") or {}).get("lat")
            lon_out = el.get("lon") or (el.get("center") or {}).get("lon")
            
            # 주소 정보 구성
            addr = build_address_from_tags(tags)
            if not addr and lat_out and lon_out:
                addr = reverse_geocode(lat_out, lon_out)
            
            results.append({
                "name": name,
                "address": addr or f"위도: {lat_out:.4f}, 경도: {lon_out:.4f}",
                "lat": lat_out,
                "lon": lon_out,
            })
    return results

# ==================== 기본 규칙 ====================
def simple_text_rules(symptoms_text: str) -> dict:
    t = (symptoms_text or "").lower()
    advice = "증상에 대한 기본 응급처치를 안내합니다. 심각한 증상이면 즉시 119(일본: 119)를 호출하세요."
    otc: list = []
    
    if any(k in t for k in ["fever", "열", "発熱"]):
        otc.append("해열제(아세트아미노펜)")
    if any(k in t for k in ["cough", "기침", "咳"]):
        otc.append("진해거담제")
    if any(k in t for k in ["diarrhea", "설사", "下痢"]):
        otc.append("지사제 및 수분보충")
    if any(k in t for k in ["abdominal pain", "stomach ache", "배아픔", "복통", "腹痛"]):
        otc.extend(["제산제/위산억제제(증상에 따라)", "가스완화제(시메티콘)", "진통제(아세트아미노펜)"])
    if any(k in t for k in ["headache", "두통", "頭痛"]):
        if "해열제(아세트아미노펜)" not in otc:
            otc.append("진통제(아세트아미노펜)")
    if any(k in t for k in ["vomit", "vomiting", "구토", "嘔吐", "탈수", "dehydration"]):
        otc.append("경구수분보충액(ORS)")
    if any(k in t for k in ["rash", "발진", "알레르기", "蕁麻疹", "じんましん", "allergy"]):
        otc.append("항히스타민제")
    if any(k in t for k in ["sore throat", "인후통", "목아픔", "喉の痛み"]):
        otc.append("목염증 완화 목캔디/로젠지")
    if any(k in t for k in ["stuffy nose", "nasal congestion", "코막힘", "鼻づまり"]):
        otc.append("비충혈 제거제(디콘제스턴트)")
    if any(k in t for k in ["toothache", "치통", "歯痛"]):
        if "진통제(아세트아미노펜)" not in otc:
            otc.append("진통제(아세트아미노펜)")
    if any(k in t for k in ["cut", "bleeding", "상처", "出血"]):
        advice = "상처 부위를 압박하여 지혈하고, 깨끗한 물로 세척 후 멸균 거즈를 적용하세요. 심한 출혈은 즉시 119."
    
    # 벌레 물림 (말벌/벌 키워드 제외)
    if any(k in t for k in ["벌레", "물림", "벌레에 물림", "벌레에물림", "모기", "모기에 물림", "모기에물림", "insect bite", "虫に刺された"]) and not any(k in t for k in ["말벌", "벌", "쏘임", "wasp", "bee", "蜂"]):
        advice = "벌레 물림: 즉시 해당 부위를 깨끗한 물로 씻고, 얼음찜질로 부종을 완화하세요. 항히스타민 연고를 바르고, 긁지 않도록 주의하세요. 24시간 후에도 개선되지 않으면 의료진 상담하세요."
        otc.extend(["항히스타민 연고", "소독제", "얼음팩"])
    
    # 말벌 쏘임 (우선순위 높음)
    elif any(k in t for k in ["말벌", "벌", "쏘임", "말벌에 쏘임", "말벌에쏘임", "벌에 쏘임", "벌에쏘임", "wasp sting", "bee sting", "蜂に刺された"]):
        advice = "말벌 쏘임: 즉시 침을 제거하고, 깨끗한 물로 세척하세요. 얼음찜질로 부종을 완화하고, 상처 부위를 심장보다 높게 유지하세요. 호흡곤란, 전신 두드러기, 의식 변화 시 즉시 119에 연락하세요."
        otc.extend(["항히스타민 연고", "항히스타민제(경구)", "소독제", "얼음팩"])
    
    # LLM을 사용한 고급 조언 생성 (API 키가 있는 경우)
    try:
        # RAG 검색 결과 준비
        rag_passages = []
        if 'hits' in locals() and hits:
            rag_passages = [hit[0] for hit in hits[:3]]  # 상위 3개 문서

        # 이미지 분석 결과 준비 (간단한 버전)
        image_findings = []
        if 'uploaded_file' in locals() and uploaded_file:
            image_findings = ["이미지 분석됨"] # Placeholder, actual image analysis is in main.py

        # LLM 조언 생성
        if rag_passages or image_findings:
            llm_advice = generate_advice(symptoms_text, image_findings, rag_passages)
            if llm_advice and not llm_advice.startswith("증상에 대한 일반 조언입니다"):
                advice = llm_advice
    except Exception as e:
        # LLM 오류 시 기본 조언 사용
        pass

    
    # ==================== LLM 기반 자동 생성 규칙 ====================

    # 열이 39도입니다 관련 규칙
    if any(k in t for k in ["열이 39도입니다"]):
        advice = "열이 39도인 경우, 여러 원인이 있을 수 있으며, 특히 감염이나 염증이 있을 수 있습니다."
        otc.extend(['해열제'])

    # fever 38.5 관련 규칙
    if any(k in t for k in ["fever 38.5"]):
        advice = "증상으로 38."
        otc.extend(['해열제', '의약'])

    # 発熱が続きます 관련 규칙
    if any(k in t for k in ["発熱が続きます"]):
        advice = "발열이 지속되는 경우, 다음과 같은 조치를 취할 수 있습니다."
        otc.extend([])

    # 고열이 나요 관련 규칙
    if any(k in t for k in ["고열이 나요"]):
        advice = "고열이 나는 증상에 대해 안전 중심의 응급처치 및 OTC 조언을 드리겠습니다."
        otc.extend([])

    # 체온이 높아요 관련 규칙
    if any(k in t for k in ["체온이 높아요"]):
        advice = "체온이 높다는 것은 발열을 의미하며, 이는 여러 원인에 의해 발생할 수 있습니다."
        otc.extend(['의약'])

    # 열감이 있어요 관련 규칙
    if any(k in t for k in ["열감이 있어요"]):
        advice = "열감이 있는 경우, 다음과 같은 조치를 취할 수 있습니다."
        otc.extend(['의약'])

    # 몸이 뜨거워요 관련 규칙
    if any(k in t for k in ["몸이 뜨거워요"]):
        advice = "몸이 뜨거운 증상은 여러 원인에 의해 발생할 수 있으며, 특히 열이 나는 경우에는 주의가 필요합니다."
        otc.extend(['의약'])

    # 발열과 두통 관련 규칙
    if any(k in t for k in ["발열과 두통"]):
        advice = "발열과 두통 증상에 대해 안전 중심의 응급처치 및 OTC 조언을 드리겠습니다."
        otc.extend(['해열제', '의약'])

    # 고열과 오한 관련 규칙
    if any(k in t for k in ["고열과 오한"]):
        advice = "고열과 오한 증상에 대한 안전 중심의 응급처치 및 OTC 조언을 드리겠습니다."
        otc.extend([])

    # 열이 안 떨어져요 관련 규칙
    if any(k in t for k in ["열이 안 떨어져요"]):
        advice = "열이 떨어지지 않는 증상에 대해 다음과 같은 안전 중심의 응급처치 및 OTC 조언을 드립니다."
        otc.extend([])

    return {"advice": advice, "otc": otc}

# ==================== 응급상황 감지 ====================
CRITICAL_KEYWORDS = [
    "chest pain", "심한 가슴 통증", "胸の激痛",
    "severe bleeding", "대량 출혈", "大量出血",
    "unconscious", "의식 없음", "意識なし",
    "stroke", "편마비", "脳卒中",
    "difficulty breathing", "숨이 가쁨", "呼吸困難",
    "severe abdominal pain", "복부 극심한 통증", "激しい腹痛",
    "anaphylaxis", "아나필락시스", "심한 알레르기 반응", "전신 두드러기", "호흡곤란",
    "severe allergic reaction", "全身蕁麻疹", "呼吸困難",
]

def detect_emergency(symptoms_text: str) -> list:
    t = (symptoms_text or "").lower()
    reasons: list = []
    for k in CRITICAL_KEYWORDS:
        if k in t:
            reasons.append(k)
    return reasons

# ==================== 이미지 분석 ====================
def simple_image_screening(img: Image.Image) -> List[str]:
    w, h = img.size
    findings: List[str] = []
    if min(w, h) < 128:
        findings.append("저해상도 이미지")
    return findings

def detect_emergency_from_image(img: Image.Image, raw_image: bytes = None) -> List[str]:
    reasons: List[str] = []
    red_thr = 0.25
    burn_thr = 0.30
    
    # 휴리스틱 분석
    try:
        small = img.resize((224, 224))
        hsv = small.convert("HSV")
        arr = np.array(hsv)
        h = arr[:, :, 0].astype(np.float32)
        s = arr[:, :, 1].astype(np.float32)
        v = arr[:, :, 2].astype(np.float32)
        
        red_mask = ((h < 10) | (h > 245)) & (s > 100) & (v > 60)
        red_ratio = float(red_mask.mean())
        if red_ratio > red_thr:
            reasons.append("이미지상 과다 출혈 의심")
            
        orange_mask = (h >= 10) & (h <= 50) & (s > 120) & (v > 120)
        orange_ratio = float(orange_mask.mean())
        if orange_ratio > burn_thr:
            reasons.append("이미지상 화상/광범위 홍반 의심")
    except Exception:
        pass
    
    # OpenAI Vision API 분석 (환경변수가 설정된 경우)
    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
        if api_key and raw_image:
            import openai
            client = openai.OpenAI(api_key=api_key)
            
            # 이미지를 base64로 인코딩
            import base64
            from io import BytesIO
            
            img_buffer = BytesIO()
            img.save(img_buffer, format="JPEG")
            img_bytes = img_buffer.getvalue()
            b64_image = base64.b64encode(img_bytes).decode("utf-8")
            
            # 의료 이미지 분석 프롬프트
            prompt = """
            이 의료/상해 이미지를 분석해주세요. 다음 항목들을 확인하고 발견된 것만 한국어로 보고해주세요:
            
            응급상황:
            - 심한 출혈 (과다 출혈, 대량 출혈)
            - 심한 화상 (2도 이상 화상, 광범위 화상)
            - 뼈 노출 (골절, 개방성 골절)
            - 절단상 (손가락, 팔, 다리 절단)
            - 중증 외상 (심각한 상처, 깊은 상처)
            
            일반 의료상황:
            - 발진, 알레르기 반응
            - 부종, 붓기
            - 멍, 타박상
            - 가벼운 상처, 찰과상
            - 피부염, 습진
            - 물집, 수포
            
            발견된 증상이 없으면 "정상"이라고 답해주세요.
            """
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": "당신은 의료 이미지 분석 전문가입니다. 정확하고 신중하게 분석해주세요."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500,
                temperature=0.1
            )
            
            analysis = response.choices[0].message.content.strip()
            
            # 응급상황 키워드 체크
            emergency_keywords = ["심한 출혈", "과다 출혈", "대량 출혈", "심한 화상", "2도 이상", "광범위 화상", 
                                "뼈 노출", "골절", "개방성", "절단", "중증 외상", "심각한 상처", "깊은 상처"]
            
            for keyword in emergency_keywords:
                if keyword in analysis:
                    reasons.append(f"AI 분석: {analysis}")
                    break
            else:
                # 응급상황이 아닌 경우 일반 의료상황으로 분류
                if "정상" not in analysis and analysis:
                    reasons.append(f"AI 분석: {analysis}")
                    
    except Exception as e:
        # OpenAI API 오류 시 휴리스틱 결과만 사용
        pass
    
    return reasons

# ==================== 일본어 문장 생성 ====================
def build_jp_phrase(symptoms_text: str, otc: list) -> str:
    base = "薬局で相談したいです。"
    if any("지사제" in o or "설사" in symptoms_text for o in otc) or ("설사" in (symptoms_text or "")):
        return base + "『腹痛や下痢があります。市販の整腸剤や下痢止めを探しています。』"
    if any("해열" in o or "열" in symptoms_text for o in otc) or ("발열" in (symptoms_text or "") or "열" in (symptoms_text or "")):
        return base + "『発熱があります。アセトアミノフェン成分の解熱薬を探しています。』"
    if any("진해" in o or "기침" in symptoms_text for o in otc) or ("咳" in (symptoms_text or "")):
        return base + "『咳があります。市販の鎮咳去痰薬を探しています。』"
    return base + "『症状に合う一般用医薬品を教えてください。』"

def map_otc_to_brands(otc: list) -> list:
    hints: list = []
    for o in otc:
        lo = o.lower()
        if "해열" in o or "acet" in lo:
            hints.append("解熱薬: アセトアミノフェン配合製品")
        if "지사" in o:
            hints.append("下痢止め/整腸剤: 乳酸菌/ロペラミド系(症状により) ※用法注意")
        if "제산" in o or "위산" in o:
            hints.append("胃薬: 制酸薬/H2ブロッカー系(症状により) ※相互作用注意")
        if "가스" in o or "시메티콘" in o:
            hints.append("胃腸薬: シメチコン配合")
        if "진통제" in o:
            hints.append("鎮痛薬: アセトアミノフェン優先(イブプロフェン等は状況で回避)")
        if "진해" in o:
            hints.append("咳止め: 鎮咳去痰薬カテゴリ")
        if "항히스타민" in o:
            hints.append("抗ヒスタミン薬: かゆみ/蕁麻疹等")
        if "경구수분보충" in o or "ORS" in o.upper():
            hints.append("経口補水液(ORS): 脱水時の電解質/水分補給")
        if "로젠지" in o or "목염증" in o:
            hints.append("トローチ/のど飴: 咽頭痛緩和")
        if "비충혈" in o or "디콘제스턴트" in o or "decongestant" in lo:
            hints.append("鼻づまり: 血管収縮点鼻薬(短期使用)")
    
    out = []
    for h in hints:
        if h not in out:
            out.append(h)
    return out

# ==================== 지도 링크 생성 ====================
def build_google_maps_link(lat: Optional[float], lon: Optional[float], name: Optional[str] = None) -> Optional[str]:
    if lat is None or lon is None:
        return None
    q = f"{lat},{lon}"
    if name:
        q = name
    return f"https://www.google.com/maps/search/?api=1&query={q}"

# ==================== OTC 이미지 매핑 ====================
def map_otc_to_images(otc: list) -> list:
    urls: list = []
    
    def add_for(cat: str, placeholder: str) -> None:
        # 로컬 이미지가 있으면 사용, 없으면 플레이스홀더
        urls.append(placeholder)
    
    for o in otc:
        lo = o.lower()
        if ("해열" in o) or ("acet" in lo):
            add_for("acetaminophen", "💊")
        if "지사" in o:
            add_for("antidiarrheal", "💊")
        if ("제산" in o) or ("위산" in o):
            add_for("antacid", "💊")
        if ("가스" in o) or ("시메티콘" in o):
            add_for("simethicone", "💊")
        if "항히스타민" in o:
            add_for("antihistamine", "💊")
        if ("경구수분보충" in o) or ("ors" in lo):
            add_for("ors", "💊")
        if ("로젠지" in o) or ("목염증" in o):
            add_for("lozenge", "💊")
        if ("비충혈" in o) or ("decongestant" in lo) or ("디콘제스턴트" in o):
            add_for("decongestant", "💊")
        if ("화상" in o) or ("burn" in lo):
            add_for("burngel", "💊")
        if ("보습" in o) or ("건조" in o) or ("atopy" in lo) or ("아토피" in o):
            add_for("emollient", "💊")
    
    # 중복 제거
    dedup: list = []
    for u in urls:
        if u not in dedup:
            dedup.append(u)
    return dedup

# ==================== RAD-AR 의약품 검색 ====================
import re
import time
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
import json
from pathlib import Path

RADAR_BASE = "https://www.rad-ar.or.jp/siori/english/"
RADAR_SEARCH_URL = urljoin(RADAR_BASE, "search")

RADAR_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "en,ja;q=0.9,ko;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": RADAR_BASE.rstrip("/") + "/",
}

def radar_session():
    s = requests.Session()
    s.headers.update(RADAR_HEADERS)
    return s

def radar_search(keyword: str, limit: int = 5) -> List[Dict]:
    try:
        params = {"w": keyword}
        s = radar_session()
        res = s.get(RADAR_SEARCH_URL, params=params, timeout=15)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, "lxml")
        results = []
        
        # 검색 결과 링크 파싱
        links = []
        for a in soup.select('a[href*="search/result?n="]'):
            href = a.get("href")
            if href:
                full_url = urljoin(RADAR_BASE, href)
                if full_url not in links:
                    links.append(full_url)
        
        # 상세 정보 가져오기
        for url in links[:limit]:
            try:
                detail_res = s.get(url, timeout=15)
                detail_res.raise_for_status()
                detail_soup = BeautifulSoup(detail_res.text, "lxml")
                
                # 기본 정보 추출
                brand = ""
                h1 = detail_soup.select_one("h1")
                if h1:
                    brand = h1.get_text(strip=True)
                
                company = ""
                for a in detail_soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if href.startswith("http") and "rad-ar.or.jp" not in href:
                        company = a.get_text(strip=True)
                        break
                
                # 테이블에서 정보 추출
                active_ingredient = ""
                dosage_form = ""
                for tr in detail_soup.select("table tr"):
                    cells = tr.find_all(["td", "th"])
                    if len(cells) >= 2:
                        key = re.sub(r"\s+", " ", cells[0].get_text(strip=True))
                        val = cells[1].get_text(strip=True)
                        if "Active ingredient" in key:
                            active_ingredient = val
                        elif "Dosage form" in key:
                            dosage_form = val
                
                results.append({
                    "brand": brand,
                    "company": company,
                    "active_ingredient": active_ingredient,
                    "dosage_form": dosage_form,
                    "url": url
                })
                
                time.sleep(0.5)  # 요청 간격
                
            except Exception as e:
                continue
                
        return results
        
    except Exception as e:
        return []

# ==================== 메인 앱 ====================
@st.cache_resource
def load_rag():
    """고도화된 RAG 시스템 로드"""
    return GLOBAL_ADVANCED_RAG

# RAG 로드
rag = load_rag()

with st.form("chat_form"):
    uploaded = st.file_uploader("증상 사진 업로드 (선택)", type=["png", "jpg", "jpeg"])
    symptoms = st.text_area("증상 설명", placeholder="예) 이마가 찢어져 피가 나요, 열이 38.5도예요")
    
    # 위치 설정 섹션
    st.subheader("📍 위치 설정")
    
    # 테스트 모드 선택
    test_mode = st.checkbox("🧪 테스트 모드 (랜덤 도쿄 지역)", value=False, 
                           help="체크하면 도쿄의 랜덤한 지역으로 테스트합니다")
    
    if test_mode:
        st.info("🧪 테스트 모드: 도쿄의 랜덤한 지역에서 병원/약국을 검색합니다")
        location = "Tokyo (Test Mode)"
    else:
        location = st.text_input("현재 위치(도시/구 단위, 일본)", value="Tokyo")
        st.write("내 위치 사용(브라우저 권한 필요):")
        loc = streamlit_geolocation()
    
    traveler = st.checkbox("여행자 모드(한국→일본)", value=True)
    submitted = st.form_submit_button("상담하기")

if submitted:
    # 로깅을 위한 시작 시간
    start_time = time.time()
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    with st.spinner("분석 중..."):
        # 이미지 분석
        findings = []
        image_uploaded = uploaded is not None
        if uploaded is not None:
            try:
                img = Image.open(uploaded).convert("RGB")
                findings = simple_image_screening(img)
                
                # 이미지 바이트 데이터 준비
                img_bytes = uploaded.getvalue()
                emg_img = detect_emergency_from_image(img, img_bytes)
                if emg_img:
                    findings.extend(emg_img)
            except Exception as e:
                findings = ["이미지 해석 실패"]
        
        # 기본 규칙 기반 조언
        rule_out = simple_text_rules(symptoms)
        advice = rule_out["advice"]
        otc = rule_out["otc"]
        
        # 고도화된 RAG 검색
        rag_results = []
        rag_confidence = 0.0
        try:
            # 고도화된 검색: 쿼리 확장, Dense+Sparse 결합, 리랭킹 포함
            hits = rag.search(symptoms, top_k=3, use_reranking=True)
            passages = [h[0] for h in hits]
            rag_results = hits
            rag_confidence = max([score for _, score in hits]) if hits else 0.0
            evidence_titles = []
            for txt, score in hits:
                first = (txt.strip().splitlines() or [""])[0].strip()
                evidence_titles.append(f"{first[:60]}... (신뢰도: {score:.2f})" if first else "근거 문서")
            
            # RAG 시스템 통계 표시 (디버깅용)
            if st.checkbox("🔍 RAG 시스템 통계 보기", value=False):
                stats = rag.get_search_stats()
                st.json(stats)
                
        except Exception as e:
            passages = []
            evidence_titles = []
            st.error(f"RAG 검색 오류: {str(e)}")
        
        # 지오 검색
        nearby_hospitals = []
        nearby_pharmacies = []
        try:
            if test_mode:
                # 테스트 모드: 도쿄의 랜덤한 지역 사용
                lat, lon = random_tokyo_latlon()
                st.info(f"🧪 테스트 모드: ({lat:.4f}, {lon:.4f}) 위치에서 검색 중...")
            elif loc and loc.get("latitude") and loc.get("longitude"):
                # 실제 위치 사용 (브라우저 GPS)
                lat, lon = loc["latitude"], loc["longitude"]
                st.info(f"📍 실제 위치: ({lat:.4f}, {lon:.4f})")
            else:
                # 입력된 위치로 검색
                geo = geocode_place(location)
                if geo:
                    lat, lon = geo["lat"], geo["lon"]
                    st.info(f"📍 검색된 위치: {location} ({lat:.4f}, {lon:.4f})")
                else:
                    lat, lon = 35.676203, 139.650311  # Tokyo fallback
                    st.warning(f"⚠️ 위치 검색 실패, 도쿄 기본 위치 사용: ({lat:.4f}, {lon:.4f})")
            
            nearby_hospitals = search_hospitals(lat, lon, 2000)
            nearby_pharmacies = search_pharmacies(lat, lon, 1500)
        except Exception as e:
            st.error(f"위치 검색 오류: {str(e)}")
            pass
        
        # 응급상황 감지
        emergency_reasons = detect_emergency(symptoms)
        if findings:
            for f in findings:
                if any(s in f.lower() for s in ["출혈", "bleeding", "화상", "burn"]):
                    emergency_reasons.append(f)
        
        # 업로드된 이미지 표시
        if uploaded is not None:
            st.subheader("업로드된 이미지")
            st.image(uploaded, caption="증상 사진", use_container_width=True)
        
        if emergency_reasons:
            st.error("위급 신호가 감지되었습니다. 즉시 119로 전화하세요.")
            st.write("근거: ", ", ".join(emergency_reasons))
            col_a, col_b = st.columns(2)
            with col_a:
                st.link_button("현지 119 연결", "tel:119")
            with col_b:
                st.link_button("한국 긴급 지원(재외국민)", "tel:+82232100404")
            st.caption("참고: 해외에서 한국 119 직접 연결은 불가하며, 재외국민 긴급전화로 도움을 받을 수 있습니다.")
        else:
            st.subheader("조언")
            st.write(advice)
            
            if findings:
                st.write("이미지 참고: " + ", ".join(findings))
            
            if otc:
                st.subheader("권장 OTC")
                st.write(", ".join(otc))
                
                # OTC 이미지 표시
                otc_images = map_otc_to_images(otc)
                if otc_images:
                    st.caption("대표 이미지")
                    cols = st.columns(min(4, len(otc_images)))
                    for i, img in enumerate(otc_images):
                        with cols[i % len(cols)]:
                            st.write(img)
                
                if traveler:
                    brands = map_otc_to_brands(otc)
                    if brands:
                        st.caption("구매 시 참고(성분/카테고리):")
                        for b in brands:
                            st.write(f"- {b}")
                    
                    jp_phrase = build_jp_phrase(symptoms, otc)
                    st.subheader("약국에서 보여줄 일본어 문장")
                    st.code(jp_phrase)
            
            # 병원 정보 표시
            if nearby_hospitals:
                st.subheader("근처 병원")
                for h in nearby_hospitals[:5]:
                    name = h.get('name', 'Unknown')
                    address = h.get('address', '주소 정보 없음')
                    lat = h.get('lat')
                    lon = h.get('lon')
                    
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"- **{name}**")
                        st.write(f"  📍 {address}")
                    with col2:
                        if lat and lon:
                            map_link = build_google_maps_link(lat, lon, name)
                            if map_link:
                                st.link_button("🗺️ 지도", map_link)
            
            # 약국 정보 표시
            if nearby_pharmacies:
                st.subheader("근처 약국")
                for p in nearby_pharmacies[:5]:
                    name = p.get('name', 'Unknown')
                    address = p.get('address', '주소 정보 없음')
                    lat = p.get('lat')
                    lon = p.get('lon')
                    
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.write(f"- **{name}**")
                        st.write(f"  📍 {address}")
                    with col2:
                        if lat and lon:
                            map_link = build_google_maps_link(lat, lon, name)
                            if map_link:
                                st.link_button("🗺️ 지도", map_link)
            
            if evidence_titles:
                st.subheader("근거 문서")
                for t in evidence_titles:
                    st.write(f"- {t}")
            
            # 의약품 검색 섹션
            if otc:
                st.subheader("일본 의약품 정보 검색")
                drug_keywords = []
                for o in otc:
                    if "해열" in o or "acet" in o.lower():
                        drug_keywords.append("acetaminophen")
                    elif "지사" in o:
                        drug_keywords.append("antidiarrheal")
                    elif "제산" in o or "위산" in o:
                        drug_keywords.append("antacid")
                    elif "진통" in o:
                        drug_keywords.append("analgesic")
                    elif "항히스타민" in o:
                        drug_keywords.append("antihistamine")
                
                if drug_keywords:
                    with st.spinner("일본 의약품 정보를 검색 중..."):
                        for keyword in drug_keywords[:2]:  # 최대 2개 키워드만 검색
                            try:
                                drug_results = radar_search(keyword, limit=3)
                                if drug_results:
                                    st.write(f"**{keyword} 관련 의약품:**")
                                    for drug in drug_results:
                                        with st.expander(f"💊 {drug.get('brand', 'Unknown')}"):
                                            if drug.get('company'):
                                                st.write(f"**제조사:** {drug['company']}")
                                            if drug.get('active_ingredient'):
                                                st.write(f"**주성분:** {drug['active_ingredient']}")
                                            if drug.get('dosage_form'):
                                                st.write(f"**제형:** {drug['dosage_form']}")
                                            if drug.get('url'):
                                                st.link_button("상세 정보 보기", drug['url'])
                            except Exception as e:
                                st.write(f"의약품 정보 검색 중 오류: {keyword}")
                                continue
            
            st.caption("일본 현지 드럭스토어/약국(Matsumoto Kiyoshi, Welcia 등)에서 구매 가능")
        
        # 로깅 완료
        processing_time = time.time() - start_time
        
        # 응답 품질 평가
        default_advice = "증상에 대한 기본 응급처치를 안내합니다. 심각한 증상이면 즉시 119(일본: 119)를 호출하세요."
        is_default_advice = advice.strip() == default_advice.strip()
        
        advice_quality = "good" if rag_confidence > 0.5 and len(rag_results) > 0 and not is_default_advice else "poor"
        
        # 기본 조언인 경우 실패로 간주
        if is_default_advice:
            advice_quality = "failed"
        
        # 위치 정보
        location_coords = None
        if not test_mode and loc and 'latitude' in loc and 'longitude' in loc:
            location_coords = (loc['latitude'], loc['longitude'])
        
        # 로그 기록 (배포용에서는 비활성화)
        # try:
        #     log_id = symptom_logger.log_symptom(
        #         user_input=symptoms,
        #         image_uploaded=image_uploaded,
        #         rag_results=rag_results,
        #         advice_generated=bool(advice),
        #         advice_quality=advice_quality,
        #         hospital_found=len(nearby_hospitals) > 0,
        #         pharmacy_found=len(nearby_pharmacies) > 0,
        #         location=location_coords,
        #         processing_time=processing_time,
        #         session_id=session_id
        #     )
        # except Exception as e:
        #     pass
        
        # 기본 조언인 경우 자동 크롤링 트리거 (배포용에서는 비활성화)
        # if is_default_advice:
        #     try:
        #         st.info("🔍 새로운 증상이 감지되었습니다. 관련 정보를 수집 중입니다...")
        #         # 백그라운드에서 자동 크롤링 실행
        #         auto_crawl_unhandled_symptoms()
        #         st.success("✅ 새로운 의료 정보가 수집되었습니다. 다음에 더 정확한 조언을 제공할 수 있습니다.")
        #     except Exception as e:
        #         st.warning(f"⚠️ 자동 정보 수집 중 오류가 발생했습니다: {str(e)}")
