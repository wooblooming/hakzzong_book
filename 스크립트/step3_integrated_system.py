#!/usr/bin/env python3.11
"""
고등학생 탐구주제 도서 추천 시스템 (통합 버전 - 고도화됨)
- Gemini 1.5 Pro (키워드 추출 + 지능형 평가) + 1.5 Pro (LLM 검증)
- 네이버 도서 API 연동
- 병렬 처리 (5개씩)
- 체크포인트 저장 및 재시작 기능
- 상세한 추천 이유 생성
- 개선된 검색 및 필터링 시스템
- step4의 지능형 분석 시스템 통합
"""

import pandas as pd
import json
import re
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime, timedelta
import time
import requests
from typing import Dict, List, Tuple, Optional
from collections import Counter
import concurrent.futures
import threading
from pathlib import Path
import random
from functools import wraps

# 환경 변수 로드 (상대 경로 지정)
load_dotenv('../설정파일/.env')

class APIQuotaExceededException(Exception):
    """API 호출 한도 초과 예외"""
    def __init__(self, message="API 호출 한도가 초과되었습니다"):
        self.message = message
        super().__init__(self.message)

def retry_with_exponential_backoff(max_retries: int = 3, base_delay: float = 1.0):
    """지수 백오프를 사용한 재시도 데코레이터"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except APIQuotaExceededException:
                    # API 한도 초과는 재시도하지 않고 즉시 전파
                    raise
                except Exception as e:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                        print(f"  ⚠️ 시도 {attempt + 1}/{max_retries} 실패: {str(e)[:50]}...")
                        print(f"  ⏳ {delay:.1f}초 후 재시도...")
                        time.sleep(delay)
                    else:
                        print(f"  ❌ 최종 실패: {str(e)}")
                        raise e
            return None
        return wrapper
    return decorator

def format_time_remaining(seconds: float) -> str:
    """초를 시:분:초 형태로 변환"""
    if seconds < 0:
        return "계산 중..."
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}시간 {minutes}분 {seconds}초"
    elif minutes > 0:
        return f"{minutes}분 {seconds}초"
    else:
        return f"{seconds}초"

class APIUsageTracker:
    """API 사용량 및 비용 추적 클래스"""
    
    def __init__(self):
        self.usage_log = []
        self.total_cost = 0.0
        self.lock = threading.Lock()  # 스레드 안전성을 위한 락
        self.naver_api_calls = 0  # 네이버 API 호출 횟수 (현재 실제 사용량으로 초기화)
        self.daily_limit = 25000  # 네이버 API 일일 한도
        
        # Gemini API 가격 (2024년 12월 기준, USD per 1M tokens)
        self.pricing = {
            'gemini-1.5-pro': {
                'input': 0.50,
                'output': 1.50
            },
            'gemini-1.5-flash': {
                'input': 0.075,
                'output': 0.30
            },
            'gemini-2.5-pro-preview': {
                'input': 1.25,    # $1.25 per 1M input tokens
                'output': 10.00   # $10.00 per 1M output tokens
            }
        }
    
    def increment_naver_api_call(self):
        """네이버 API 호출 횟수 증가 및 한도 확인"""
        with self.lock:
            self.naver_api_calls += 1
            
            # 경고 메시지
            if self.naver_api_calls == 20000:
                print(f"\n⚠️ 네이버 API 호출 20,000회 도달! (한도의 80%)")
                print(f"🔄 남은 호출: 약 {self.daily_limit - self.naver_api_calls:,}회")
            elif self.naver_api_calls == 24000:
                print(f"\n🚨 네이버 API 호출 24,000회 도달! (한도의 96%)")
                print(f"⚠️ 남은 호출: 약 {self.daily_limit - self.naver_api_calls:,}회 - 주의!")
            
            return self.naver_api_calls
    
    def get_naver_api_usage_info(self):
        """네이버 API 사용량 정보 반환"""
        with self.lock:
            usage_percentage = (self.naver_api_calls / self.daily_limit) * 100
            remaining = self.daily_limit - self.naver_api_calls
            
            return {
                'calls_made': self.naver_api_calls,
                'daily_limit': self.daily_limit,
                'usage_percentage': usage_percentage,
                'remaining_calls': remaining,
                'estimated_topics_remaining': remaining // 4  # 주제당 평균 4회 호출
            }
    
    def estimate_tokens(self, text: str) -> int:
        """토큰 수 추정 (한국어 기준)"""
        # 한국어: 평균 1.5-2자 = 1토큰
        # 영어: 평균 4글자 = 1토큰
        korean_chars = len(re.findall(r'[가-힣]', text))
        other_chars = len(text) - korean_chars
        
        estimated_tokens = (korean_chars // 2) + (other_chars // 4)
        return max(estimated_tokens, len(text.split()) // 2)  # 최소값 보장
    
    def log_api_call(self, model: str, input_text: str, output_text: str, 
                     call_type: str = "general"):
        """API 호출 로그 및 비용 계산"""
        with self.lock:
            input_tokens = self.estimate_tokens(input_text)
            output_tokens = self.estimate_tokens(output_text)
            
            # 비용 계산
            if model in self.pricing:
                input_cost = (input_tokens / 1_000_000) * self.pricing[model]['input']
                output_cost = (output_tokens / 1_000_000) * self.pricing[model]['output']
                total_cost = input_cost + output_cost
            else:
                total_cost = 0.0
            
            self.total_cost += total_cost
            
            # 로그 기록
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'model': model,
                'call_type': call_type,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'cost_usd': total_cost,
                'cost_krw': total_cost * 1300  # 환율 적용
            }
            self.usage_log.append(log_entry)
    
    def save_usage_report(self, filename: str = None):
        """사용량 리포트 저장"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f'../결과파일/api_usage_report_{timestamp}.txt'
        
        # 모델별 통계
        model_stats = {}
        for log in self.usage_log:
            model = log['model']
            if model not in model_stats:
                model_stats[model] = {
                    'calls': 0,
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'cost': 0.0
                }
            model_stats[model]['calls'] += 1
            model_stats[model]['input_tokens'] += log['input_tokens']
            model_stats[model]['output_tokens'] += log['output_tokens']
            model_stats[model]['cost'] += log['cost_usd']
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("Gemini API 사용량 및 비용 리포트\n")
            f.write("=" * 80 + "\n")
            f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"총 API 호출 수: {len(self.usage_log)}회\n")
            f.write(f"총 예상 비용: ${self.total_cost:.4f} USD (₩{self.total_cost * 1300:.0f})\n\n")
            
            f.write("모델별 사용량 통계:\n")
            f.write("-" * 50 + "\n")
            for model, stats in model_stats.items():
                f.write(f"• {model}:\n")
                f.write(f"  - 호출 수: {stats['calls']}회\n")
                f.write(f"  - Input 토큰: {stats['input_tokens']:,}개\n")
                f.write(f"  - Output 토큰: {stats['output_tokens']:,}개\n")
                f.write(f"  - 비용: ${stats['cost']:.4f} USD (₩{stats['cost'] * 1300:.0f})\n\n")
            
            f.write("상세 API 호출 로그:\n")
            f.write("-" * 50 + "\n")
            for log in self.usage_log:
                f.write(f"[{log['timestamp']}] {log['model']} ({log['call_type']})\n")
                f.write(f"  토큰: {log['input_tokens']}→{log['output_tokens']} | 비용: ${log['cost_usd']:.4f}\n")
        
        print(f"📊 API 사용량 리포트 저장: {filename}")
        return filename


class EnhancedBookRecommendationSystem:
    """고도화된 도서 추천 시스템 (step4 기능 통합)"""
    
    def __init__(self, input_file: str = None):
        """시스템 초기화"""
        # API 키 설정
        self.gemini_api_key = os.getenv('GOOGLE_API_KEY')
        self.naver_client_id = os.getenv('NAVER_CLIENT_ID')
        self.naver_client_secret = os.getenv('NAVER_CLIENT_SECRET')
        
        if not self.gemini_api_key:
            raise ValueError("GOOGLE_API_KEY가 .env 파일에 설정되지 않았습니다.")
        if not self.naver_client_id or not self.naver_client_secret:
            raise ValueError("네이버 API 키가 .env 파일에 설정되지 않았습니다.")
        
        # Gemini API 설정
        genai.configure(api_key=self.gemini_api_key)
        
        # 두 개의 모델 초기화
        self.keyword_model = genai.GenerativeModel('gemini-1.5-pro')     # 키워드 추출용
        self.verification_model = genai.GenerativeModel('gemini-1.5-pro')  # 도서 검증용
        
        print("✅ Gemini 1.5 Pro (키워드 추출 + 지능형 평가) + 1.5 Pro (도서 검증) 로드 완료")
        
        # API 사용량 추적기
        self.api_tracker = APIUsageTracker()
        
        # 고등학생 적합도 키워드
        self.suitable_keywords = [
            '고등학생', '청소년', '입문', '기초', '쉬운', '이해하기', '개론', 
            '교양', '학습', '공부', '수험생', '대학', '진로', '미래'
        ]
        self.unsuitable_keywords = [
            '대학원', '박사', '석사', '전문가', '고급', '심화', '연구자', 
            '학술논문', '이론서', '전공서적'
        ]
        
        # 부적합 도서 필터링 키워드
        self.irrelevant_keywords = [
            '소설', '에세이', '시집', '자기계발', '성공', '행복', '사랑', '연애',
            '요리', '여행', '문학', '수필', '칼럼', '만화', '웹툰', '게임'
        ]
        
        self.processed_count = 0
        self.total_count = 0
        
        # 입력 파일 기반 파일명 설정
        if input_file:
            # 입력 파일명에서 확장자 제거
            base_filename = os.path.splitext(os.path.basename(input_file))[0]
            self.base_filename = base_filename
            # 체크포인트 파일명도 입력 파일 기반으로 설정
            self.checkpoint_file = f'../결과파일/checkpoint_{base_filename}.json'
        else:
            self.base_filename = 'default'
            self.checkpoint_file = '../결과파일/checkpoint_progress.json'
        
        self.current_results = []
    
    @retry_with_exponential_backoff(max_retries=3, base_delay=0.5)
    def search_naver_books(self, query: str, display: int = 10) -> List[Dict]:
        """네이버 도서 API를 사용하여 도서 검색"""
        url = "https://openapi.naver.com/v1/search/book.json"
        headers = {
            'X-Naver-Client-Id': self.naver_client_id,
            'X-Naver-Client-Secret': self.naver_client_secret
        }
        params = {
            'query': query,
            'display': display,
            'sort': 'sim'  # 정확도순
        }
        
        # 실제 네이버 API 응답으로만 할당량 체크 (내부 카운터 체크 제거)
        
        try:
            response = requests.get(url, headers=headers, params=params)
            
            # API 호출 횟수 추적
            self.api_tracker.increment_naver_api_call()
            
            # HTTP 429 에러 체크 (할당량 초과)
            if response.status_code == 429:
                raise APIQuotaExceededException(
                    f"네이버 API 호출 한도가 초과되었습니다. HTTP 429 에러 발생."
                )
            
            response.raise_for_status()  # 다른 HTTP 에러 체크
            data = response.json()
            
        except APIQuotaExceededException:
            raise  # API 할당량 초과는 재시도하지 않고 바로 전파
        except Exception as e:
            print(f"  네이버 API 호출 오류: {str(e)}")
            raise
        
        if 'items' in data:
            books = []
            for item in data['items']:
                # HTML 태그 제거
                title = re.sub(r'<[^>]+>', '', item.get('title', ''))
                author = re.sub(r'<[^>]+>', '', item.get('author', ''))
                publisher = re.sub(r'<[^>]+>', '', item.get('publisher', ''))
                description = re.sub(r'<[^>]+>', '', item.get('description', ''))
                
                # 사전 필터링: 학술적 관련성 체크
                if not self.is_academically_relevant(title, description, '', []): # academic_field 정보가 없으므로 빈 문자열로 대체
                    continue
                
                book_info = {
                    'title': title,
                    'author': author,
                    'publisher': publisher,
                    'pubdate': item.get('pubdate', ''),
                    'isbn': item.get('isbn', ''),
                    'description': description,
                    'image': item.get('image', ''),
                    'search_keyword': query,
                    'enhanced_query': self.create_enhanced_search_query(query, '') # enhanced_query는 현재 사용되지 않으므로 빈 문자열로 대체
                }
                books.append(book_info)
            return books
        else:
            print(f"  네이버 API 검색 결과 없음: {query}")
            return []
    
    @retry_with_exponential_backoff(max_retries=3, base_delay=1.0)
    def analyze_topic_with_llm(self, topic: str) -> Dict:
        """LLM을 사용한 심층적 주제 분석 및 검색 전략 수립 (step4 기능 통합)"""
        prompt = f"""
다음 고등학생 탐구주제를 분석하여 도서 검색 전략을 수립해주세요:

주제: "{topic}"

다음 형식으로 분석 결과를 JSON으로 제공해주세요:

{{
    "topic_summary": "주제 요약 (한 문장)",
    "core_concepts": ["핵심 개념1", "핵심 개념2", "핵심 개념3"],
    "academic_field": "주요 학문 분야",
    "difficulty_level": "입문/중급/고급",
    "search_strategy": {{
        "primary_keywords": ["1차 검색어1", "1차 검색어2", "1차 검색어3"],
        "secondary_keywords": ["2차 검색어1", "2차 검색어2"],
        "alternative_keywords": ["대안 검색어1", "대안 검색어2"],
        "book_types": ["적합한 도서 유형1", "적합한 도서 유형2"]
    }},
    "expected_difficulty": "도서 찾기 난이도 (쉬움/보통/어려움)",
    "quality_guidelines": "도서 선정 시 품질 기준",
    "search_tips": "검색 시 주의사항이나 팁"
}}

고등학생 수준에 적합한 도서를 찾는 것이 목표입니다.
반드시 JSON 형식으로만 응답해주세요.
"""
        
        response = self.keyword_model.generate_content(prompt)
        
        # API 사용량 기록
        self.api_tracker.log_api_call(
            'gemini-1.5-pro', 
            prompt, 
            response.text, 
            'topic_analysis'
        )
        
        # JSON 파싱
        content = response.text.strip()
        if content.startswith('```json'):
            content = content[7:-3].strip()
        elif content.startswith('```'):
            content = content[3:-3].strip()
        
        analysis = json.loads(content)
        return analysis
    
    def search_books_with_strategy(self, analysis: Dict, max_books: int = 15) -> List[Dict]:
        """다단계 검색 전략을 사용한 도서 검색 (step4 기능 통합)"""
        all_books = []
        search_strategy = analysis.get('search_strategy', {})
        successful_searches = 0
        failed_searches = 0
        
        try:
            # 1단계: Primary keywords 검색
            primary_keywords = search_strategy.get('primary_keywords', [])
            for keyword in primary_keywords:
                try:
                    books = self.search_naver_books(keyword, display=5)
                    all_books.extend(books)
                    successful_searches += 1
                except Exception:
                    failed_searches += 1
                    continue
            
            # 2단계: Secondary keywords 검색 (필요시)
            if len(all_books) < max_books // 2:
                secondary_keywords = search_strategy.get('secondary_keywords', [])
                for keyword in secondary_keywords:
                    try:
                        books = self.search_naver_books(keyword, display=5)
                        all_books.extend(books)
                        successful_searches += 1
                    except Exception:
                        failed_searches += 1
                        continue
            
            # 3단계: Alternative keywords 검색 (필요시)
            if len(all_books) < max_books // 3:
                alternative_keywords = search_strategy.get('alternative_keywords', [])
                for keyword in alternative_keywords:
                    try:
                        books = self.search_naver_books(keyword, display=5)
                        all_books.extend(books)
                        successful_searches += 1
                    except Exception:
                        failed_searches += 1
                        continue
            
            # 중복 제거
            unique_books = self.remove_duplicates(all_books)
            
            # 검색 요약 (실패가 많을 때만 표시)
            if failed_searches > successful_searches:
                print(f"   ⚠️ 검색 제한: 성공 {successful_searches}회, 실패 {failed_searches}회")
            
            # 최대 개수 제한
            return unique_books[:max_books]
            
        except Exception as e:
            # 기본 검색 시도 (조용히)
            try:
                core_concepts = analysis.get('core_concepts', [])
                if core_concepts:
                    return self.search_naver_books(core_concepts[0], display=10)
                else:
                    return []
            except Exception:
                return []
    
    def remove_duplicates(self, books: List[Dict]) -> List[Dict]:
        """중복 도서 제거"""
        unique_books = []
        seen_isbns = set()
        seen_titles = set()
        
        for book in books:
            isbn = book.get('isbn', '')
            title = book.get('title', '')
            
            # ISBN이 있으면 ISBN으로 중복 체크
            if isbn and isbn not in seen_isbns:
                unique_books.append(book)
                seen_isbns.add(isbn)
                seen_titles.add(title)
            # ISBN이 없으면 제목으로 중복 체크
            elif not isbn and title not in seen_titles:
                unique_books.append(book)
                seen_titles.add(title)
        
        return unique_books
    
    @retry_with_exponential_backoff(max_retries=3, base_delay=1.0)
    def intelligent_book_evaluation(self, topic: str, books: List[Dict], analysis: Dict) -> Dict:
        """LLM 기반 지능형 도서 평가 (step4 기능 통합 + 기존 점수 시스템)"""
        if not books:
            return {
                "evaluation_summary": "검색된 도서가 없습니다",
                "recommendation_decision": "추천불가",
                "recommended_books": []
            }
        
        # 도서 목록을 텍스트로 변환
        books_text = ""
        for i, book in enumerate(books, 1):
            books_text += f"{i}. 제목: {book['title']}\n"
            books_text += f"   저자: {book['author']}\n"
            books_text += f"   출판사: {book['publisher']}\n"
            books_text += f"   출간일: {book.get('pubdate', '')}\n"
            books_text += f"   설명: {book.get('description', '')[:200]}...\n\n"
        
        prompt = f"""
고등학생 탐구주제: "{topic}"

주제 분석 결과:
- 핵심 개념: {', '.join(analysis.get('core_concepts', []))}
- 학문 분야: {analysis.get('academic_field', '')}
- 난이도: {analysis.get('difficulty_level', '')}
- 품질 기준: {analysis.get('quality_guidelines', '')}

다음 도서들을 평가해주세요:

{books_text}

평가 기준:
1. 주제 관련성 (매우 높음/높음/보통/낮음/매우 낮음)
2. 고등학생 적합성 (매우 적합/적합/보통/부적합/매우 부적합)
3. 학술적 가치 (높음/보통/낮음)
4. 접근 용이성 (쉬움/보통/어려움)

다음 형식으로 응답해주세요:

{{
    "evaluation_summary": "전체 도서 품질에 대한 한 줄 평가",
    "recommendation_decision": "추천/조건부추천/추천불가",
    "recommended_books": [
        {{
            "book_number": 1,
            "title": "도서명",
            "relevance_level": "관련성 수준",
            "appropriateness_level": "적합성 수준",
            "academic_value": "학술적 가치",
            "accessibility": "접근 용이성",
            "recommendation_reason": "추천 이유 (200-250자)",
            "quality_rating": "A/B/C/D/F"
        }}
    ]
}}

- 최대 2권까지만 추천
- 관련성이 어느 정도 있는 도서는 적극적으로 추천
- 완벽하지 않더라도 학습에 도움이 될 수 있는 도서는 조건부추천
- 조건부추천: 직접적이지 않더라도 참고할 만한 가치가 있는 도서
- 고등학생이 이해할 수 있는 수준이라면 적극 고려
"""
# - 정말 적합한 도서가 없다면 솔직히 "추천불가"로 판정
# - 억지로 추천하지 말고 품질을 우선시
# - 조건부추천: 완벽하지 않지만 참고할만한 도서        
        try:
            response = self.verification_model.generate_content(prompt)
            
            # API 사용량 기록
            self.api_tracker.log_api_call(
                'gemini-1.5-pro', 
                prompt, 
                response.text, 
                'intelligent_evaluation'
            )
            
            # JSON 파싱
            content = response.text.strip()
            if content.startswith('```json'):
                content = content[7:-3].strip()
            elif content.startswith('```'):
                content = content[3:-3].strip()
            
            return json.loads(content)
            
        except Exception as e:
            print(f"  ⚠️ 지능형 평가 실패: {e}")
            # 오류 발생 시 추천불가로 처리 (시스템 오류 메시지 제거)
            return {
                "evaluation_summary": "평가 중 오류가 발생하여 추천할 수 없습니다",
                "recommendation_decision": "추천불가",
                "recommended_books": []
            }
    
    def extract_keywords_with_gemini(self, topic: str) -> Tuple[List[str], Dict]:
        """Gemini 1.5 Pro를 사용하여 키워드 추출 (기존 방식과 호환)"""
        try:
            # 새로운 분석 방식 사용
            analysis = self.analyze_topic_with_llm(topic)
            
            # 기존 형식으로 변환
            search_strategy = analysis.get('search_strategy', {})
            all_keywords = []
            all_keywords.extend(search_strategy.get('primary_keywords', []))
            all_keywords.extend(search_strategy.get('secondary_keywords', []))
            all_keywords.extend(search_strategy.get('alternative_keywords', []))
            
            # 중복 제거
            unique_keywords = list(dict.fromkeys(all_keywords))
            
            return unique_keywords, analysis
            
        except Exception as e:
            print(f"  ⚠️ 키워드 추출 실패 (기본 분석 사용): {e}")
            # 기본 분석 반환
            return [topic], {
                "topic_summary": topic[:100],
                "core_concepts": [topic.split()[0] if topic.split() else "연구"],
                "academic_field": "일반",
                "difficulty_level": "중급",
                "search_strategy": {
                    "primary_keywords": [topic],
                    "secondary_keywords": [],
                    "alternative_keywords": [],
                    "book_types": ["교양서", "입문서"]
                },
                "expected_difficulty": "보통",
                "quality_guidelines": "고등학생 수준에 적합한 도서",
                "search_tips": "기본적인 검색 수행"
            }

    def create_enhanced_search_query(self, keyword: str, academic_field: str) -> str:
        """학문분야를 고려한 향상된 검색 쿼리 생성"""
        # 학문분야별 검색 보강 키워드
        field_enhancers = {
            '물리학': ['물리', '역학', '전자기학', '양자'],
            '화학': ['화학', '분자', '반응', '원소'],
            '생물학': ['생물', '생명', '생명과학', '유전'],
            '수학': ['수학', '기하', '대수', '통계'],
            '사회과학': ['사회', '정치', '경제', '사회학'],
            '인문학': ['인문', '철학', '역사', '문학'],
            '의학': ['의학', '건강', '질병', '치료'],
            '공학': ['공학', '기술', '설계', '시스템'],
            '지구과학': ['지구', '환경', '기후', '지질'],
            '천문학': ['천문', '우주', '별', '행성']
        }
        
        # 학문분야에서 보강 키워드 찾기
        enhancer = ""
        for field, keywords in field_enhancers.items():
            if field in academic_field:
                enhancer = keywords[0]  # 첫 번째 키워드 사용
                break
        
        # 향상된 검색 쿼리 생성
        if enhancer:
            return f"{keyword} {enhancer}"
        else:
            return keyword

    def is_academically_relevant(self, title: str, description: str, 
                                 academic_field: str, keywords: List[str]) -> bool:
        """학술적 관련성 사전 필터링"""
        text_to_check = f"{title} {description}".lower()
        
        # 부적합 키워드 체크
        for irrelevant in self.irrelevant_keywords:
            if irrelevant in text_to_check:
                return False
        
        # 키워드 관련성 체크 (최소 1개 이상 매칭)
        keyword_matches = sum(1 for kw in keywords if kw.lower() in text_to_check)
        
        # 학문분야 관련성 체크
        field_terms = academic_field.split(', ')
        field_matches = sum(1 for field in field_terms if field.replace('학', '').lower() in text_to_check)
        
        # 최소 조건: 키워드 1개 이상 또는 학문분야 매칭
        return keyword_matches >= 1 or field_matches >= 1

    def save_checkpoint(self, results: List[Dict], processed_count: int):
        """체크포인트 저장"""
        checkpoint_data = {
            'timestamp': datetime.now().isoformat(),
            'processed_count': processed_count,
            'total_count': self.total_count,
            'results': results
        }
        
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
    
    def load_checkpoint(self) -> Tuple[List[Dict], int]:
        """체크포인트 로드"""
        if os.path.exists(self.checkpoint_file):
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            
            print(f"🔄 체크포인트 발견: {checkpoint_data['processed_count']}/{checkpoint_data['total_count']} 완료")
            return checkpoint_data['results'], checkpoint_data['processed_count']
        
        return [], 0
        
    def process_single_topic(self, topic_data: Dict) -> Dict:
        """단일 탐구주제 처리"""
        topic_id = topic_data.get('id', 'unknown')
        topic = topic_data.get('task', '')
        
        with self.api_tracker.lock:
            self.processed_count += 1
            current_count = self.processed_count
        
        # 주제 정보 출력 (간결하게)
        print(f"\n" + "="*80)
        print(f"📚 [{current_count:,}/{self.total_count:,}] {topic_id}")
        print(f"💡 주제: {topic[:100]}{'...' if len(topic) > 100 else ''}")
        
        try:
            # 1단계: 주제 분석
            print(f"🔍 1단계: 주제 분석 중...")
            keywords, topic_analysis = self.extract_keywords_with_gemini(topic)
            
            if not keywords:
                print(f"❌ 주제 분석 실패")
                return self._create_empty_result(topic_id, topic, keywords, topic_analysis)
            
            academic_field = topic_analysis.get('academic_field', '미분류')
            difficulty = topic_analysis.get('expected_difficulty', '보통')
            print(f"✅ 분석 완료: {academic_field} | 난이도: {difficulty}")
            
            # 2단계: 도서 검색
            print(f"🔍 2단계: 도서 검색 중...")
            books = self.search_books_with_strategy(topic_analysis, max_books=15)
            
            if not books:
                print(f"❌ 검색된 도서 없음")
                return self._create_empty_result(topic_id, topic, keywords, topic_analysis)
            
            print(f"✅ 검색 완료: {len(books)}권 발견")
            
            # 3단계: 도서 평가 및 추천
            print(f"🔍 3단계: AI 도서 평가 중...")
            evaluation_result = self.intelligent_book_evaluation(topic, books, topic_analysis)
            
            # 추천 도서 생성
            recommended_books = self._create_recommended_books(evaluation_result, books)
            
            # 결과 출력
            if recommended_books:
                print(f"🎯 최종 결과: {len(recommended_books)}권 추천")
                for i, book in enumerate(recommended_books, 1):
                    grade = book.get('quality_rating', 'C')
                    title = book.get('title', '제목 없음')[:50]
                    print(f"   {i}. [{grade}등급] {title}")
            else:
                print(f"⚠️ 최종 결과: 추천 가능한 도서 없음")
            
            return {
                'id': topic_id,
                'topic': topic,
                'keywords': keywords,
                'topic_analysis': topic_analysis,
                'total_books_found': len(books),
                'verified_books_count': len(recommended_books),
                'recommended_books': recommended_books
            }
            
        except Exception as e:
            print(f"💥 처리 실패: {str(e)[:100]}")
            return self._create_empty_result(topic_id, topic, [], {'error': str(e)})
    
    def _create_empty_result(self, topic_id: str, topic: str, keywords: List[str], topic_analysis: Dict) -> Dict:
        """빈 결과 생성 헬퍼 함수"""
        return {
            'id': topic_id,
            'topic': topic,
            'keywords': keywords,
            'topic_analysis': topic_analysis,
            'total_books_found': 0,
            'verified_books_count': 0,
            'recommended_books': []
        }
    
    def _create_recommended_books(self, evaluation_result: Dict, books: List[Dict]) -> List[Dict]:
        """추천 도서 생성 헬퍼 함수"""
        recommended_books = []
        for book_eval in evaluation_result.get('recommended_books', []):
            book_number = book_eval.get('book_number', 1) - 1
            if 0 <= book_number < len(books):
                enhanced_book = books[book_number].copy()
                enhanced_book.update({
                    'quality_rating': book_eval.get('quality_rating', 'C'),
                    'relevance_level': book_eval.get('relevance_level', '보통'),
                    'appropriateness_level': book_eval.get('appropriateness_level', '보통'),
                    'academic_value': book_eval.get('academic_value', '보통'),
                    'accessibility': book_eval.get('accessibility', '보통'),
                    'recommendation_reason': book_eval.get('recommendation_reason', '추천 이유를 생성할 수 없습니다.')
                })
                recommended_books.append(enhanced_book)
        return recommended_books

    def process_topics_parallel(self, topics_data: List[Dict], batch_size: int = 10) -> List[Dict]:
        """병렬 처리로 모든 주제 처리 (체크포인트 포함)"""
        # 체크포인트 로드
        existing_results, start_idx = self.load_checkpoint()
        
        if start_idx > 0:
            remaining_topics = topics_data[start_idx:]
            print(f"💾 체크포인트에서 재시작: {start_idx}번째부터 진행 ({len(remaining_topics)}개 남음)")
            print(f"✅ 이미 완료된 주제: {start_idx}개")
            print(f"🔄 남은 주제: {len(remaining_topics)}개")
        else:
            remaining_topics = topics_data
            existing_results = []
            print(f"🚀 처음부터 시작")
        
        all_results = existing_results.copy()
        
        # 시간 계산을 위한 변수
        start_time = time.time()
        
        # 배치 단위로 처리
        for i in range(0, len(remaining_topics), batch_size):
            batch_topics = remaining_topics[i:i+batch_size]
            batch_start = start_idx + i + 1
            batch_end = min(start_idx + i + len(batch_topics), len(topics_data))
            
            # 진행률 및 시간 정보 (간결하게)
            progress = (len(all_results) / len(topics_data)) * 100
            remaining_count = len(topics_data) - len(all_results)
            
            print(f"\n📊 진행 현황: {len(all_results):,}/{len(topics_data):,} ({progress:.1f}%) | 남은 주제: {remaining_count:,}개")
            
            # 10% 단위로만 시간 예상 표시
            if len(all_results) > 0 and int(progress) % 10 == 0:
                elapsed_time = time.time() - start_time
                avg_time_per_topic = elapsed_time / len(all_results)
                estimated_remaining_time = avg_time_per_topic * remaining_count
                estimated_completion = datetime.now() + timedelta(seconds=estimated_remaining_time)
                print(f"⏱️ 예상 완료: {estimated_completion.strftime('%H:%M')}")
            
            # 병렬 처리
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
                    batch_results = list(executor.map(self.process_single_topic, batch_topics))
                
                all_results.extend(batch_results)
                
            except APIQuotaExceededException as e:
                print(f"\n🚨 API 할당량 초과! 진행상황 저장 후 중단합니다.")
                self.save_checkpoint(all_results, start_idx + i)
                
                usage_info = self.api_tracker.get_naver_api_usage_info()
                print(f"📊 API 사용률: {usage_info['usage_percentage']:.1f}% ({usage_info['calls_made']:,}/{usage_info['daily_limit']:,})")
                print(f"💾 처리 완료: {len(all_results):,}개 주제")
                print(f"🔄 새 API 키 등록 후 재실행하면 자동 재시작됩니다.")
                
                # 현재까지의 결과 반환
                return all_results
            
            # 배치 완료 후 체크포인트 저장
            self.save_checkpoint(all_results, start_idx + i + len(batch_topics))
            # 체크포인트 저장 (조용히)
        
        return all_results

    def create_comprehensive_excel(self, results: List[Dict], original_df: pd.DataFrame) -> pd.DataFrame:
        """추천도서 정보를 포함한 완전한 엑셀 파일 생성"""
        excel_data = []
        
        # 원본 ID 정보 가져오기
        ids = original_df['id'].tolist() if 'id' in original_df.columns else []
        
        for idx, result in enumerate(results):
            # 기본 정보
            row = {
                'id': ids[idx] if idx < len(ids) else f'hz-topic::{idx+1}',
                'task': result['topic'],
                'keywords': ', '.join(result['keywords']),
                'academic_field': result['topic_analysis'].get('academic_field', '미분류'),
                'total_books_found': result['total_books_found'],
                'verified_books_count': result['verified_books_count']
            }
            
            # 추천도서 정보 (최대 2권)
            recommended_books = result.get('recommended_books', [])
            
            # 추천도서가 하나도 없는 경우 특별 처리
            if not recommended_books:
                row['추천도서1_제목'] = '추천도서 없음'
                row['추천도서1_저자'] = ''
                row['추천도서1_출판사'] = ''
                row['추천도서1_출간일'] = ''
                row['추천도서1_ISBN'] = ''
                row['추천도서1_품질등급'] = 'F'
                row['추천도서1_관련성'] = '매우 낮음'
                row['추천도서1_적합성'] = '부적합'
                row['추천도서1_학술가치'] = '낮음'
                row['추천도서1_접근성'] = '어려움'
                row['추천도서1_추천이유'] = '해당 주제와 관련된 도서를 찾지 못했습니다.'
                row['추천도서1_이미지URL'] = ''
                
                # 추천도서2는 빈 값
                row['추천도서2_제목'] = ''
                row['추천도서2_저자'] = ''
                row['추천도서2_출판사'] = ''
                row['추천도서2_출간일'] = ''
                row['추천도서2_ISBN'] = ''
                row['추천도서2_품질등급'] = ''
                row['추천도서2_관련성'] = ''
                row['추천도서2_적합성'] = ''
                row['추천도서2_학술가치'] = ''
                row['추천도서2_접근성'] = ''
                row['추천도서2_추천이유'] = ''
                row['추천도서2_이미지URL'] = ''
            else:
                # 추천도서가 있는 경우 정상 처리
                for i in range(1, 3):  # 추천도서1, 추천도서2
                    if i <= len(recommended_books):
                        book_info = recommended_books[i-1]
                        # 새로운 형식: intelligent_book_evaluation 결과
                        row.update({
                            f'추천도서{i}_제목': book_info.get('title', ''),
                            f'추천도서{i}_저자': book_info.get('author', ''),
                            f'추천도서{i}_출판사': book_info.get('publisher', ''),
                            f'추천도서{i}_출간일': book_info.get('pubdate', ''),
                            f'추천도서{i}_ISBN': book_info.get('isbn', ''),
                            f'추천도서{i}_품질등급': book_info.get('quality_rating', 'C'),
                            f'추천도서{i}_관련성': book_info.get('relevance_level', '보통'),
                            f'추천도서{i}_적합성': book_info.get('appropriateness_level', '보통'),
                            f'추천도서{i}_학술가치': book_info.get('academic_value', '보통'),
                            f'추천도서{i}_접근성': book_info.get('accessibility', '보통'),
                            f'추천도서{i}_추천이유': book_info.get('recommendation_reason', '')[:200] + '...' if len(book_info.get('recommendation_reason', '')) > 200 else book_info.get('recommendation_reason', ''),
                            f'추천도서{i}_이미지URL': book_info.get('image', '')
                        })
                    else:
                        # 2번째 추천도서가 없는 경우 빈 값
                        row.update({
                            f'추천도서{i}_제목': '',
                            f'추천도서{i}_저자': '',
                            f'추천도서{i}_출판사': '',
                            f'추천도서{i}_출간일': '',
                            f'추천도서{i}_ISBN': '',
                            f'추천도서{i}_품질등급': '',
                            f'추천도서{i}_관련성': '',
                            f'추천도서{i}_적합성': '',
                            f'추천도서{i}_학술가치': '',
                            f'추천도서{i}_접근성': '',
                            f'추천도서{i}_추천이유': '',
                            f'추천도서{i}_이미지URL': ''
                        })
            
            excel_data.append(row)
        
        return pd.DataFrame(excel_data)

    def process_excel_file(self, input_file: str) -> Dict:
        """Excel 파일의 모든 탐구주제 처리 (병렬 + 체크포인트 + 완전한 Excel 생성)"""
        print(f"📊 Excel 파일 로드 중: {input_file}")
        
        # Excel 파일 읽기
        df = pd.read_excel(input_file)
        
        # 파일 구조 확인 및 적절한 컬럼 찾기
        if 'task' in df.columns:
            topics_data = df[['task']].dropna().to_dict('records')
            topics_data = [{'id': f'topic_{i}', 'task': item['task']} for i, item in enumerate(topics_data)]
        elif 'Column5' in df.columns:
            # 첫 번째 행이 헤더인 경우 제거
            if df.iloc[0]['Column5'] == 'task':
                df = df.iloc[1:]  # 첫 번째 행 제거
            # ID와 task를 함께 저장
            topics_data = []
            for _, row in df.iterrows():
                if pd.notna(row['Column5']):  # task가 있는 경우만
                    topics_data.append({
                        'id': row['Column1'] if pd.notna(row['Column1']) else f'topic_{len(topics_data)}',
                        'task': row['Column5']
                    })
            print(f"📋 Column5를 task 컬럼으로 사용합니다.")
        else:
            raise ValueError("Excel 파일에 'task' 또는 'Column5' 컬럼이 없습니다.")
        
        self.total_count = len(topics_data)
        
        print(f"📋 총 {self.total_count}개 탐구주제 처리 시작")
        print(f"🚀 병렬 처리 모드: 10개씩 동시 처리")
        print(f"💾 체크포인트 저장: 배치마다 자동 저장")
        print(f"🔧 시스템 개선 사항:")
        print(f"  ✅ 학문분야 기반 검색 쿼리 향상")
        print(f"  ✅ 사전 필터링으로 부적합 도서 제거")
        print(f"  ✅ 더 엄격한 LLM 검증 기준")
        print(f"  ✅ 완전한 추천도서 정보 포함 Excel 생성")
        print("=" * 80)
        
        # 체크포인트 상태 확인
        if os.path.exists(self.checkpoint_file):
            print(f"🔄 체크포인트 파일 발견: {self.checkpoint_file}")
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)
            print(f"📊 이전 진행 상황: {checkpoint_data['processed_count']}/{checkpoint_data['total_count']} 완료")
            print(f"💾 이어서 진행하거나 새로 시작할 수 있습니다.")
        else:
            print(f"🚀 새로운 세션 시작")
        
        start_time = time.time()
        
        # 병렬 처리로 결과 생성
        results = self.process_topics_parallel(topics_data, batch_size=10)
        
        processing_time = time.time() - start_time
        
        # 완전한 Excel 파일 생성 (추천도서 정보 포함)
        comprehensive_df = self.create_comprehensive_excel(results, df)
        
        # 통계 계산
        field_counts = Counter([r['topic_analysis'].get('academic_field', '미분류') for r in results])
        avg_books_per_topic = sum(r['total_books_found'] for r in results) / len(results) if results else 0
        
        # 체크포인트 파일 삭제 (완료 후)
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            print("🗑️ 체크포인트 파일 정리 완료")
        
        return {
            'total_topics': len(topics_data),
            'results': results,
            'statistics': {
                'academic_fields': dict(field_counts),
                'average_books_per_topic': round(avg_books_per_topic, 1),
                'total_processing_time': f"{processing_time:.1f}초",
                'api_cost_usd': round(self.api_tracker.total_cost, 4),
                'api_cost_krw': round(self.api_tracker.total_cost * 1300, 0),
                'api_calls_total': len(self.api_tracker.usage_log),
                'cost_per_topic_usd': round(self.api_tracker.total_cost / len(topics_data) if topics_data else 0, 4),
                'parallel_processing': True,
                'batch_size': 10,
                'checkpoint_enabled': True,
                'system_improvements': {
                    'enhanced_search_queries': True,
                    'pre_filtering': True,
                    'stricter_llm_verification': True,
                    'comprehensive_excel': True
                }
            },
            'comprehensive_dataframe': comprehensive_df  # 완전한 Excel 데이터
        }

def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("고등학생 탐구주제 도서 추천 시스템 (대용량 처리 버전 - 개선됨)")
    print("- Gemini 1.5 Pro (키워드 추출 + 도서 검증)")
    print("- 병렬 처리 (10개씩)")
    print("- 체크포인트 저장 및 재시작 기능")
    print("- API 사용량 및 비용 추적 기능")
    print("- 향상된 검색 및 필터링 시스템")
    print("=" * 80)
    
    try:
        # Excel 파일 처리
        input_file = '../원천파일/failed_topics_for_reprocessing_20250716_091106.xlsx'
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"{input_file} 파일을 찾을 수 없습니다.")
        
        # 시스템 초기화 (입력 파일 기반 파일명 설정)
        system = EnhancedBookRecommendationSystem(input_file)
        
        # 체크포인트 파일 상태 확인
        if os.path.exists(system.checkpoint_file):
            print(f"\n🔄 체크포인트 파일 발견!")
            print(f"📁 파일 위치: {system.checkpoint_file}")
            print(f"💡 중간에 실패했어도 이어서 진행할 수 있습니다.")
            print(f"🗑️ 처음부터 시작하려면 체크포인트 파일을 삭제하세요.")
        else:
            print(f"\n🚀 새로운 처리 세션 시작")
        
        start_time = time.time()
        try:
            final_results = system.process_excel_file(input_file)
            processing_time = time.time() - start_time
        except APIQuotaExceededException as e:
            print(f"\n🚨 API 할당량 초과로 인한 처리 중단!")
            print(f"❌ {str(e)}")
            print(f"\n📋 상황 요약:")
            print(f"   - 네이버 API 일일 호출 한도가 초과되었습니다")
            print(f"   - 현재까지 처리된 결과는 체크포인트에 자동 저장되었습니다")
            print(f"   - 새로운 API 키를 등록하고 다시 실행하면 이어서 진행됩니다")
            
            # 네이버 API 사용량 정보 출력
            usage_info = system.api_tracker.get_naver_api_usage_info()
            print(f"\n📊 네이버 API 사용량 정보:")
            print(f"   - 총 호출 횟수: {usage_info['calls_made']:,}회")
            print(f"   - 일일 한도: {usage_info['daily_limit']:,}회")
            print(f"   - 사용률: {usage_info['usage_percentage']:.1f}%")
            
            print(f"\n🔧 해결 방법:")
            print(f"   1. 네이버 API 콘솔에서 새로운 API 키 생성")
            print(f"   2. .env 파일의 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET 업데이트")
            print(f"   3. 이 스크립트를 다시 실행 (자동으로 이어서 진행됨)")
            
            return  # 정상 종료
            
        processing_time = time.time() - start_time
        
        # 결과 저장 (원천파일 이름 기반)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = system.base_filename
        
        # JSON 결과 저장 (DataFrame 제외)
        json_filename = f'../결과파일/book_recommendations_{base_filename}_{timestamp}.json'
        json_data = {
            'total_topics': final_results['total_topics'],
            'results': final_results['results'],
            'statistics': final_results['statistics']
        }
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        # 완전한 Excel 결과 저장 (추천도서 정보 포함)
        excel_filename = f'../결과파일/final_book_recommendations_{base_filename}_{timestamp}.xlsx'
        final_results['comprehensive_dataframe'].to_excel(excel_filename, index=False)
        
        # API 사용량 리포트 저장
        api_report_filename = system.api_tracker.save_usage_report(f'../결과파일/api_usage_report_{base_filename}_{timestamp}.txt')
        
        # 최종 결과 출력
        print("\n" + "=" * 80)
        print("🎉 처리 완료!")
        print("=" * 80)
        stats = final_results['statistics']
        print(f"⏱️ 총 처리 시간: {stats['total_processing_time']}")
        print(f"📊 처리된 탐구주제: {final_results['total_topics']}개")
        print(f"📚 평균 도서 발견: {stats['average_books_per_topic']}권/주제")
        
        print(f"\n💰 API 비용 정보:")
        print(f"  📞 총 API 호출: {stats['api_calls_total']}회")
        print(f"  💵 예상 총 비용: ${stats['api_cost_usd']} USD (₩{stats['api_cost_krw']:,})")
        print(f"  💰 주제당 평균 비용: ${stats['cost_per_topic_usd']} USD")
        
        print(f"\n🚀 성능 정보:")
        print(f"  🔄 병렬 처리: {stats['batch_size']}개씩 동시 처리")
        print(f"  💾 체크포인트: {'활성화' if stats['checkpoint_enabled'] else '비활성화'}")
        print(f"  🔄 배치 크기: {stats['batch_size']}개 (처리 속도와 안정성 균형)")
        print(f"  💾 자동 저장: 배치마다 중간 결과 저장")
        print(f"  🔁 재시작 기능: 중간 실패 시 이어서 진행 가능")
        
        improvements = stats['system_improvements']
        print(f"\n🔧 시스템 개선 사항:")
        print(f"  ✅ 향상된 검색 쿼리: {'활성화' if improvements['enhanced_search_queries'] else '비활성화'}")
        print(f"  ✅ 사전 필터링: {'활성화' if improvements['pre_filtering'] else '비활성화'}")
        print(f"  ✅ 엄격한 LLM 검증: {'활성화' if improvements['stricter_llm_verification'] else '비활성화'}")
        print(f"  ✅ 완전한 Excel 생성: {'활성화' if improvements['comprehensive_excel'] else '비활성화'}")
        
        print(f"\n📊 학문분야별 분포:")
        for field, count in stats['academic_fields'].items():
            print(f"  📖 {field}: {count}개")
        
        print(f"\n📁 생성된 파일:")
        print(f"  📄 JSON 결과: {json_filename}")
        print(f"  📊 완전한 Excel 결과: {excel_filename}")
        print(f"  📈 API 사용량 리포트: {api_report_filename}")
        
        # 샘플 결과 출력
        if final_results['results']:
            sample = final_results['results'][0]
            print(f"\n📚 샘플 결과 ('{sample['topic'][:30]}...'):")
            print(f"  🔍 키워드: {', '.join(sample['keywords'])}")
            print(f"  📖 학문분야: {sample['topic_analysis'].get('academic_field', '미분류')}")
            
            if sample['recommended_books']:
                book = sample['recommended_books'][0]
                print(f"  🏆 추천도서 1위: {book['title']} (점수: {book.get('llm_total_score', 'N/A')}점)")
                print(f"  📚 ISBN: {book['isbn']}")
                print(f"  💡 추천이유: {book.get('recommendation_reason', '')[:100]}...")
        
        print(f"\n🎯 주요 개선 효과:")
        print(f"  📈 검색 정확도 향상: 학문분야 기반 검색")
        print(f"  🗂️ 불필요한 도서 제거: 사전 필터링")
        print(f"  🎯 더 엄격한 검증: 향상된 LLM 프롬프트")
        print(f"  📊 완전한 결과 제공: 추천도서 정보 포함 Excel")
        
    except Exception as e:
        print(f"❌ 시스템 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 