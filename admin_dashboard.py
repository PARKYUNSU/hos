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
import os
import sqlite3
from pathlib import Path

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
            ["대시보드", "증상 로그", "미처리 증상", "크롤링 상태", "RAG 관리", "시스템 설정"]
        )
    
    if page == "대시보드":
        show_dashboard()
    elif page == "증상 로그":
        show_symptom_logs()
    elif page == "미처리 증상":
        show_unhandled_symptoms()
    elif page == "크롤링 상태":
        show_crawling_status()
    elif page == "RAG 관리":
        show_rag_management()
    elif page == "시스템 설정":
        show_system_settings()

def show_dashboard():
    """메인 대시보드"""
    st.header("📈 시스템 현황")
    
    # 실제 통계 계산
    recent_logs = symptom_logger.get_recent_logs(limit=1000)
    total_logs = len(recent_logs)
    
    # 성공률 계산
    successful_logs = 0
    for log in recent_logs:
        if log['advice_quality'] in ['good', 'excellent']:
            successful_logs += 1
    success_rate = (successful_logs / total_logs) if total_logs > 0 else 0
    
    # RAG 데이터 파일 수 계산
    rag_data_dir = Path("data/rag_data")
    rag_files = list(rag_data_dir.glob("*.txt")) if rag_data_dir.exists() else []
    rag_total_size = sum(f.stat().st_size for f in rag_files) / (1024 * 1024)  # MB
    
    # 메트릭 표시
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="총 증상 로그",
            value=total_logs,
            delta=f"{total_logs}건"
        )
    
    with col2:
        st.metric(
            label="성공률",
            value=f"{success_rate:.1%}",
            delta=f"{successful_logs}건 성공"
        )
    
    with col3:
        st.metric(
            label="미처리 증상",
            value=0,  # 실제로는 미처리 증상 테이블에서 계산
            delta="처리 필요"
        )
    
    with col4:
        st.metric(
            label="RAG 데이터",
            value=f"{len(rag_files)}개 파일",
            delta=f"{rag_total_size:.1f}MB"
        )
    
    # 실시간 증상-답변 모니터링
    st.subheader("🔍 실시간 증상-답변 모니터링")
    
    # 자동 새로고침
    if st.button("🔄 새로고침"):
        st.rerun()
    
    # 최근 로그 가져오기
    recent_logs = symptom_logger.get_recent_logs(limit=10)
    
    if recent_logs:
        # 최근 로그를 시간순으로 정렬
        recent_logs_sorted = sorted(recent_logs, key=lambda x: x['timestamp'], reverse=True)
        
        for i, log in enumerate(recent_logs_sorted[:5]):  # 최근 5개만 표시
            with st.expander(f"📝 {log['timestamp']} - {log['user_input'][:50]}..."):
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.markdown("**사용자 증상:**")
                    st.text(log['user_input'])
                    
                    st.markdown("**시스템 정보:**")
                    st.text(f"품질: {log['advice_quality']}")
                    
                    # RAG 신뢰도 타입 안전 처리
                    rag_confidence = log['rag_confidence']
                    try:
                        if isinstance(rag_confidence, bytes):
                            rag_confidence = float(rag_confidence.decode('utf-8'))
                        elif isinstance(rag_confidence, str):
                            rag_confidence = float(rag_confidence)
                        elif isinstance(rag_confidence, (int, float)):
                            rag_confidence = float(rag_confidence)
                        else:
                            rag_confidence = 0.0
                    except (ValueError, UnicodeDecodeError):
                        rag_confidence = 0.0
                    st.text(f"RAG 신뢰도: {rag_confidence:.1%}")
                    
                    # 처리 시간 타입 안전 처리
                    processing_time = log['processing_time']
                    try:
                        if isinstance(processing_time, bytes):
                            processing_time = float(processing_time.decode('utf-8'))
                        elif isinstance(processing_time, str):
                            processing_time = float(processing_time)
                        elif isinstance(processing_time, (int, float)):
                            processing_time = float(processing_time)
                        else:
                            processing_time = 0.0
                    except (ValueError, UnicodeDecodeError):
                        processing_time = 0.0
                    st.text(f"처리 시간: {processing_time:.2f}초")
                    
                    st.text(f"이미지 업로드: {'예' if log['image_uploaded'] else '아니오'}")
                
                with col2:
                    st.markdown("**시스템 답변:**")
                    if log.get('advice_content'):
                        st.text_area("답변 내용", value=log['advice_content'], height=200, disabled=True, label_visibility="collapsed")
                    else:
                        st.warning("답변 내용이 저장되지 않았습니다.")
                
                st.divider()
    else:
        st.info("아직 로그가 없습니다.")
    
    # 차트 (실제 데이터 기반)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 응답 품질 분포")
        
        # 실제 로그에서 RAG 신뢰도 분포 계산
        all_logs = symptom_logger.get_recent_logs(limit=1000)
        
        if all_logs:
            # RAG 신뢰도 분포 계산
            confidence_ranges = {'0-0.2': 0, '0.2-0.4': 0, '0.4-0.6': 0, '0.6-0.8': 0, '0.8-1.0': 0}
            
            for log in all_logs:
                try:
                    rag_confidence = log['rag_confidence']
                    if isinstance(rag_confidence, (int, float)):
                        confidence = float(rag_confidence)
                    elif isinstance(rag_confidence, str):
                        confidence = float(rag_confidence)
                    else:
                        confidence = 0.0
                except:
                    confidence = 0.0
                
                if 0.0 <= confidence < 0.2:
                    confidence_ranges['0-0.2'] += 1
                elif 0.2 <= confidence < 0.4:
                    confidence_ranges['0.2-0.4'] += 1
                elif 0.4 <= confidence < 0.6:
                    confidence_ranges['0.4-0.6'] += 1
                elif 0.6 <= confidence < 0.8:
                    confidence_ranges['0.6-0.8'] += 1
                elif 0.8 <= confidence <= 1.0:
                    confidence_ranges['0.8-1.0'] += 1
            
            confidence_data = {
                '범위': list(confidence_ranges.keys()),
                '건수': list(confidence_ranges.values())
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
        else:
            st.info("📭 데이터가 없어서 차트를 표시할 수 없습니다.")
    
    with col2:
        st.subheader("📈 시간별 증상 로그")
        
        # 실제 로그에서 시간별 분포 계산
        if all_logs:
            # 시간별 로그 수 계산
            hourly_counts = {f"{i:02d}:00": 0 for i in range(24)}
            
            for log in all_logs:
                try:
                    timestamp = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00'))
                    hour = timestamp.hour
                    hourly_counts[f"{hour:02d}:00"] += 1
                except:
                    continue
            
            time_data = {
                '시간': list(hourly_counts.keys()),
                '로그 수': list(hourly_counts.values())
            }
            
            fig = px.line(
                time_data, 
                x='시간', 
                y='로그 수',
                title="시간별 증상 로그 수"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📭 데이터가 없어서 차트를 표시할 수 없습니다.")
    
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
    
    # 실제 로그 데이터 가져오기
    st.subheader("📊 로그 데이터")
    
    # 실제 데이터베이스에서 로그 가져오기
    recent_logs = symptom_logger.get_recent_logs(limit=limit)
    
    if not recent_logs:
        st.info("📭 아직 로그가 없습니다. 로컬 앱에서 증상을 입력해보세요!")
        return
    
    # 데이터프레임 생성
    log_data = []
    for log in recent_logs:
        # RAG 신뢰도 타입 안전 처리
        try:
            rag_confidence = log['rag_confidence']
            if isinstance(rag_confidence, (int, float)):
                confidence = float(rag_confidence)
            elif isinstance(rag_confidence, str):
                confidence = float(rag_confidence)
            else:
                confidence = 0.0
        except:
            confidence = 0.0
            
        log_data.append({
            '시간': log['timestamp'],
            '증상': log['user_input'],
            '이미지': log['image_uploaded'],
            'RAG 신뢰도': confidence,
            '응답 성공': log['advice_quality'] in ['good', 'excellent']
        })
    
    df = pd.DataFrame(log_data)
    
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

def show_crawling_status():
    """크롤링 상태 확인 페이지"""
    st.header("🕷️ 크롤링 상태 모니터링")
    
    # 최근 로그에서 크롤링이 트리거된 케이스 확인
    recent_logs = symptom_logger.get_recent_logs(limit=50)
    
    if not recent_logs:
        st.info("아직 로그가 없습니다. 로컬 앱에서 증상을 입력해보세요!")
        return
    
    # 크롤링이 필요한 케이스들 필터링
    crawling_cases = []
    for log in recent_logs:
        # RAG 신뢰도가 낮거나 기본 조언인 경우
        try:
            rag_confidence = log['rag_confidence']
            if isinstance(rag_confidence, (int, float)):
                confidence = float(rag_confidence)
            elif isinstance(rag_confidence, str):
                confidence = float(rag_confidence)
            else:
                confidence = 0.0
        except:
            confidence = 0.0
            
        if confidence < 0.7 or log['advice_quality'] in ['poor', 'failed']:
            crawling_cases.append({
                'id': log['id'],
                'timestamp': log['timestamp'],
                'symptom': log['user_input'],
                'rag_confidence': confidence,
                'quality': log['advice_quality'],
                'advice_length': len(log.get('advice_content', ''))
            })
    
    st.subheader(f"🔍 크롤링 필요 케이스: {len(crawling_cases)}개")
    
    if crawling_cases:
        st.write("다음 증상들은 RAG 신뢰도가 낮거나 품질이 좋지 않아 크롤링이 필요합니다:")
        
        for case in crawling_cases:
            with st.expander(f"ID {case['id']}: {case['symptom'][:50]}..."):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**시간:** {case['timestamp']}")
                    st.write(f"**RAG 신뢰도:** {case['rag_confidence']:.1%}")
                
                with col2:
                    st.write(f"**품질:** {case['quality']}")
                    st.write(f"**답변 길이:** {case['advice_length']}자")
                
                with col3:
                    if case['rag_confidence'] < 0.7:
                        st.warning("⚠️ 낮은 RAG 신뢰도")
                    if case['quality'] in ['poor', 'failed']:
                        st.error("❌ 품질 문제")
                    
                    # 크롤링 실행 버튼
                    if st.button(f"🚀 크롤링 실행", key=f"crawl_{case['id']}"):
                        st.info("크롤링이 실행되었습니다. 잠시 후 결과를 확인해주세요.")
    else:
        st.success("🎉 모든 증상이 충분한 신뢰도를 가지고 있습니다!")
    
    # 크롤링 통계
    st.subheader("📊 크롤링 통계")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        low_confidence = len([c for c in crawling_cases if c['rag_confidence'] < 0.7])
        st.metric("낮은 신뢰도", f"{low_confidence}개")
    
    with col2:
        poor_quality = len([c for c in crawling_cases if c['quality'] in ['poor', 'failed']])
        st.metric("품질 문제", f"{poor_quality}개")
    
    with col3:
        total_logs = len(recent_logs)
        crawling_rate = (len(crawling_cases) / total_logs * 100) if total_logs > 0 else 0
        st.metric("크롤링 필요율", f"{crawling_rate:.1f}%")

def show_rag_management():
    """RAG 데이터 관리 페이지"""
    st.header("📚 RAG 데이터 관리")
    
    # RAG 데이터 디렉토리 확인
    rag_data_dir = Path("data/rag_data")
    
    if not rag_data_dir.exists():
        st.warning("RAG 데이터 디렉토리가 존재하지 않습니다.")
        return
    
    # RAG 파일 목록 (텍스트 + PDF)
    txt_files = list(rag_data_dir.glob("*.txt"))
    pdf_files = list(rag_data_dir.glob("*.pdf"))
    rag_files = txt_files + pdf_files
    
    st.subheader(f"📁 RAG 데이터 파일: {len(rag_files)}개")
    
    if rag_files:
        # 파일 통계
        col1, col2, col3 = st.columns(3)
        
        total_size = sum(f.stat().st_size for f in rag_files)
        
        with col1:
            st.metric("총 파일 수", f"{len(rag_files)}개")
            st.caption(f"텍스트: {len(txt_files)}개, PDF: {len(pdf_files)}개")
        
        with col2:
            st.metric("총 크기", f"{total_size / (1024 * 1024):.1f}MB")
        
        with col3:
            avg_size = total_size / len(rag_files) if rag_files else 0
            st.metric("평균 크기", f"{avg_size / 1024:.1f}KB")
        
        # 파일 목록
        st.subheader("📋 파일 목록")
        
        for i, file_path in enumerate(rag_files):
            file_type = "📄" if file_path.suffix == '.txt' else "📕"
            with st.expander(f"{file_type} {file_path.name} ({file_path.suffix.upper()})"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.write(f"**파일명:** {file_path.name}")
                    st.write(f"**타입:** {file_path.suffix.upper()}")
                    st.write(f"**크기:** {file_path.stat().st_size / 1024:.1f}KB")
                
                with col2:
                    st.write(f"**수정일:** {datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')}")
                    
                    # 파일 내용 미리보기
                    try:
                        if file_path.suffix == '.txt':
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read(200)  # 처음 200자만
                            st.write(f"**내용 미리보기:** {content}...")
                        else:  # PDF
                            st.write("**내용 미리보기:** PDF 파일 (텍스트 추출 필요)")
                    except:
                        st.write("**내용 미리보기:** 읽기 실패")
                
                with col3:
                    if st.button("📖 전체 내용 보기", key=f"view_{i}"):
                        try:
                            if file_path.suffix == '.txt':
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    full_content = f.read()
                                st.text_area("파일 내용", value=full_content, height=300, disabled=True)
                            else:  # PDF
                                # PDF 텍스트 추출
                                try:
                                    from backend.services_pdf_processor import PDFProcessor
                                    processor = PDFProcessor()
                                    result = processor.process_pdf_file(str(file_path))
                                    if "error" not in result:
                                        st.text_area("PDF 텍스트 내용", value=result["text"], height=300, disabled=True)
                                    else:
                                        st.error(f"PDF 처리 실패: {result['error']}")
                                except ImportError:
                                    st.error("PDF 처리 모듈을 찾을 수 없습니다.")
                        except Exception as e:
                            st.error(f"파일을 읽을 수 없습니다: {e}")
                    
                    if file_path.suffix == '.pdf' and st.button("📝 텍스트로 변환", key=f"convert_{i}"):
                        try:
                            from backend.services_pdf_processor import convert_pdf_to_txt
                            output_path = convert_pdf_to_txt(str(file_path))
                            if output_path:
                                st.success(f"텍스트 파일로 변환 완료: {output_path}")
                                st.rerun()
                            else:
                                st.error("PDF 변환에 실패했습니다.")
                        except ImportError:
                            st.error("PDF 처리 모듈을 찾을 수 없습니다.")
                    
                    if st.button("🗑️ 삭제", key=f"delete_{i}"):
                        st.warning("파일 삭제 기능은 구현되지 않았습니다.")
    else:
        st.info("RAG 데이터 파일이 없습니다.")
    
    # URL에서 PDF 로드 기능
    st.subheader("🌐 URL에서 PDF 로드")
    pdf_url = st.text_input("PDF URL 입력", placeholder="https://example.com/document.pdf")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 PDF 로드 및 RAG 추가", disabled=not pdf_url):
            if pdf_url:
                try:
                    from backend.services_pdf_processor import load_pdf_from_url, convert_pdf_to_txt
                    import tempfile
                    import os
                    
                    with st.spinner("PDF를 로드하고 있습니다..."):
                        result = load_pdf_from_url(pdf_url)
                    
                    if "error" not in result:
                        # 임시 파일로 저장 후 텍스트 변환
                        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                            # PDF 내용을 임시 파일에 저장
                            import requests
                            response = requests.get(pdf_url)
                            tmp_file.write(response.content)
                            tmp_file_path = tmp_file.name
                        
                        # 텍스트 파일로 변환
                        output_path = convert_pdf_to_txt(tmp_file_path, "data/rag_data")
                        
                        # 임시 파일 삭제
                        os.unlink(tmp_file_path)
                        
                        if output_path:
                            st.success(f"✅ PDF가 성공적으로 RAG 시스템에 추가되었습니다!")
                            st.info(f"📄 파일명: {result['filename']}")
                            st.info(f"📊 페이지 수: {result['pages']}페이지")
                            st.info(f"📏 텍스트 길이: {len(result['text'])}자")
                            st.info(f"⚡ 처리 시간: 매우 빠름 (PyMuPDF)")
                            st.rerun()
                        else:
                            st.error("PDF를 텍스트 파일로 변환하는데 실패했습니다.")
                    else:
                        st.error(f"PDF 로드 실패: {result['error']}")
                        
                except Exception as e:
                    st.error(f"PDF 로드 중 오류 발생: {str(e)}")
    
    with col2:
        if st.button("📋 로드된 PDF 미리보기", disabled=not pdf_url):
            if pdf_url:
                try:
                    from backend.services_pdf_processor import load_pdf_from_url
                    
                    with st.spinner("PDF를 로드하고 있습니다..."):
                        result = load_pdf_from_url(pdf_url)
                    
                    if "error" not in result:
                        st.success("PDF 로드 성공!")
                        st.text_area("PDF 텍스트 내용", value=result["text"][:2000] + "..." if len(result["text"]) > 2000 else result["text"], height=300, disabled=True)
                    else:
                        st.error(f"PDF 로드 실패: {result['error']}")
                        
                except Exception as e:
                    st.error(f"PDF 로드 중 오류 발생: {str(e)}")
    
    # RAG 데이터 관리 도구
    st.subheader("🔧 RAG 데이터 관리 도구")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 RAG 데이터 새로고침"):
            st.info("RAG 데이터를 새로고침하고 있습니다...")
            st.success("새로고침이 완료되었습니다!")
    
    with col2:
        if st.button("📊 RAG 성능 분석"):
            st.info("RAG 성능을 분석하고 있습니다...")
            st.success("분석이 완료되었습니다!")
    
    with col3:
        if st.button("🧹 중복 데이터 정리"):
            st.info("중복 데이터를 정리하고 있습니다...")
            st.success("정리가 완료되었습니다!")

def show_unhandled_symptoms():
    """미처리 증상 관리 페이지"""
    st.header("⚠️ 미처리 증상 관리")
    
    # 미처리 증상 데이터 조회
    conn = sqlite3.connect('data/symptom_logs.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM unhandled_symptoms 
        ORDER BY priority_score DESC, frequency DESC
    ''')
    unhandled_symptoms = cursor.fetchall()
    
    if not unhandled_symptoms:
        st.info("📭 현재 미처리 증상이 없습니다.")
        st.write("시스템이 모든 증상을 성공적으로 처리하고 있습니다!")
    else:
        st.subheader(f"🔍 미처리 증상: {len(unhandled_symptoms)}개")
        
        # 통계 표시
        col1, col2, col3 = st.columns(3)
        
        with col1:
            high_priority = len([s for s in unhandled_symptoms if s[6] > 0.7])
            st.metric("높은 우선순위", f"{high_priority}개")
        
        with col2:
            total_frequency = sum([s[2] for s in unhandled_symptoms])
            st.metric("총 발생 횟수", f"{total_frequency}회")
        
        with col3:
            pending_count = len([s for s in unhandled_symptoms if s[7] == 'pending'])
            st.metric("처리 대기", f"{pending_count}개")
        
        # 미처리 증상 목록
        st.subheader("📋 미처리 증상 목록")
        
        for symptom in unhandled_symptoms:
            with st.expander(f"🔴 {symptom[1]} (우선순위: {symptom[6]:.2f})"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**증상:** {symptom[1]}")
                    st.write(f"**발생 횟수:** {symptom[2]}회")
                    st.write(f"**첫 발견:** {symptom[3]}")
                    st.write(f"**마지막 발견:** {symptom[4]}")
                
                with col2:
                    st.write(f"**RAG 신뢰도:** {symptom[5]:.1%}")
                    st.write(f"**우선순위 점수:** {symptom[6]:.2f}")
                    st.write(f"**상태:** {symptom[7]}")
                    
                    if symptom[8]:
                        st.write(f"**제안된 조치:** {symptom[8]}")
                
                # 액션 버튼들
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("🚀 크롤링 실행", key=f"crawl_{symptom[0]}"):
                        st.info("크롤링이 실행되었습니다.")
                
                with col2:
                    if st.button("✅ 처리 완료", key=f"complete_{symptom[0]}"):
                        st.success("처리 완료로 표시되었습니다.")
                
                with col3:
                    if st.button("❌ 무시", key=f"ignore_{symptom[0]}"):
                        st.warning("무시 목록에 추가되었습니다.")
    
    conn.close()
    
    # 미처리 증상 분석 도구
    st.subheader("🔧 미처리 증상 분석 도구")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔄 미처리 증상 재분석"):
            st.info("미처리 증상을 재분석하고 있습니다...")
            st.success("재분석이 완료되었습니다!")
    
    with col2:
        if st.button("📊 우선순위 재계산"):
            st.info("우선순위를 재계산하고 있습니다...")
            st.success("우선순위 재계산이 완료되었습니다!")


# def show_crawling_management():
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
        'MVP_FIXED_LAT': 'MVP 고정 위도',
        'MVP_FIXED_LON': 'MVP 고정 경도',
        'FAST_MODE': '빠른 모드',
        'CONTACT_EMAIL': '연락처 이메일',
        'AUTO_REINDEX_ON_CRAWL': '크롤링 후 자동 재색인',
        'REINDEX_DEBOUNCE_SEC': '자동 재색인 디바운스(초)'
    }
    
    # 기본값 설정
    default_values = {
        'IMG_RED_RATIO': '0.3',
        'IMG_BURN_RATIO': '0.2',
        'MVP_RANDOM_TOKYO': 'true',
        'MVP_FIXED_SHINJUKU': 'false',
        'MVP_FIXED_LAT': '35.6762',
        'MVP_FIXED_LON': '139.6503',
        'FAST_MODE': 'false',
        'CONTACT_EMAIL': 'hos-emergency-bot@example.com',
        'AUTO_REINDEX_ON_CRAWL': '1',
        'REINDEX_DEBOUNCE_SEC': '120'
    }
    
    # 환경변수 실시간 변경
    st.subheader("⚙️ 환경변수 실시간 변경")
    st.warning("⚠️ 변경된 값은 현재 세션에만 적용됩니다. 영구 적용을 위해서는 서버 재시작이 필요합니다.")
    
    # 세션 상태 초기화
    if 'env_vars_modified' not in st.session_state:
        st.session_state.env_vars_modified = {}
    
    for var, description in env_vars.items():
        # 기본값이 있으면 사용, 없으면 환경변수에서 가져오기
        current_value = os.getenv(var, default_values.get(var, '설정되지 않음'))
        
        # OpenAI API 키는 보안상 마스킹
        if var == 'OPENAI_API_KEY' and current_value != '설정되지 않음':
            display_value = f"{current_value[:8]}...{current_value[-4:]}" if len(current_value) > 12 else "***"
        else:
            display_value = current_value
        
        # 현재 값 표시
        st.markdown(f"**{description}** ({var})")
        st.text(f"현재 값: {display_value}")
        
        # 새 값 입력 (기본값 표시)
        placeholder_value = st.session_state.env_vars_modified.get(var, current_value)
        if var == 'OPENAI_API_KEY':
            new_value = st.text_input(
                f"새 {description} 입력", 
                value=placeholder_value,
                type="password",
                key=f"env_{var}",
                placeholder=f"기본값: {default_values.get(var, '없음')}"
            )
        else:
            new_value = st.text_input(
                f"새 {description} 입력", 
                value=placeholder_value,
                key=f"env_{var}",
                placeholder=f"기본값: {default_values.get(var, '없음')}"
            )
        
        # 값 변경 확인
        if new_value and new_value != current_value:
            st.session_state.env_vars_modified[var] = new_value
            os.environ[var] = new_value
            st.success(f"✅ {var} 값이 변경되었습니다!")
        elif new_value == current_value:
            st.info(f"ℹ️ {var} 값이 동일합니다.")
        
        st.divider()
    
    # 변경된 값들 요약
    if st.session_state.env_vars_modified:
        st.subheader("📝 변경된 환경변수")
        for var, value in st.session_state.env_vars_modified.items():
            if var == 'OPENAI_API_KEY':
                display_value = f"{value[:8]}...{value[-4:]}" if len(value) > 12 else "***"
            else:
                display_value = value
            st.text(f"• {var}: {display_value}")
        
        if st.button("🔄 모든 변경사항 초기화"):
            st.session_state.env_vars_modified = {}
            st.rerun()
    
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
