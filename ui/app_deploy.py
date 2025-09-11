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
# sys.path.append('backend')
# from services_logging import symptom_logger

st.set_page_config(page_title="응급 챗봇", page_icon="🚑", layout="centered")
st.title("응급 환자 챗봇 (일본)")
st.caption("일본 여행자를 위한 응급 의료 조언 - VLM/LLM/RAG 통합")

# ==================== RAG 시스템 ====================
class HybridRAG:
    def __init__(self, passages: List[str]):
        self.passages = passages
        self.tokenized = [self._tokenize(p) for p in passages]
        self.bm25 = BM25Okapi(self.tokenized)
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=8000)
        self.tfidf = self.vectorizer.fit_transform(passages)

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r'\b\w+\b', text.lower())
        return tokens

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        if not query:
            return []
        q_tokens = self._tokenize(query)
        bm_scores = self.bm25.get_scores(q_tokens)
        q_vec = self.vectorizer.transform([query])
        tf_scores = cosine_similarity(q_vec, self.tfidf)[0]
        scores = [(i, 0.6 * bm_scores[i] + 0.4 * tf_scores[i]) for i in range(len(self.passages))]
        scores.sort(key=lambda x: x[1], reverse=True)
        idxs = [i for i, _ in scores[:top_k]]
        return [(self.passages[i], float(scores[j][1])) for j, i in enumerate(idxs)]

def load_disk_passages() -> list[str]:
    root = pathlib.Path(__file__).resolve().parents[1]
    pdir = root / "data" / "passages" / "jp"
    if not pdir.exists():
        return []
    out = []
    for p in sorted(pdir.glob("*.txt")):
        try:
            out.append(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return out

DEFAULT_PASSAGES = [
    "熱があるときはぬるま湯で体を冷やし、水分を十分にとりましょう。アセトアミノフェンは比較的安全です。",
    "出血している傷は直接圧迫で止血し、きれいな水で洗浄後、滅菌ガーゼを当ててください。",
    "下痢のときは水分・電解質の補給を行ってください。症状が重い場合は受診してください。",
    "벌레 물림이나 말벌 쏘임의 경우, 즉시 해당 부위를 깨끗한 물로 씻고, 얼음팩으로 부기를 줄이세요. 알레르기 반응이 있으면 즉시 의료진에게 연락하세요.",
    "응급상황에서는 즉시 119에 연락하고, 환자를 안전한 곳으로 이동시키세요. 의식이 없으면 심폐소생술을 시도하세요."
]

_disk = load_disk_passages()
rag = HybridRAG(_disk if _disk else DEFAULT_PASSAGES)

# ==================== 기본 규칙 ====================
def simple_text_rules(symptoms: str) -> Dict[str, any]:
    symptoms_lower = symptoms.lower()
    
    # 응급상황 키워드
    emergency_keywords = [
        "의식없", "의식 없", "호흡곤란", "호흡 곤란", "심한출혈", "심한 출혈",
        "가슴통증", "가슴 통증", "심한복통", "심한 복통", "경련", "발작",
        "화상", "중독", "질식", "쇼크", "심정지", "심장마비"
    ]
    
    # 벌레 물림 키워드
    insect_bite_keywords = [
        "벌레", "물림", "벌레물림", "벌레에물림", "벌레에 물림",
        "insect", "bite", "bug bite"
    ]
    
    # 말벌 쏘임 키워드
    wasp_sting_keywords = [
        "말벌", "쏘임", "말벌쏘임", "말벌에쏘임", "말벌에 쏘임", "벌", "벌에쏘임", "벌에 쏘임",
        "wasp", "sting", "wasp sting", "bee", "bee sting"
    ]
    
    advice = "조언 증상에 대한 기본 응급처치를 안내합니다. 심각한 증상이면 즉시 119(일본: 119)를 호출하세요."
    otc = []
    
    # 응급상황 체크
    if any(keyword in symptoms_lower for keyword in emergency_keywords):
        advice = "🚨 응급상황입니다! 즉시 119에 연락하고 응급실로 가세요."
        return {"advice": advice, "otc": [], "emergency": True}
    
    # 벌레 물림 특별 처리 (말벌/벌 키워드 제외)
    if any(keyword in symptoms_lower for keyword in insect_bite_keywords) and not any(keyword in symptoms_lower for keyword in wasp_sting_keywords):
        advice = """벌레 물림 응급처치:
1. 즉시 해당 부위를 깨끗한 물로 씻으세요
2. 얼음팩이나 차가운 물수건으로 부기를 줄이세요
3. 항히스타민 연고나 크림을 바르세요
4. 긁지 않도록 주의하세요 (감염 위험)
5. 24시간 후에도 개선되지 않으면 의료진 상담하세요"""
        otc = ["항히스타민 연고", "소독약", "얼음팩"]
        return {"advice": advice, "otc": otc, "emergency": False}
    
    # 말벌 쏘임 특별 처리 (우선순위 높음)
    elif any(keyword in symptoms_lower for keyword in wasp_sting_keywords):
        advice = """말벌 쏘임 응급처치:
1. 즉시 침을 제거하세요 (핀셋이나 신용카드 가장자리 사용)
2. 상처 부위를 깨끗한 물로 씻으세요
3. 얼음팩이나 차가운 물수건으로 부기를 줄이세요
4. 상처 부위를 심장보다 높게 유지하세요
5. 알레르기 반응(호흡곤란, 두드러기, 현기증)이 있으면 즉시 119에 연락"""
        otc = ["항히스타민 연고", "항히스타민제", "소독약", "얼음팩"]
        return {"advice": advice, "otc": otc, "emergency": False}
    
    # 일반 증상별 조언
    if "복통" in symptoms_lower or "배아픔" in symptoms_lower:
        advice = "복통이 있으면 금식하고 따뜻한 물을 조금씩 마시세요. 심한 통증이면 병원을 방문하세요."
        otc = ["제산제", "진통제"]
    elif "두통" in symptoms_lower or "머리아픔" in symptoms_lower:
        advice = "두통이 있으면 조용한 곳에서 휴식을 취하고 충분한 수분을 섭취하세요."
        otc = ["해열진통제"]
    elif "감기" in symptoms_lower or "기침" in symptoms_lower:
        advice = "감기 증상이 있으면 충분한 휴식과 수분 섭취를 하세요."
        otc = ["해열제", "기침약"]
    elif "화상" in symptoms_lower:
        advice = "화상 부위를 차가운 물에 15-20분간 담그세요. 심한 화상이면 병원을 방문하세요."
        otc = ["화상 연고", "소독약"]
    
    return {"advice": advice, "otc": otc, "emergency": False}

# ==================== 이미지 분석 ====================
def simple_image_screening(img: Image.Image) -> List[str]:
    img_array = np.array(img)
    
    # 휴식 분석
    red_ratio = np.mean(img_array[:, :, 0]) / 255.0
    green_ratio = np.mean(img_array[:, :, 1]) / 255.0
    blue_ratio = np.mean(img_array[:, :, 2]) / 255.0
    
    findings = []
    
    # 빨간색 비율이 높으면 출혈 가능성
    red_threshold = float(os.getenv("IMG_RED_RATIO", "0.3"))
    if red_ratio > red_threshold:
        findings.append("출혈 가능성")
    
    # 화상 분석 (빨간색과 갈색)
    burn_threshold = float(os.getenv("IMG_BURN_RATIO", "0.2"))
    if red_ratio > burn_threshold and green_ratio < 0.3:
        findings.append("화상 가능성")
    
    # OpenAI Vision API 분석 (환경변수가 설정된 경우)
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if openai_api_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_api_key)
            
            # 이미지를 base64로 인코딩
            img_buffer = img.tobytes()
            img_base64 = base64.b64encode(img_buffer).decode()
            
            # 의료 이미지 분석 프롬프트
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": """이 의료/상해 이미지를 분석해주세요. 다음 항목들을 확인하고 발견된 것만 한국어로 보고해주세요:
1. 출혈 여부
2. 화상 여부
3. 부종/붓기
4. 상처의 심각도
5. 기타 주목할 만한 증상

간단하고 명확하게 보고해주세요."""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=200,
                temperature=0.1
            )
            
            analysis = response.choices[0].message.content.strip()
            if analysis and analysis != "분석할 수 있는 특별한 의료 증상이 보이지 않습니다.":
                findings.append(f"AI 분석: {analysis}")
                
        except Exception as e:
            findings.append(f"AI 분석: 이미지 분석 중 오류 발생")
    
    return findings

def detect_emergency_from_image(img: Image.Image, img_bytes: bytes) -> List[str]:
    """이미지에서 응급상황을 감지합니다."""
    findings = simple_image_screening(img)
    
    emergency_keywords = ["출혈", "화상", "심한", "응급", "위험", "부종", "붓기"]
    emergency_findings = []
    
    for finding in findings:
        if any(keyword in finding for keyword in emergency_keywords):
            emergency_findings.append(finding)
    
    return emergency_findings

# ==================== OTC 매핑 ====================
def map_otc_to_brands(otc_list: List[str]) -> List[str]:
    mapping = {
        "해열제": "アセトアミノフェン (Acetaminophen)",
        "진통제": "イブプロフェン (Ibuprofen)",
        "제산제": "制酸剤 (Antacid)",
        "기침약": "咳止め (Cough Suppressant)",
        "항히스타민": "抗ヒスタミン (Antihistamine)",
        "소독약": "消毒剤 (Antiseptic)",
        "화상 연고": "やけど軟膏 (Burn Ointment)"
    }
    
    brands = []
    for otc in otc_list:
        if otc in mapping:
            brands.append(mapping[otc])
    
    return brands

def map_otc_to_images(otc_list: List[str]) -> List[str]:
    mapping = {
        "해열제": "🌡️",
        "진통제": "💊",
        "제산제": "🧪",
        "기침약": "🤧",
        "항히스타민": "🩹",
        "소독약": "🧴",
        "화상 연고": "🩹"
    }
    
    images = []
    for otc in otc_list:
        if otc in mapping:
            images.append(mapping[otc])
    
    return images

def build_jp_phrase(symptoms: str, otc_list: List[str]) -> str:
    """일본어 문장을 생성합니다."""
    jp_symptoms = {
        "복통": "お腹が痛いです",
        "두통": "頭が痛いです",
        "감기": "風邪をひきました",
        "화상": "やけどをしました",
        "벌레": "虫に刺されました",
        "말벌": "ハチに刺されました"
    }
    
    symptom_jp = "具合が悪いです"  # 기본값
    for symptom, jp in jp_symptoms.items():
        if symptom in symptoms:
            symptom_jp = jp
            break
    
    otc_jp = []
    for otc in otc_list:
        if "해열" in otc:
            otc_jp.append("解熱剤")
        elif "진통" in otc:
            otc_jp.append("鎮痛剤")
        elif "제산" in otc:
            otc_jp.append("制酸剤")
        elif "기침" in otc:
            otc_jp.append("咳止め")
        elif "항히스타민" in otc:
            otc_jp.append("抗ヒスタミン剤")
    
    if otc_jp:
        return f"{symptom_jp}。{', '.join(otc_jp)}をください。"
    else:
        return f"{symptom_jp}。薬をください。"

# ==================== 지오 서비스 ====================
def geocode_place(place: str) -> Tuple[float, float]:
    """장소명을 좌표로 변환합니다."""
    try:
        # MVP 모드 체크
        if os.getenv("MVP_RANDOM_TOKYO") == "true":
            import random
            return (35.6762 + random.uniform(-0.1, 0.1), 139.6503 + random.uniform(-0.1, 0.1))
        
        if os.getenv("MVP_FIXED_SHINJUKU") == "true":
            return (35.6762, 139.6503)
        
        # 실제 지오코딩
        response = requests.get(
            f"https://nominatim.openstreetmap.org/search?q={place}&format=json&limit=1",
            headers={"User-Agent": "HOS-App/1.0"}
        )
        
        if response.status_code == 200:
            data = response.json()
            if data:
                return (float(data[0]["lat"]), float(data[0]["lon"]))
        
        # 폴백: 도쿄 중심
        return (35.6762, 139.6503)
    except:
        return (35.6762, 139.6503)

def reverse_geocode(lat: float, lon: float) -> str:
    """좌표를 주소로 변환합니다."""
    try:
        response = requests.get(
            f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json",
            headers={"User-Agent": "HOS-App/1.0"}
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("display_name", f"위도: {lat}, 경도: {lon}")
        
        return f"위도: {lat}, 경도: {lon}"
    except:
        return f"위도: {lat}, 경도: {lon}"

def build_address_from_tags(tags: Dict) -> str:
    """OSM 태그에서 주소를 구성합니다."""
    address_parts = []
    
    if "addr:city" in tags:
        address_parts.append(tags["addr:city"])
    if "addr:street" in tags:
        address_parts.append(tags["addr:street"])
    if "addr:housenumber" in tags:
        address_parts.append(tags["addr:housenumber"])
    
    return " ".join(address_parts) if address_parts else "주소 정보 없음"

def search_hospitals(lat: float, lon: float) -> List[Dict]:
    """근처 병원을 검색합니다."""
    try:
        # Overpass API 쿼리
        query = f"""
        [out:json];
        (
          node["amenity"="hospital"](around:1000,{lat},{lon});
          way["amenity"="hospital"](around:1000,{lat},{lon});
          relation["amenity"="hospital"](around:1000,{lat},{lon});
        );
        out center;
        """
        
        response = requests.post(
            "https://overpass-api.de/api/interpreter",
            data=query,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            hospitals = []
            
            for element in data.get("elements", []):
                if "tags" in element:
                    name = element["tags"].get("name", "Unknown Hospital")
                    
                    # 좌표 추출
                    if "lat" in element and "lon" in element:
                        elat, elon = element["lat"], element["lon"]
                    elif "center" in element:
                        elat, elon = element["center"]["lat"], element["center"]["lon"]
                    else:
                        continue
                    
                    # 주소 구성
                    address = build_address_from_tags(element["tags"])
                    if address == "주소 정보 없음":
                        address = reverse_geocode(elat, elon)
                    
                    hospitals.append({
                        "name": name,
                        "lat": elat,
                        "lon": elon,
                        "address": address
                    })
            
            return hospitals[:5]  # 최대 5개
        
        return []
    except:
        return []

def search_pharmacies(lat: float, lon: float) -> List[Dict]:
    """근처 약국을 검색합니다."""
    try:
        # Overpass API 쿼리
        query = f"""
        [out:json];
        (
          node["amenity"="pharmacy"](around:1000,{lat},{lon});
          way["amenity"="pharmacy"](around:1000,{lat},{lon});
          relation["amenity"="pharmacy"](around:1000,{lat},{lon});
        );
        out center;
        """
        
        response = requests.post(
            "https://overpass-api.de/api/interpreter",
            data=query,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            pharmacies = []
            
            for element in data.get("elements", []):
                if "tags" in element:
                    name = element["tags"].get("name", "Unknown Pharmacy")
                    
                    # 좌표 추출
                    if "lat" in element and "lon" in element:
                        elat, elon = element["lat"], element["lon"]
                    elif "center" in element:
                        elat, elon = element["center"]["lat"], element["center"]["lon"]
                    else:
                        continue
                    
                    # 주소 구성
                    address = build_address_from_tags(element["tags"])
                    if address == "주소 정보 없음":
                        address = reverse_geocode(elat, elon)
                    
                    pharmacies.append({
                        "name": name,
                        "lat": elat,
                        "lon": elon,
                        "address": address
                    })
            
            return pharmacies[:5]  # 최대 5개
        
        return []
    except:
        return []

def build_google_maps_link(lat: float, lon: float, name: str) -> str:
    """Google Maps 링크를 생성합니다."""
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}&query_place_id={name}"

# ==================== 의약품 검색 ====================
def radar_search(keyword: str, limit: int = 5) -> List[Dict]:
    """RAD-AR에서 의약품 정보를 검색합니다."""
    try:
        # 간단한 모의 데이터 (실제로는 RAD-AR API 호출)
        mock_data = [
            {
                "brand": "ロキソニン",
                "company": "第一三共",
                "active_ingredient": "ロキソプロフェンナトリウム",
                "dosage_form": "錠剤",
                "url": "https://www.rad-ar.or.jp/siori/english/"
            },
            {
                "brand": "バファリン",
                "company": "ライオン",
                "active_ingredient": "アセトアミノフェン",
                "dosage_form": "錠剤",
                "url": "https://www.rad-ar.or.jp/siori/english/"
            }
        ]
        
        # 키워드 매칭
        results = []
        for item in mock_data:
            if keyword.lower() in item["active_ingredient"].lower() or keyword.lower() in item["brand"].lower():
                results.append(item)
        
        return results[:limit]
    except:
        return []

# ==================== 메인 앱 ====================
st.header("증상 입력")

with st.form("symptom_form"):
    symptoms = st.text_area("어떤 증상이 있나요?", placeholder="예: 복통, 두통, 벌레에 물렸어요")
    uploaded = st.file_uploader("상처 사진 (선택사항)", type=["jpg", "jpeg", "png"])
    location = st.text_input("현재 위치(도시/구 단위, 일본)", value="Tokyo")
    st.write("내 위치 사용(브라우저 권한 필요):")
    loc = streamlit_geolocation()
    traveler = st.checkbox("여행자 모드(한국→일본)", value=True)
    submitted = st.form_submit_button("상담하기")

if submitted:
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
                st.write(f"🔍 디버깅: 이미지 분석 오류 = {str(e)}")
        
        # 기본 규칙 기반 조언
        rule_out = simple_text_rules(symptoms)
        advice = rule_out["advice"]
        otc = rule_out["otc"]
        
        # 디버깅 정보
        st.write(f"🔍 디버깅: 입력된 증상 = '{symptoms}'")
        st.write(f"🔍 디버깅: 추천 OTC = {otc}")
        
        # RAG 검색
        rag_results = []
        rag_confidence = 0.0
        try:
            hits = rag.search(symptoms, top_k=3)
            passages = [h[0] for h in hits]
            rag_results = hits
            rag_confidence = max([score for _, score in hits]) if hits else 0.0
            evidence_titles = []
            for txt, _ in hits:
                first = (txt.strip().splitlines() or [""])[0].strip()
                evidence_titles.append(first[:80] if first else "근거 문서")
            st.write(f"🔍 디버깅: RAG 검색 결과 = {len(hits)}개")
        except Exception as e:
            passages = []
            evidence_titles = []
            st.write(f"🔍 디버깅: RAG 검색 오류 = {str(e)}")
        
        # 지오 검색
        nearby_hospitals = []
        nearby_pharmacies = []
        try:
            if loc and 'latitude' in loc and 'longitude' in loc:
                lat, lon = loc['latitude'], loc['longitude']
            else:
                lat, lon = geocode_place(location)
            
            # 병원과 약국 검색
            nearby_hospitals = search_hospitals(lat, lon)
            nearby_pharmacies = search_pharmacies(lat, lon)
            
            st.write(f"🔍 디버깅: 위치 = {lat}, {lon}")
            st.write(f"🔍 디버깅: 병원 = {len(nearby_hospitals)}개, 약국 = {len(nearby_pharmacies)}개")
        except Exception as e:
            st.write(f"🔍 디버깅: 지오 검색 오류 = {str(e)}")
        
        # 응급상황 체크
        emergency_reasons = []
        if rule_out.get("emergency", False):
            emergency_reasons.append("증상 기반 응급상황")
        
        if findings:
            emergency_findings = [f for f in findings if any(keyword in f for keyword in ["출혈", "화상", "심한", "응급"])]
            if emergency_findings:
                emergency_reasons.extend(emergency_findings)
        
        # 결과 표시
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
        
        # 처리 시간 표시
        processing_time = time.time() - start_time if 'start_time' in locals() else 0
        st.write(f"🔍 디버깅: 처리 시간 = {processing_time:.2f}초")
