"""
자동 크롤링 시스템
미처리 증상을 기반으로 자동으로 의료 데이터를 크롤링합니다.
"""

import asyncio
import json
import os
import re
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .services_logging import symptom_logger

class AutoCrawler:
    """자동 크롤링 클래스"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # 크롤링 대상 사이트들
        self.target_sites = {
            'mhlw': {
                'name': '厚生労働省 (MHLW)',
                'base_url': 'https://www.mhlw.go.jp',
                'search_url': 'https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/kyukyu.html',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, div.content',
                    'links': 'a[href*="kyukyu"]'
                }
            },
            'jma': {
                'name': '日本医師会 (JMA)',
                'base_url': 'https://www.med.or.jp',
                'search_url': 'https://www.med.or.jp/doctor/teireikaiken/',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, div.content',
                    'links': 'a[href*="teireikaiken"]'
                }
            },
            'jrc': {
                'name': '日本赤十字社 (JRC)',
                'base_url': 'https://www.jrc.or.jp',
                'search_url': 'https://www.jrc.or.jp/study/kind/emergency/',
                'selectors': {
                    'title': 'h1, h2, h3',
                    'content': 'p, li, div.content',
                    'links': 'a[href*="emergency"]'
                }
            }
        }
    
    def extract_keywords(self, symptom_text: str) -> List[str]:
        """증상 텍스트에서 키워드를 추출합니다."""
        # 일본어 의료 키워드 패턴
        medical_patterns = [
            r'[あ-ん]+',  # 히라가나
            r'[ア-ン]+',  # 가타카나
            r'[一-龯]+',  # 한자
        ]
        
        keywords = []
        for pattern in medical_patterns:
            matches = re.findall(pattern, symptom_text)
            keywords.extend(matches)
        
        # 영어 의료 용어도 포함
        english_words = re.findall(r'[a-zA-Z]+', symptom_text)
        keywords.extend(english_words)
        
        # 중복 제거 및 길이 필터링
        keywords = list(set([kw for kw in keywords if len(kw) >= 2]))
        
        return keywords
    
    def search_site(self, site_key: str, keywords: List[str]) -> List[Dict]:
        """특정 사이트에서 키워드로 검색합니다."""
        site_config = self.target_sites[site_key]
        results = []
        
        try:
            # 검색 URL 구성
            search_url = site_config['search_url']
            
            # 페이지 내용 가져오기
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 제목과 내용 추출
            titles = soup.select(site_config['selectors']['title'])
            contents = soup.select(site_config['selectors']['content'])
            links = soup.select(site_config['selectors']['links'])
            
            # 키워드 매칭으로 관련 내용 필터링
            for i, title in enumerate(titles):
                title_text = title.get_text().strip()
                if any(keyword in title_text for keyword in keywords):
                    # 관련 링크 찾기
                    related_links = []
                    for link in links:
                        link_text = link.get_text().strip()
                        if any(keyword in link_text for keyword in keywords):
                            href = link.get('href')
                            if href:
                                if href.startswith('/'):
                                    href = site_config['base_url'] + href
                                related_links.append({
                                    'text': link_text,
                                    'url': href
                                })
                    
                    # 내용 추출
                    content_text = ""
                    if i < len(contents):
                        content_text = contents[i].get_text().strip()
                    
                    results.append({
                        'site': site_key,
                        'title': title_text,
                        'content': content_text,
                        'links': related_links,
                        'url': search_url,
                        'keywords_matched': [kw for kw in keywords if kw in title_text]
                    })
            
        except Exception as e:
            print(f"Error crawling {site_key}: {e}")
        
        return results
    
    def crawl_for_symptoms(self, symptom_text: str) -> Dict:
        """증상에 대한 크롤링을 수행합니다."""
        keywords = self.extract_keywords(symptom_text)
        
        if not keywords:
            return {
                'success': False,
                'error': 'No keywords extracted',
                'results': []
            }
        
        all_results = []
        
        # 각 사이트에서 크롤링
        for site_key in self.target_sites.keys():
            try:
                site_results = self.search_site(site_key, keywords)
                all_results.extend(site_results)
            except Exception as e:
                print(f"Error crawling {site_key}: {e}")
                continue
        
        return {
            'success': True,
            'keywords': keywords,
            'results': all_results,
            'total_results': len(all_results)
        }
    
    def save_crawled_data(self, symptom_text: str, crawl_results: Dict) -> str:
        """크롤링된 데이터를 파일로 저장합니다."""
        if not crawl_results['success']:
            return None
        
        # 데이터 디렉토리 생성
        data_dir = Path("data/passages/jp")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성 (타임스탬프 + 증상)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_symptom = re.sub(r'[^\w\s-]', '', symptom_text)[:20]
        filename = f"{timestamp}_{safe_symptom}.txt"
        filepath = data_dir / filename
        
        # 데이터 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# 증상: {symptom_text}\n")
            f.write(f"# 크롤링 시간: {datetime.now().isoformat()}\n")
            f.write(f"# 키워드: {', '.join(crawl_results['keywords'])}\n\n")
            
            for result in crawl_results['results']:
                f.write(f"## {result['site']} - {result['title']}\n")
                f.write(f"URL: {result['url']}\n")
                f.write(f"매칭 키워드: {', '.join(result['keywords_matched'])}\n\n")
                
                if result['content']:
                    f.write(f"{result['content']}\n\n")
                
                if result['links']:
                    f.write("관련 링크:\n")
                    for link in result['links']:
                        f.write(f"- {link['text']}: {link['url']}\n")
                    f.write("\n")
                
                f.write("-" * 50 + "\n\n")
        
        return str(filepath)
    
    def process_unhandled_symptoms(self, limit: int = 5) -> Dict:
        """미처리 증상들을 처리합니다."""
        unhandled = symptom_logger.get_unhandled_symptoms(limit)
        
        if not unhandled:
            return {
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'results': []
            }
        
        results = []
        successful = 0
        failed = 0
        
        for symptom in unhandled:
            symptom_text = symptom['symptom_text']
            
            # 크롤링 작업 생성
            keywords = self.extract_keywords(symptom_text)
            job_id = symptom_logger.create_crawling_job(
                keywords, 
                list(self.target_sites.keys())
            )
            
            try:
                # 크롤링 시작
                symptom_logger.update_crawling_job(job_id, 'started')
                
                # 크롤링 수행
                crawl_results = self.crawl_for_symptoms(symptom_text)
                
                if crawl_results['success'] and crawl_results['results']:
                    # 데이터 저장
                    filepath = self.save_crawled_data(symptom_text, crawl_results)
                    
                    if filepath:
                        # 작업 완료
                        symptom_logger.update_crawling_job(
                            job_id, 'completed', 
                            len(crawl_results['results'])
                        )
                        
                        # 미처리 증상 상태 업데이트
                        self._update_symptom_status(symptom_text, 'processed')
                        
                        successful += 1
                        results.append({
                            'symptom': symptom_text,
                            'status': 'success',
                            'filepath': filepath,
                            'results_count': len(crawl_results['results'])
                        })
                    else:
                        raise Exception("Failed to save data")
                else:
                    raise Exception("No results found")
                    
            except Exception as e:
                # 작업 실패
                symptom_logger.update_crawling_job(
                    job_id, 'failed', 0, str(e)
                )
                
                failed += 1
                results.append({
                    'symptom': symptom_text,
                    'status': 'failed',
                    'error': str(e)
                })
            
            # 요청 간격 조절
            time.sleep(2)
        
        return {
            'processed': len(unhandled),
            'successful': successful,
            'failed': failed,
            'results': results
        }
    
    def _update_symptom_status(self, symptom_text: str, status: str):
        """미처리 증상 상태를 업데이트합니다."""
        import sqlite3
        
        conn = sqlite3.connect(symptom_logger.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE unhandled_symptoms 
            SET status = ? 
            WHERE symptom_text = ?
        """, (status, symptom_text))
        
        conn.commit()
        conn.close()

# 전역 크롤러 인스턴스
auto_crawler = AutoCrawler()
