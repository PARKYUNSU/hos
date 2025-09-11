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
]

# ==================== 지오 서비스 ====================
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

def _headers() -> Dict[str, str]:
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
            results.append({
                "name": name,
                "address": tags.get("addr:full", ""),
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
            results.append({
                "name": name,
                "address": tags.get("addr:full", ""),
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
    
    return {"advice": advice, "otc": otc}

# ==================== 응급상황 감지 ====================
CRITICAL_KEYWORDS = [
    "chest pain", "심한 가슴 통증", "胸の激痛",
    "severe bleeding", "대량 출혈", "大量出血",
    "unconscious", "의식 없음", "意識なし",
    "stroke", "편마비", "脳卒中",
    "difficulty breathing", "숨이 가쁨", "呼吸困難",
    "severe abdominal pain", "복부 극심한 통증", "激しい腹痛",
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

def detect_emergency_from_image(img: Image.Image) -> List[str]:
    reasons: List[str] = []
    red_thr = 0.25
    burn_thr = 0.30
    
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

# ==================== 메인 앱 ====================
@st.cache_resource
def load_rag():
    _disk = load_disk_passages()
    return HybridRAG(_disk if _disk else DEFAULT_PASSAGES)

# RAG 로드
rag = load_rag()

with st.form("chat_form"):
    uploaded = st.file_uploader("증상 사진 업로드 (선택)", type=["png", "jpg", "jpeg"])
    symptoms = st.text_area("증상 설명", placeholder="예) 이마가 찢어져 피가 나요, 열이 38.5도예요")
    location = st.text_input("현재 위치(도시/구 단위, 일본)", value="Tokyo")
    st.write("내 위치 사용(브라우저 권한 필요):")
    loc = streamlit_geolocation()
    traveler = st.checkbox("여행자 모드(한국→일본)", value=True)
    submitted = st.form_submit_button("상담하기")

if submitted:
    with st.spinner("분석 중..."):
        # 이미지 분석
        findings = []
        if uploaded is not None:
            try:
                img = Image.open(uploaded).convert("RGB")
                findings = simple_image_screening(img)
                emg_img = detect_emergency_from_image(img)
                if emg_img:
                    findings.extend(emg_img)
            except Exception:
                findings = ["이미지 해석 실패"]
        
        # 기본 규칙 기반 조언
        rule_out = simple_text_rules(symptoms)
        advice = rule_out["advice"]
        otc = rule_out["otc"]
        
        # RAG 검색
        try:
            hits = rag.search(symptoms, top_k=3)
            passages = [h[0] for h in hits]
            evidence_titles = []
            for txt, _ in hits:
                first = (txt.strip().splitlines() or [""])[0].strip()
                evidence_titles.append(first[:80] if first else "근거 문서")
        except Exception:
            passages = []
            evidence_titles = []
        
        # 지오 검색
        nearby_hospitals = []
        nearby_pharmacies = []
        try:
            if loc and loc.get("latitude") and loc.get("longitude"):
                lat, lon = loc["latitude"], loc["longitude"]
            else:
                geo = geocode_place(location)
                if geo:
                    lat, lon = geo["lat"], geo["lon"]
                else:
                    lat, lon = 35.676203, 139.650311  # Tokyo fallback
            
            nearby_hospitals = search_hospitals(lat, lon, 2000)
            nearby_pharmacies = search_pharmacies(lat, lon, 1500)
        except Exception:
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
            st.image(uploaded, caption="증상 사진", use_column_width=True)
        
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
            
            st.caption("일본 현지 드럭스토어/약국(Matsumoto Kiyoshi, Welcia 등)에서 구매 가능")
