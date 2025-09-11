from fastapi import FastAPI, UploadFile, File, Form, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
import logging
import json
from typing import List, Optional
import concurrent.futures
from io import BytesIO
from PIL import Image
import os
import base64
import numpy as np
from backend.services_rag import GLOBAL_RAG
from backend.services_geo import geocode_place, search_hospitals, search_pharmacies
from backend.services_gen import generate_advice
from backend.services_radar import radar_search_cached


class ChatResponse(BaseModel):
    advice: str
    otc: List[str]
    nearby_hospitals: List[dict]
    requires_emergency_call: bool = False
    emergency_reasons: List[str] = []
    nearby_pharmacies: List[dict] = []
    traveler_mode: bool = False
    jp_phrase: Optional[str] = None
    otc_brands: List[str] = []
    hospital_map_urls: List[str] = []
    pharmacy_map_urls: List[str] = []
    evidence_titles: List[str] = []
    otc_image_urls: List[str] = []


from backend.logging_setup import setup_logging

# Load environment variables from .env if present
load_dotenv()

logger = setup_logging()

app = FastAPI(title="Emergency Triage API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
def health() -> dict:
    logger.debug(json.dumps({"event": "health_check"}))
    return {"status": "ok"}


@app.get("/config")
def config() -> dict:
    return {
        "openai_enabled": bool(os.getenv("OPENAI_API_KEY")),
        "img_thresholds": {
            "red_ratio": float(os.getenv("IMG_RED_RATIO", "0.25")),
            "burn_ratio": float(os.getenv("IMG_BURN_RATIO", "0.30")),
        },
        "fast_mode": os.getenv("FAST_MODE", "0") in ("1", "true", "True", "on"),
    }


def simple_image_screening(img: Image.Image) -> List[str]:
    w, h = img.size
    findings: List[str] = []
    if min(w, h) < 128:
        findings.append("저해상도 이미지")
    # 실제 VLM 모델 연결 전 자리표시자
    return findings


def detect_emergency_from_image(img: Image.Image, raw_image: bytes) -> List[str]:
    reasons: List[str] = []
    # Thresholds via env
    red_thr = float(os.getenv("IMG_RED_RATIO", "0.25"))
    burn_thr = float(os.getenv("IMG_BURN_RATIO", "0.30"))
    # Heuristic: dominant red (possible heavy bleeding)
    try:
        small = img.resize((224, 224))
        hsv = small.convert("HSV")
        arr = np.array(hsv)
        h = arr[:, :, 0].astype(np.float32)  # 0..255
        s = arr[:, :, 1].astype(np.float32)
        v = arr[:, :, 2].astype(np.float32)
        red_mask = ((h < 10) | (h > 245)) & (s > 100) & (v > 60)
        red_ratio = float(red_mask.mean())
        if red_ratio > red_thr:
            reasons.append("이미지상 과다 출혈 의심")
        # Heuristic: orange/yellow high sat/val (possible burn/erythema)
        orange_mask = (h >= 10) & (h <= 50) & (s > 120) & (v > 120)
        orange_ratio = float(orange_mask.mean())
        if orange_ratio > burn_thr:
            reasons.append("이미지상 화상/광범위 홍반 의심")
    except Exception:
        pass

    # OpenAI vision (optional)
    try:
        from openai import OpenAI  # type: ignore
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key and raw_image:
            client = OpenAI(api_key=api_key)
            b64 = base64.b64encode(raw_image).decode("utf-8")
            prompt = (
                "이미지에서 다음 항목을 감지하세요. 발견된 항목의 라벨만 쉼표로 구분해 반환: "
                "HEAVY_BLEEDING, SEVERE_BURN, BONE_EXPOSURE, AMPUTATION, SEVERE_INJURY. "
                "없으면 NONE만 반환. 추가 설명/문장 금지."
            )
            content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Answer strictly with labels only."},
                    {"role": "user", "content": content},
                ],
                temperature=0,
                max_tokens=20,
            )
            ans = (res.choices[0].message.content or "").strip().upper()
            labels = [a.strip() for a in ans.replace(";", ",").split(",") if a.strip()]
            for lab in labels:
                if lab == "HEAVY_BLEEDING":
                    reasons.append("비전 분석: 과다 출혈 의심")
                elif lab == "SEVERE_BURN":
                    reasons.append("비전 분석: 심한 화상 의심")
                elif lab == "BONE_EXPOSURE":
                    reasons.append("비전 분석: 뼈 노출 의심")
                elif lab == "AMPUTATION":
                    reasons.append("비전 분석: 절단/절단상 의심")
                elif lab == "SEVERE_INJURY":
                    reasons.append("비전 분석: 중증 외상 의심")
    except Exception:
        pass

    return reasons


def simple_text_rules(symptoms_text: str) -> dict:
    t = (symptoms_text or "").lower()
    advice = "증상에 대한 기본 응급처치를 안내합니다. 심각한 증상이면 즉시 119(일본: 119)를 호출하세요."
    otc: List[str] = []
    if any(k in t for k in ["fever", "열", "発熱"]):
        otc.append("해열제(아세트아미노펜)")
    if any(k in t for k in ["cough", "기침", "咳"]):
        otc.append("진해거담제")
    if any(k in t for k in ["diarrhea", "설사", "下痢"]):
        otc.append("지사제 및 수분보충")
    if any(k in t for k in ["abdominal pain", "stomach ache", "배아픔", "복통", "腹痛"]):
        otc.extend(["제산제/위산억제제(증상에 따라)", "가스완화제(시메티콘)", "진통제(아세트아미노펜)"])
    # 확장 증상
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


def build_google_maps_link(lat: Optional[float], lon: Optional[float], name: Optional[str] = None) -> Optional[str]:
    if lat is None or lon is None:
        return None
    q = f"{lat},{lon}"
    if name:
        q = name
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def build_jp_phrase(symptoms_text: str, otc: List[str]) -> str:
    # 약국에서 사용할 수 있는 간단한 일본어 표현
    base = "薬局で相談したいです。"
    if any("지사제" in o or "설사" in symptoms_text for o in otc) or ("설사" in (symptoms_text or "")):
        return base + "『腹痛や下痢があります。市販の整腸剤や下痢止めを探しています。』"
    if any("해열" in o or "열" in symptoms_text for o in otc) or ("발열" in (symptoms_text or "") or "열" in (symptoms_text or "")):
        return base + "『発熱があります。アセトアミノフェン成分の解熱薬を探しています。』"
    if any("진해" in o or "기침" in symptoms_text for o in otc) or ("咳" in (symptoms_text or "")):
        return base + "『咳があります。市販の鎮咳去痰薬を探しています。』"
    return base + "『症状に合う一般用医薬品を教えてください。』"


def random_tokyo_latlon() -> tuple:
    import random
    # Rough bounding box covering Tokyo 23 wards
    lat = random.uniform(35.56, 35.80)
    lon = random.uniform(139.60, 139.92)
    return (lat, lon)

def fixed_shinjuku_latlon() -> tuple:
    # JR 신주쿠역 근처(서측/동측 사이 중간 지점 근사)
    return (35.690921, 139.700258)

def map_otc_to_brands(otc: List[str]) -> List[str]:
    # 구체 상표 대신 성분 중심/카테고리 힌트 제공(안전)
    hints: List[str] = []
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
    # 중복 제거
    out = []
    for h in hints:
        if h not in out:
            out.append(h)
    return out


def _collect_local_jp_images(category_key: str, limit: int = 6) -> List[str]:
    base_dir = os.path.join("static", "otc", "jp", category_key)
    if not os.path.isdir(base_dir):
        return []
    files = sorted(
        [f for f in os.listdir(base_dir) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    )
    return [f"/static/otc/jp/{category_key}/{f}" for f in files[:limit]]


def map_otc_to_images(otc: List[str]) -> List[str]:
    urls: List[str] = []

    def add_for(cat: str, placeholder: str) -> None:
        local = _collect_local_jp_images(cat)
        if local:
            urls.extend(local)
        else:
            urls.append(placeholder)

    for o in otc:
        lo = o.lower()
        if ("해열" in o) or ("acet" in lo):
            add_for("acetaminophen", "/static/otc/acetaminophen.svg")
        if "지사" in o:
            add_for("antidiarrheal", "/static/otc/antidiarrheal.svg")
        if ("제산" in o) or ("위산" in o):
            add_for("antacid", "/static/otc/antacid.svg")
        if ("가스" in o) or ("시메티콘" in o):
            add_for("simethicone", "/static/otc/simethicone.svg")
        if "항히스타민" in o:
            add_for("antihistamine", "/static/otc/antihistamine.svg")
        if ("경구수분보충" in o) or ("ors" in lo):
            add_for("ors", "/static/otc/ors.svg")
        if ("로젠지" in o) or ("목염증" in o):
            add_for("lozenge", "/static/otc/lozenge.svg")
        if ("비충혈" in o) or ("decongestant" in lo) or ("디콘제스턴트" in o):
            add_for("decongestant", "/static/otc/decongestant.svg")
        # 피부카테고리(추가됨)
        if ("화상" in o) or ("burn" in lo):
            add_for("burngel", "/static/otc/burngel.svg")
        if ("보습" in o) or ("건조" in o) or ("atopy" in lo) or ("아토피" in o):
            add_for("emollient", "/static/otc/emollient.svg")

    # dedupe
    dedup: List[str] = []
    for u in urls:
        if u not in dedup:
            dedup.append(u)
    return dedup


CRITICAL_KEYWORDS = [
    "chest pain", "심한 가슴 통증", "胸の激痛",
    "severe bleeding", "대량 출혈", "大量出血",
    "unconscious", "의식 없음", "意識なし",
    "stroke", "편마비", "脳卒中",
    "difficulty breathing", "숨이 가쁨", "呼吸困難",
    "severe abdominal pain", "복부 극심한 통증", "激しい腹痛",
]


def detect_emergency(symptoms_text: str, findings: List[str]) -> List[str]:
    t = (symptoms_text or "").lower()
    reasons: List[str] = []
    for k in CRITICAL_KEYWORDS:
        if k in t:
            reasons.append(k)
    # 이미지 분석 결과 반영(다국어)
    for f in findings:
        fl = f.lower()
        if any(s in fl for s in [
            "heavy bleeding", "과다 출혈", "대량 출혈", "大量出血",
            "심각 손상", "severe injury", "重度外傷"
        ]):
            reasons.append(f)
    return reasons


def search_hospitals_jp(place: str) -> List[dict]:
    geo = geocode_place(place or "Tokyo")
    if not geo:
        return []
    return search_hospitals(geo["lat"], geo["lon"], radius_m=3000)


def search_pharmacies_jp(place: str) -> List[dict]:
    geo = geocode_place(place or "Tokyo")
    if not geo:
        return []
    return search_pharmacies(geo["lat"], geo["lon"], radius_m=3000)


@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    image: UploadFile = File(None),
    symptoms: str = Form("") ,
    location: str = Form("Japan"),
    lat: float = Form(None),
    lon: float = Form(None),
    traveler: str = Form("0"),  # "1"이면 여행자 모드
) -> ChatResponse:
    fast_mode = os.getenv("FAST_MODE", "0") in ("1", "true", "True", "on")
    findings: List[str] = []
    raw_image: bytes = b""
    if image is not None:
        content = await image.read()
        raw_image = content
        try:
            img = Image.open(BytesIO(content)).convert("RGB")
            findings = simple_image_screening(img)
            emg_img = detect_emergency_from_image(img, raw_image)
            if emg_img:
                findings.extend(emg_img)
        except Exception:
            findings = ["이미지 해석 실패"]

    # MVP: Use random Tokyo coordinates when enabled and no coordinates provided
    try:
        if (lat is None or lon is None):
            # 1) Explicit fixed lat/lon via env
            if os.getenv("MVP_FIXED_LAT") and os.getenv("MVP_FIXED_LON"):
                lat = float(os.getenv("MVP_FIXED_LAT"))
                lon = float(os.getenv("MVP_FIXED_LON"))
            # 2) Shinjuku station preset
            elif os.getenv("MVP_FIXED_SHINJUKU", "0") in ("1", "true", "True", "on"):
                flat, flon = fixed_shinjuku_latlon()
                lat = float(flat)
                lon = float(flon)
            # 3) Random Tokyo fallback
            elif os.getenv("MVP_RANDOM_TOKYO", "0") in ("1", "true", "True", "on"):
                rlat, rlon = random_tokyo_latlon()
                lat = float(rlat)
                lon = float(rlon)
    except Exception:
        pass

    rule_out = simple_text_rules(symptoms)
    advice = rule_out["advice"]
    otc = rule_out["otc"]
    # Geo lookups (skip in fast mode)
    nearby: List[dict] = []
    pharmacies: List[dict] = []
    if not fast_mode:
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                if lat is not None and lon is not None:
                    fut_h = pool.submit(search_hospitals, lat, lon, 2000)
                    fut_p = pool.submit(search_pharmacies, lat, lon, 1500)
                else:
                    fut_h = pool.submit(search_hospitals_jp, location)
                    fut_p = pool.submit(search_pharmacies_jp, location)
                try:
                    nearby = fut_h.result(timeout=7)
                except Exception:
                    nearby = []
                try:
                    pharmacies = fut_p.result(timeout=7)
                except Exception:
                    pharmacies = []
        except Exception:
            nearby, pharmacies = [], []

    evidence_titles: List[str] = []
    passages: List[str] = []
    gen_text = ""
    if not fast_mode:
        # 간단 RAG로 한두 문장 보강
        hits = GLOBAL_RAG.search(symptoms, top_k=3)
        passages = [h[0] for h in hits]
        for txt, _ in hits:
            # 첫 줄 또는 40자까지를 제목 대용으로 사용
            first = (txt.strip().splitlines() or [""])[0].strip()
            evidence_titles.append(first[:80] if first else "근거 문서")
        # Generate advice with timeout guard
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                fut_gen = pool.submit(generate_advice, symptoms, findings, passages, raw_image or None)
                try:
                    gen_text = fut_gen.result(timeout=7)
                except Exception:
                    gen_text = ""
        except Exception:
            gen_text = ""
    if gen_text:
        advice = gen_text

    if findings:
        advice += " | 이미지 참고: " + ", ".join(findings)
    emg = detect_emergency(symptoms, findings)

    # 지도 링크 생성
    hospital_links: List[str] = []
    for h in nearby:
        link = build_google_maps_link(h.get("lat"), h.get("lon"), h.get("name"))
        if link:
            hospital_links.append(link)
    pharmacy_links: List[str] = []
    for p in pharmacies:
        link = build_google_maps_link(p.get("lat"), p.get("lon"), p.get("name"))
        if link:
            pharmacy_links.append(link)

    traveler_mode = traveler in ("1", "true", "True", "on")
    jp_phrase = build_jp_phrase(symptoms, otc) if traveler_mode else None
    otc_brands = map_otc_to_brands(otc) if traveler_mode else []
    otc_images = map_otc_to_images(otc)

    ua = request.headers.get("user-agent", "")
    request_id = request.headers.get("x-request-id") or request.scope.get("headers")
    # 간단한 요청 ID 대체: 없음이면 id(request)
    if not isinstance(request_id, str):
        request_id = str(id(request))

    payload_for_log = {
        "symptoms_len": len(symptoms or ""),
        "has_image": image is not None,
        "location": location,
        "lat": lat,
        "lon": lon,
        "traveler_mode": traveler_mode,
        "requires_emergency_call": len(emg) > 0,
        "emergency_reasons": emg,
        "otc": otc,
        "ua": ua[:200],
        "request_id": request_id,
    }
    try:
        import time
        start = time.perf_counter()
        logger.info(json.dumps({"event": "chat_in", **payload_for_log}))
    except Exception:
        start = None

    try:
        resp = ChatResponse(
        advice=advice,
        otc=otc,
        nearby_hospitals=nearby,
        requires_emergency_call=len(emg) > 0,
        emergency_reasons=emg,
        nearby_pharmacies=pharmacies,
        traveler_mode=traveler_mode,
        jp_phrase=jp_phrase,
        otc_brands=otc_brands,
        hospital_map_urls=hospital_links,
        pharmacy_map_urls=pharmacy_links,
        evidence_titles=evidence_titles,
        otc_image_urls=otc_images,
        )
        return resp
    except Exception as e:
        logger.exception(json.dumps({"event": "chat_error", "request_id": request_id, "error": str(e)}))
        raise
    finally:
        if start is not None:
            import time
            dur_ms = int((time.perf_counter() - start) * 1000)
            try:
                logger.info(json.dumps({"event": "chat_out", "request_id": request_id, "duration_ms": dur_ms}))
            except Exception:
                pass



@app.get("/drugsearch")
def drugsearch(q: str = "", limit: int = 10, live: bool = False) -> dict:
    """RAD-AR(영문) 검색: 로컬 JSON 우선, 필요시 live=1로 강제 갱신"""
    try:
        query = (q or "").strip()
        if not query:
            return {"query": q, "count": 0, "items": []}
        if live:
            from backend.services_radar import radar_search, save_search_to_json
            items = radar_search(query, limit=limit)
            try:
                save_search_to_json(query, items)
            except Exception:
                pass
        else:
            items = radar_search_cached(query, limit=limit)
        return {"query": q, "count": len(items), "items": items}
    except Exception as e:
        logger.exception(json.dumps({"event": "radar_error", "q": q, "error": str(e)}))
        return {"query": q, "count": 0, "items": [], "error": str(e)}
        