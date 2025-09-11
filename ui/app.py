import os
import requests
import streamlit as st
from streamlit_geolocation import streamlit_geolocation


API_URL = os.getenv("TRIAGE_API_URL", "http://localhost:8000")

st.set_page_config(page_title="응급 챗봇", page_icon="🚑", layout="centered")
st.title("응급 환자 챗봇 (일본)")
st.caption(f"API: {API_URL}")

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
        files = {"image": (uploaded.name, uploaded.getvalue(), uploaded.type)} if uploaded else None
        data = {"symptoms": symptoms, "location": location, "traveler": "1" if traveler else "0"}
        if loc and loc.get("latitude") and loc.get("longitude"):
            data.update({"lat": str(loc["latitude"]), "lon": str(loc["longitude"])})
        try:
            res = requests.post(f"{API_URL}/chat", files=files, data=data, timeout=20)
            if res.ok:
                data = res.json()
                if data.get("requires_emergency_call"):
                    st.error("위급 신호가 감지되었습니다. 즉시 119로 전화하세요.")
                    reasons = data.get("emergency_reasons", [])
                    if reasons:
                        st.write("근거: ", ", ".join(reasons))
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.link_button("현지 119 연결", "tel:119")
                    with col_b:
                        st.link_button("한국 긴급 지원(재외국민)", "tel:+82232100404")
                    st.caption("참고: 해외에서 한국 119 직접 연결은 불가하며, 재외국민 긴급전화로 도움을 받을 수 있습니다.")
                else:
                    st.subheader("조언")
                    st.write(data.get("advice", ""))
                    otc = data.get("otc", [])
                    if otc:
                        st.subheader("권장 OTC")
                        st.write(", ".join(otc))
                        brands = data.get("otc_brands", [])
                        if brands:
                            st.caption("구매 시 참고(성분/카테고리):")
                            for b in brands:
                                st.write(f"- {b}")
                        imgs = data.get("otc_image_urls", [])
                        if imgs:
                            st.caption("대표 이미지")
                            cols = st.columns(min(4, len(imgs)))
                            for i, url in enumerate(imgs):
                                with cols[i % len(cols)]:
                                    # 상대 경로를 절대 URL로 변환
                                    full_url = f"{API_URL}{url}" if url.startswith("/") else url
                                    st.image(full_url, use_column_width=True)
                    hospitals = data.get("nearby_hospitals", [])
                    if hospitals:
                        st.subheader("근처 병원")
                        for h in hospitals:
                            st.write(f"- {h.get('name')} ({h.get('address')})")
                    hlinks = data.get("hospital_map_urls", [])
                    if hlinks:
                        st.caption("병원 지도 링크")
                        for url in hlinks[:5]:
                            st.write(f"- {url}")
                    pharmacies = data.get("nearby_pharmacies", [])
                    if pharmacies:
                        st.subheader("근처 약국")
                        for p in pharmacies:
                            st.write(f"- {p.get('name')} ({p.get('address')})")
                    plinks = data.get("pharmacy_map_urls", [])
                    if plinks:
                        st.caption("약국 지도 링크")
                        for url in plinks[:5]:
                            st.write(f"- {url}")
                    if data.get("traveler_mode") and data.get("jp_phrase"):
                        st.subheader("약국에서 보여줄 일본어 문장")
                        st.code(data.get("jp_phrase"))
                    ev = data.get("evidence_titles", [])
                    if ev:
                        st.subheader("근거(제목/첫줄)")
                        for t in ev:
                            st.write(f"- {t}")
                    if data.get("otc"):
                        st.caption("일본 현지 드럭스토어/약국(Matsumoto Kiyoshi, Welcia 등)에서 구매 가능")
            else:
                st.error(f"API 오류: {res.status_code} {res.text}")
        except Exception as e:
            st.error(f"연결 실패: {e}")


