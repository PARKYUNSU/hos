"""
관리자 대시보드
사용자 증상 로그, 미처리 증상, 자동 크롤링 상태를 모니터링합니다.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json

# 백엔드 서비스 임포트
import sys
sys.path.append('backend')
from services_logging import symptom_logger
from services_auto_crawler import auto_crawler
from services_rag_updater import rag_updater

def main():
    st.set_page_config(
        page_title="HOS 관리자 대시보드",
        page_icon="🏥",
        layout="wide"
    )
    
    st.title("🏥 HOS 관리자 대시보드")
    st.markdown("---")
    
    # 사이드바
    with st.sidebar:
        st.header("📊 메뉴")
        page = st.selectbox(
            "페이지 선택",
            ["대시보드", "증상 로그", "미처리 증상", "크롤링 관리", "RAG 관리", "시스템 설정"]
        )
    
    if page == "대시보드":
        show_dashboard()
    elif page == "증상 로그":
        show_symptom_logs()
    elif page == "미처리 증상":
        show_unhandled_symptoms()
    elif page == "크롤링 관리":
        show_crawling_management()
    elif page == "RAG 관리":
        show_rag_management()
    elif page == "시스템 설정":
        show_system_settings()

def show_dashboard():
    """메인 대시보드"""
    st.header("📈 시스템 현황")
    
    # 통계 가져오기
    stats = symptom_logger.get_symptom_statistics()
    rag_stats = rag_updater.get_rag_statistics()
    
    # 메트릭 표시
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="총 증상 로그",
            value=stats['total_logs'],
            delta=f"+{stats['recent_logs_24h']} (24h)"
        )
    
    with col2:
        st.metric(
            label="성공률",
            value=f"{stats['success_rate']:.1%}",
            delta=f"{stats['successful_advice']}건 성공"
        )
    
    with col3:
        st.metric(
            label="미처리 증상",
            value=stats['unhandled_symptoms'],
            delta="처리 필요"
        )
    
    with col4:
        st.metric(
            label="RAG 데이터",
            value=f"{rag_stats['total_files']}개 파일",
            delta=f"{rag_stats['total_size_mb']}MB"
        )
    
    # 차트
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 응답 품질 분포")
        
        # RAG 신뢰도 분포 (예시)
        confidence_data = {
            '범위': ['0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0'],
            '건수': [10, 25, 35, 20, 10]
        }
        
        fig = px.bar(
            confidence_data, 
            x='범위', 
            y='건수',
            title="RAG 신뢰도 분포",
            color='건수',
            color_continuous_scale='RdYlGn'
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("📈 시간별 증상 로그")
        
        # 시간별 로그 (예시)
        time_data = {
            '시간': [f"{i:02d}:00" for i in range(24)],
            '로그 수': [5, 3, 2, 1, 2, 8, 15, 25, 30, 28, 22, 18, 20, 25, 30, 28, 22, 18, 15, 12, 8, 6, 4, 3]
        }
        
        fig = px.line(
            time_data, 
            x='시간', 
            y='로그 수',
            title="시간별 증상 로그 수"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # 최근 활동
    st.subheader("🕒 최근 활동")
    
    # 최근 미처리 증상
    recent_unhandled = symptom_logger.get_unhandled_symptoms(5)
    
    if recent_unhandled:
        for symptom in recent_unhandled:
            with st.expander(f"🔍 {symptom['symptom_text']}"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**빈도:** {symptom['frequency']}회")
                with col2:
                    st.write(f"**신뢰도:** {symptom['rag_confidence']:.2f}")
                with col3:
                    st.write(f"**우선순위:** {symptom['priority_score']:.1f}")
                
                st.write(f"**마지막 발생:** {symptom['last_seen']}")
    else:
        st.info("최근 미처리 증상이 없습니다.")

def show_symptom_logs():
    """증상 로그 페이지"""
    st.header("📋 증상 로그")
    
    # 필터 옵션
    col1, col2, col3 = st.columns(3)
    
    with col1:
        date_range = st.date_input(
            "날짜 범위",
            value=(datetime.now() - timedelta(days=7), datetime.now()),
            max_value=datetime.now()
        )
    
    with col2:
        success_filter = st.selectbox(
            "응답 성공 여부",
            ["전체", "성공", "실패"]
        )
    
    with col3:
        limit = st.number_input("표시 개수", min_value=10, max_value=1000, value=50)
    
    # 로그 데이터 가져오기 (실제로는 데이터베이스에서 가져와야 함)
    st.subheader("📊 로그 데이터")
    
    # 예시 데이터
    sample_data = {
        '시간': [datetime.now() - timedelta(hours=i) for i in range(20)],
        '증상': ['복통', '두통', '벌레 물림', '화상', '감기', '알레르기', '복통', '두통', '벌레 물림', '화상', 
                '감기', '알레르기', '복통', '두통', '벌레 물림', '화상', '감기', '알레르기', '복통', '두통'],
        '이미지': [True, False, True, True, False, True, True, False, True, True, 
                  False, True, True, False, True, True, False, True, True, False],
        'RAG 신뢰도': [0.8, 0.6, 0.3, 0.9, 0.7, 0.4, 0.8, 0.6, 0.3, 0.9, 
                     0.7, 0.4, 0.8, 0.6, 0.3, 0.9, 0.7, 0.4, 0.8, 0.6],
        '응답 성공': [True, True, False, True, True, False, True, True, False, True, 
                     True, False, True, True, False, True, True, False, True, True]
    }
    
    df = pd.DataFrame(sample_data)
    
    # 필터 적용
    if success_filter != "전체":
        df = df[df['응답 성공'] == (success_filter == "성공")]
    
    st.dataframe(df, use_container_width=True)
    
    # 통계
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("총 로그", len(df))
    with col2:
        st.metric("성공률", f"{df['응답 성공'].mean():.1%}")
    with col3:
        st.metric("평균 신뢰도", f"{df['RAG 신뢰도'].mean():.2f}")

def show_unhandled_symptoms():
    """미처리 증상 페이지"""
    st.header("🚨 미처리 증상")
    
    # 미처리 증상 가져오기
    unhandled = symptom_logger.get_unhandled_symptoms(20)
    
    if not unhandled:
        st.success("🎉 처리할 미처리 증상이 없습니다!")
        return
    
    st.subheader(f"📊 총 {len(unhandled)}개의 미처리 증상")
    
    # 우선순위별 정렬
    unhandled.sort(key=lambda x: x['priority_score'], reverse=True)
    
    for i, symptom in enumerate(unhandled, 1):
        with st.expander(f"#{i} {symptom['symptom_text']} (우선순위: {symptom['priority_score']:.1f})"):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.write(f"**빈도:** {symptom['frequency']}회")
            with col2:
                st.write(f"**신뢰도:** {symptom['rag_confidence']:.2f}")
            with col3:
                st.write(f"**첫 발생:** {symptom['first_seen']}")
            with col4:
                st.write(f"**마지막 발생:** {symptom['last_seen']}")
            
            # 액션 버튼
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button(f"🔍 크롤링 시작", key=f"crawl_{i}"):
                    with st.spinner("크롤링 중..."):
                        result = auto_crawler.crawl_for_symptoms(symptom['symptom_text'])
                        if result['success']:
                            st.success(f"크롤링 완료: {result['total_results']}개 결과")
                        else:
                            st.error(f"크롤링 실패: {result.get('error', 'Unknown error')}")
            
            with col2:
                if st.button(f"✅ 처리 완료", key=f"complete_{i}"):
                    st.success("처리 완료로 표시되었습니다.")
            
            with col3:
                if st.button(f"❌ 무시", key=f"ignore_{i}"):
                    st.warning("무시로 표시되었습니다.")

def show_crawling_management():
    """크롤링 관리 페이지"""
    st.header("🕷️ 크롤링 관리")
    
    # 자동 크롤링 실행
    st.subheader("🤖 자동 크롤링")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🚀 미처리 증상 자동 크롤링", type="primary"):
            with st.spinner("자동 크롤링 실행 중..."):
                result = auto_crawler.process_unhandled_symptoms(5)
                
                st.success(f"크롤링 완료!")
                st.write(f"- 처리된 증상: {result['processed']}개")
                st.write(f"- 성공: {result['successful']}개")
                st.write(f"- 실패: {result['failed']}개")
                
                # 결과 상세
                for item in result['results']:
                    if item['status'] == 'success':
                        st.success(f"✅ {item['symptom']}: {item['results_count']}개 결과")
                    else:
                        st.error(f"❌ {item['symptom']}: {item['error']}")
    
    with col2:
        # 수동 크롤링
        st.subheader("✋ 수동 크롤링")
        
        symptom_text = st.text_input("크롤링할 증상 입력")
        
        if st.button("🔍 크롤링 실행") and symptom_text:
            with st.spinner("크롤링 중..."):
                result = auto_crawler.crawl_for_symptoms(symptom_text)
                
                if result['success']:
                    st.success(f"크롤링 완료: {result['total_results']}개 결과")
                    
                    # 결과 표시
                    for item in result['results']:
                        with st.expander(f"{item['site']} - {item['title']}"):
                            st.write(f"**URL:** {item['url']}")
                            st.write(f"**매칭 키워드:** {', '.join(item['keywords_matched'])}")
                            if item['content']:
                                st.write(f"**내용:** {item['content'][:200]}...")
                else:
                    st.error(f"크롤링 실패: {result.get('error', 'Unknown error')}")
    
    # 크롤링 통계
    st.subheader("📊 크롤링 통계")
    
    # 예시 통계
    stats_data = {
        '사이트': ['MHLW', 'JMA', 'JRC', '기타'],
        '성공률': [0.85, 0.78, 0.92, 0.65],
        '평균 결과 수': [12, 8, 15, 5]
    }
    
    df = pd.DataFrame(stats_data)
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.bar(df, x='사이트', y='성공률', title="사이트별 크롤링 성공률")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.bar(df, x='사이트', y='평균 결과 수', title="사이트별 평균 결과 수")
        st.plotly_chart(fig, use_container_width=True)

def show_rag_management():
    """RAG 관리 페이지"""
    st.header("🧠 RAG 데이터 관리")
    
    # RAG 통계
    rag_stats = rag_updater.get_rag_statistics()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 파일 수", rag_stats['total_files'])
    with col2:
        st.metric("총 크기", f"{rag_stats['total_size_mb']}MB")
    with col3:
        st.metric("마지막 업데이트", rag_stats['last_update'] or "없음")
    with col4:
        st.metric("버전", rag_stats['version'])
    
    # RAG 업데이트
    st.subheader("🔄 RAG 시스템 업데이트")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 새 파일 스캔", type="primary"):
            new_files = rag_updater.scan_new_files()
            if new_files:
                st.success(f"새 파일 {len(new_files)}개 발견!")
                for file in new_files:
                    st.write(f"- {file.name}")
            else:
                st.info("새 파일이 없습니다.")
    
    with col2:
        if st.button("🚀 RAG 시스템 업데이트"):
            with st.spinner("RAG 시스템 업데이트 중..."):
                result = rag_updater.update_rag_system()
                
                if result['success']:
                    st.success(f"업데이트 완료: {result['new_files']}개 새 파일")
                    st.write(f"총 파일 수: {result['total_files']}개")
                    if 'backup_path' in result:
                        st.write(f"백업 위치: {result['backup_path']}")
                else:
                    st.error(f"업데이트 실패: {result['error']}")
                    if result.get('backup_restored'):
                        st.info("백업에서 복원되었습니다.")
    
    # 파일 목록
    st.subheader("📁 데이터 파일 목록")
    
    passages_dir = Path("data/passages/jp")
    if passages_dir.exists():
        files = list(passages_dir.glob("*.txt"))
        
        if files:
            file_data = []
            for file in files:
                if file.name != "metadata.json":
                    stat = file.stat()
                    file_data.append({
                        '파일명': file.name,
                        '크기 (KB)': round(stat.st_size / 1024, 2),
                        '수정일': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    })
            
            df = pd.DataFrame(file_data)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("데이터 파일이 없습니다.")
    else:
        st.warning("데이터 디렉토리가 존재하지 않습니다.")

def show_system_settings():
    """시스템 설정 페이지"""
    st.header("⚙️ 시스템 설정")
    
    # 환경변수 설정
    st.subheader("🔧 환경변수")
    
    env_vars = {
        'OPENAI_API_KEY': 'OpenAI API 키',
        'IMG_RED_RATIO': '이미지 빨간색 임계값',
        'IMG_BURN_RATIO': '이미지 화상 임계값',
        'TRIAGE_API_URL': '응급분류 API URL',
        'MVP_RANDOM_TOKYO': 'MVP 랜덤 도쿄 모드',
        'MVP_FIXED_SHINJUKU': 'MVP 고정 신주쿠 모드',
        'FAST_MODE': '빠른 모드'
    }
    
    for var, description in env_vars.items():
        value = os.getenv(var, '설정되지 않음')
        if var == 'OPENAI_API_KEY' and value != '설정되지 않음':
            value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
        
        st.text_input(f"{description} ({var})", value=value, disabled=True)
    
    # 데이터베이스 관리
    st.subheader("🗄️ 데이터베이스 관리")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 데이터베이스 통계"):
            stats = symptom_logger.get_symptom_statistics()
            st.json(stats)
    
    with col2:
        if st.button("🧹 오래된 백업 정리"):
            rag_updater.cleanup_old_backups(7)
            st.success("7일 이상 된 백업이 정리되었습니다.")
    
    # 시스템 정보
    st.subheader("ℹ️ 시스템 정보")
    
    import platform
    import sys
    
    system_info = {
        'Python 버전': sys.version,
        '플랫폼': platform.platform(),
        'Streamlit 버전': st.__version__,
        '작업 디렉토리': os.getcwd()
    }
    
    for key, value in system_info.items():
        st.text_input(key, value=value, disabled=True)

if __name__ == "__main__":
    main()
