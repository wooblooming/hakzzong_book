#!/usr/bin/env python3.11
"""
고등학생 탐구주제 도서 추천 시스템 (통합 버전)
- Gemini 2.5 Pro를 사용한 키워드 추출 및 도서 검증
- 네이버 도서 API 연동
- 상세한 추천 이유 생성
"""

import pandas as pd
import json
import re
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime
import time
import requests
from typing import Dict, List, Tuple, Optional
from collections import Counter

# 환경 변수 로드 (상대 경로 지정)
load_dotenv('../설정파일/.env')

class APIUsageTracker:
    """API 사용량 및 비용 추적 클래스"""
    
    def __init__(self):
        self.usage_log = []
        self.total_cost = 0.0
        
        # Gemini API 가격 (USD per 1M tokens, 2024년 기준)
        self.pricing = {
            'gemini-1.5-flash': {
                'input': 0.075,   # $0.075 per 1M input tokens
                'output': 0.30    # $0.30 per 1M output tokens
            },
            'gemini-1.5-pro': {
                'input': 1.25,    # $1.25 per 1M input tokens
                'output': 5.00    # $5.00 per 1M output tokens
            }
        }
    
    def estimate_tokens(self, text: str) -> int:
        """텍스트의 대략적인 토큰 수 추정 (한국어 기준)"""
        # 한국어는 약 1.5-2 토큰/단어, 영어는 약 1.3 토큰/단어
        korean_chars = len(re.findall(r'[가-힣]', text))
        other_chars = len(text) - korean_chars
        
        # 한국어: 2자당 1토큰, 영어/숫자: 4자당 1토큰으로 근사
        estimated_tokens = (korean_chars // 2) + (other_chars // 4)
        return max(estimated_tokens, 1)
    
    def log_api_call(self, model: str, input_text: str, output_text: str, 
                     call_type: str = "general"):
        """API 호출 정보 로깅"""
        input_tokens = self.estimate_tokens(input_text)
        output_tokens = self.estimate_tokens(output_text)
        
        # 비용 계산
        input_cost = (input_tokens / 1_000_000) * self.pricing[model]['input']
        output_cost = (output_tokens / 1_000_000) * self.pricing[model]['output']
        total_cost = input_cost + output_cost
        
        self.total_cost += total_cost
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'model': model,
            'call_type': call_type,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'input_cost_usd': round(input_cost, 6),
            'output_cost_usd': round(output_cost, 6),
            'total_cost_usd': round(total_cost, 6)
        }
        
        self.usage_log.append(log_entry)
        return log_entry
    
    def save_usage_report(self, filename: str = None):
        """사용량 리포트를 텍스트 파일로 저장"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f'api_usage_report_{timestamp}.txt'
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("Gemini API 사용량 및 비용 리포트\n")
            f.write("=" * 80 + "\n")
            f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"총 API 호출 수: {len(self.usage_log)}회\n")
            f.write(f"총 예상 비용: ${self.total_cost:.4f} USD (₩{self.total_cost * 1300:.0f})\n\n")
            
            # 모델별 통계
            model_stats = {}
            for log in self.usage_log:
                model = log['model']
                if model not in model_stats:
                    model_stats[model] = {
                        'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'cost': 0.0
                    }
                model_stats[model]['calls'] += 1
                model_stats[model]['input_tokens'] += log['input_tokens']
                model_stats[model]['output_tokens'] += log['output_tokens']
                model_stats[model]['cost'] += log['total_cost_usd']
            
            f.write("모델별 사용 통계:\n")
            f.write("-" * 50 + "\n")
            for model, stats in model_stats.items():
                f.write(f"{model}:\n")
                f.write(f"  호출 수: {stats['calls']}회\n")
                f.write(f"  입력 토큰: {stats['input_tokens']:,}개\n")
                f.write(f"  출력 토큰: {stats['output_tokens']:,}개\n")
                f.write(f"  비용: ${stats['cost']:.4f} USD\n\n")
            
            # 호출 유형별 통계
            type_stats = {}
            for log in self.usage_log:
                call_type = log['call_type']
                if call_type not in type_stats:
                    type_stats[call_type] = {'calls': 0, 'cost': 0.0}
                type_stats[call_type]['calls'] += 1
                type_stats[call_type]['cost'] += log['total_cost_usd']
            
            f.write("호출 유형별 통계:\n")
            f.write("-" * 50 + "\n")
            for call_type, stats in type_stats.items():
                f.write(f"{call_type}: {stats['calls']}회, ${stats['cost']:.4f} USD\n")
            
            # 상세 로그
            f.write("\n" + "=" * 80 + "\n")
            f.write("상세 API 호출 로그:\n")
            f.write("=" * 80 + "\n")
            for i, log in enumerate(self.usage_log, 1):
                f.write(f"[{i}] {log['timestamp']}\n")
                f.write(f"    모델: {log['model']}\n")
                f.write(f"    유형: {log['call_type']}\n")
                f.write(f"    토큰: {log['input_tokens']} → {log['output_tokens']}\n")
                f.write(f"    비용: ${log['total_cost_usd']:.6f} USD\n\n")
        
        print(f"API 사용량 리포트 저장: {filename}")
        return filename

class BookRecommendationSystem:
    def __init__(self):
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
        self.model = genai.GenerativeModel('gemini-1.5-pro')  # 종합 분석용 모델
        
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
        
        self.processed_count = 0
        self.total_count = 0
        
    def extract_keywords_with_gemini(self, topic: str) -> Tuple[List[str], Dict]:
        """Gemini를 사용하여 키워드 추출 및 추가 정보 생성"""
        prompt = f"""
고등학생 탐구주제: "{topic}"

이 탐구주제를 분석하여 다음 정보를 JSON 형식으로 제공해주세요:

{{
    "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5", "키워드6", "키워드7"],
    "academic_field": "주요 학문분야",
    "difficulty_level": "고등학생 수준에서의 난이도 (상/중/하)",
    "additional_keywords": ["추가검색용 키워드1", "추가검색용 키워드2"],
    "book_types": ["관련 도서 유형1", "관련 도서 유형2"],
    "cautions": "도서 선정 시 주의사항"
}}

주요 요구사항:
1. keywords: 도서 검색에 효과적인 5-7개 키워드 (한국어, 구체적이고 검색 가능한 용어)
2. academic_field: 물리학, 화학, 생물학, 수학, 사회과학, 인문학 등
3. difficulty_level: 고등학생이 이해할 수 있는 수준인지 평가
4. additional_keywords: 보완적 검색용 키워드 1-2개
5. book_types: 이론서, 실험서, 교양서, 입문서 등 적절한 도서 유형
6. cautions: 너무 어렵거나 부적절한 도서를 피하기 위한 주의사항

반드시 JSON 형식으로만 응답해주세요.
"""
        
        try:
            print(f"Gemini API로 키워드 추출 중: {topic[:50]}...")
            response = self.model.generate_content(prompt)
            
            # API 사용량 로깅
            self.api_tracker.log_api_call(
                'gemini-1.5-pro', prompt, response.text, 'keyword_extraction'
            )
            
            # JSON 파싱
            json_text = response.text.strip()
            if json_text.startswith('```json'):
                json_text = json_text[7:-3].strip()
            elif json_text.startswith('```'):
                json_text = json_text[3:-3].strip()
                
            result = json.loads(json_text)
            
            return result.get('keywords', []), result
            
        except Exception as e:
            print(f"Gemini API 오류: {e}")
            print(f"  키워드 추출 실패")
            return [], {
                'keywords': [],
                'academic_field': '미분류',
                'difficulty_level': '중',
                'additional_keywords': [],
                'book_types': [],
                'cautions': 'API 오류로 인한 처리 실패'
            }
    
    def search_books_naver(self, keywords: List[str], max_per_keyword: int = 10) -> List[Dict]:
        """네이버 도서 API로 도서 검색"""
        all_books = []
        
        for keyword in keywords[:3]:  # 상위 3개 키워드만 사용
            try:
                print(f"  네이버 API 검색: {keyword}")
                
                headers = {
                    'X-Naver-Client-Id': self.naver_client_id,
                    'X-Naver-Client-Secret': self.naver_client_secret,
                }
                
                params = {
                    'query': keyword,
                    'display': max_per_keyword,
                    'sort': 'sim'  # 정확도순
                }
                
                response = requests.get(
                    'https://openapi.naver.com/v1/search/book.json',
                    headers=headers,
                    params=params,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    books = data.get('items', [])
                    
                    for book in books:
                        if book.get('isbn'):
                            all_books.append({
                                'title': re.sub(r'<[^>]+>', '', book.get('title', '')),
                                'author': re.sub(r'<[^>]+>', '', book.get('author', '')),
                                'publisher': book.get('publisher', ''),
                                'pubdate': book.get('pubdate', ''),
                                'isbn': book.get('isbn', '').split()[-1],  # 13자리 ISBN 사용
                                'description': re.sub(r'<[^>]+>', '', book.get('description', '')),
                                'search_keyword': keyword
                            })
                
                time.sleep(0.1)  # API 호출 간격
                
            except Exception as e:
                print(f"  네이버 API 오류 ({keyword}): {e}")
                continue
        
        # ISBN 기준 중복 제거
        unique_books = {}
        for book in all_books:
            isbn = book['isbn']
            if isbn and isbn not in unique_books:
                unique_books[isbn] = book
        
        return list(unique_books.values())
    
    def verify_books_with_llm(self, books: List[Dict], topic: str, topic_info: Dict) -> List[Dict]:
        """LLM을 사용하여 도서 적합성 검증 및 점수 계산"""
        if not books:
            return []
        
        # 상위 15권만 검증 (API 비용 절약)
        books_to_verify = books[:15]
        
        book_list = []
        for i, book in enumerate(books_to_verify, 1):
            book_info = f"{i}. 제목: {book['title']}\n"
            book_info += f"   저자: {book['author']}\n"
            book_info += f"   출판사: {book['publisher']}\n"
            book_info += f"   출간년도: {book['pubdate']}\n"
            book_info += f"   설명: {book['description'][:200]}...\n"
            book_list.append(book_info)
        
        prompt = f"""
고등학생 탐구주제: "{topic}"
주제 분석 정보:
- 학문분야: {topic_info.get('academic_field', '미분류')}
- 난이도: {topic_info.get('difficulty_level', '중')}
- 도서 유형: {', '.join(topic_info.get('book_types', ['교양서']))}
- 주의사항: {topic_info.get('cautions', '없음')}

검증할 도서 목록:
{chr(10).join(book_list)}

각 도서에 대해 다음 기준으로 점수를 매기고 JSON 형식으로 제공해주세요:

{{
    "book_scores": [
        {{
            "book_number": 1,
            "relevance_score": 30,
            "appropriateness_score": 25,
            "reliability_score": 20,
            "recency_score": 15,
            "accessibility_score": 10,
            "total_score": 100,
            "recommendation_reason": "250-300자의 상세한 추천 이유"
        }},
        // ... 다른 도서들
    ]
}}

점수 기준:
1. relevance_score (연관성, 0-30점): 탐구주제와의 직접적 관련성
2. appropriateness_score (적합성, 0-25점): 고등학생 수준에의 적합성
3. reliability_score (신뢰성, 0-20점): 저자/출판사의 권위성, 내용의 정확성
4. recency_score (최신성, 0-15점): 출간년도의 최신성 (2020년 이후 만점)
5. accessibility_score (접근성, 0-10점): 구매/대출의 용이성, 읽기 난이도

recommendation_reason은 반드시 250-300자로 작성하며, 다음을 포함해야 합니다:
- 탐구주제와의 구체적 연관성
- 고등학생에게 적합한 이유
- 이 책을 통해 얻을 수 있는 구체적 지식/인사이트
- 탐구 활동에 도움이 되는 방법

반드시 JSON 형식으로만 응답해주세요.
"""
        
        try:
            print("  LLM으로 도서 검증 중...")
            response = self.model.generate_content(prompt)
            
            # API 사용량 로깅
            self.api_tracker.log_api_call(
                'gemini-1.5-pro', prompt, response.text, 'book_verification'
            )
            
            json_text = response.text.strip()
            if json_text.startswith('```json'):
                json_text = json_text[7:-3].strip()
            elif json_text.startswith('```'):
                json_text = json_text[3:-3].strip()
            
            result = json.loads(json_text)
            book_scores = result.get('book_scores', [])
            
            # 점수를 원본 도서 정보에 추가
            verified_books = []
            for score_info in book_scores:
                book_num = score_info.get('book_number', 1) - 1
                if 0 <= book_num < len(books_to_verify):
                    book = books_to_verify[book_num].copy()
                    book.update({
                        'llm_total_score': score_info.get('total_score', 0),
                        'llm_relevance': score_info.get('relevance_score', 0),
                        'llm_appropriateness': score_info.get('appropriateness_score', 0),
                        'llm_reliability': score_info.get('reliability_score', 0),
                        'llm_recency': score_info.get('recency_score', 0),
                        'llm_accessibility': score_info.get('accessibility_score', 0),
                        'recommendation_reason': score_info.get('recommendation_reason', '추천 이유를 생성할 수 없습니다.')
                    })
                    verified_books.append(book)
            
            return sorted(verified_books, key=lambda x: x.get('llm_total_score', 0), reverse=True)
            
        except Exception as e:
            print(f"  LLM 검증 오류: {e}")
            return []
    
    def process_single_topic(self, topic: str) -> Dict:
        """단일 탐구주제 처리"""
        self.processed_count += 1
        print(f"\n[{self.processed_count}/{self.total_count}] 처리 중: {topic}")
        
        try:
            # 1단계: Gemini로 키워드 추출 및 분석
            keywords, topic_info = self.extract_keywords_with_gemini(topic)
            print(f"  추출된 키워드: {keywords}")
            print(f"  학문분야: {topic_info.get('academic_field', '미분류')}")
            
            # 2단계: 네이버 API로 도서 검색
            books = self.search_books_naver(keywords)
            print(f"  검색된 도서: {len(books)}권")
            
            # 3단계: LLM으로 도서 검증 및 점수 계산
            verified_books = self.verify_books_with_llm(books, topic, topic_info)
            
            # 상위 2권 선정
            top_books = verified_books[:2]
            
            result = {
                'topic': topic,
                'keywords': keywords,
                'topic_analysis': topic_info,
                'total_books_found': len(books),
                'verified_books_count': len(verified_books),
                'recommended_books': []
            }
            
            for i, book in enumerate(top_books, 1):
                result['recommended_books'].append({
                    'rank': i,
                    'title': book['title'],
                    'author': book['author'],
                    'publisher': book['publisher'],
                    'publication_date': book['pubdate'],
                    'isbn': book['isbn'],
                    'description': book['description'][:200] + '...' if len(book['description']) > 200 else book['description'],
                    'total_score': book.get('llm_total_score', 0),
                    'score_details': {
                        'relevance': book.get('llm_relevance', 0),
                        'appropriateness': book.get('llm_appropriateness', 0),
                        'reliability': book.get('llm_reliability', 0),
                        'recency': book.get('llm_recency', 0),
                        'accessibility': book.get('llm_accessibility', 0)
                    },
                    'recommendation_reason': book.get('recommendation_reason', ''),
                    'search_keyword': book.get('search_keyword', '')
                })
            
            print(f"  추천 도서: {len(top_books)}권")
            return result
            
        except Exception as e:
            print(f"  처리 오류: {e}")
            return {
                'topic': topic,
                'keywords': [],
                'topic_analysis': {'error': str(e)},
                'total_books_found': 0,
                'verified_books_count': 0,
                'recommended_books': []
            }
    
    def process_excel_file(self, input_file: str) -> Dict:
        """Excel 파일의 모든 탐구주제 처리"""
        print(f"Excel 파일 로드 중: {input_file}")
        
        # Excel 파일 읽기
        df = pd.read_excel(input_file)
        
        if 'task' not in df.columns:
            raise ValueError("Excel 파일에 'task' 컬럼이 없습니다.")
        
        topics = df['task'].dropna().tolist()
        self.total_count = len(topics)
        
        print(f"총 {self.total_count}개 탐구주제 처리 시작")
        print("=" * 80)
        
        start_time = time.time()
        results = []
        keywords_list = []
        academic_fields = []
        
        for topic in topics:
            result = self.process_single_topic(topic)
            results.append(result)
            
            # keywords 컬럼용 데이터 수집
            keywords_list.append(', '.join(result['keywords']))
            academic_fields.append(result['topic_analysis'].get('academic_field', '미분류'))
            
            # 진행률 표시
            progress = (self.processed_count / self.total_count) * 100
            print(f"  진행률: {progress:.1f}%")
            
            # API 호출 간격 (1.5-pro 모델이므로 더 짧은 간격)
            time.sleep(0.5)
        
        processing_time = time.time() - start_time
        
        # Excel 파일에 keywords 컬럼 추가
        df['keywords'] = keywords_list
        df['academic_field'] = academic_fields
        
        # 통계 계산
        field_counts = Counter(academic_fields)
        avg_books_per_topic = sum(r['total_books_found'] for r in results) / len(results) if results else 0
        
        return {
            'total_topics': len(topics),
            'results': results,
            'statistics': {
                'academic_fields': dict(field_counts),
                'average_books_per_topic': round(avg_books_per_topic, 1),
                'total_processing_time': f"{processing_time:.1f}초",
                'api_cost_usd': round(self.api_tracker.total_cost, 4),
                'api_cost_krw': round(self.api_tracker.total_cost * 1300, 0),
                'api_calls_total': len(self.api_tracker.usage_log),
                'cost_per_topic_usd': round(self.api_tracker.total_cost / len(topics) if topics else 0, 4)
            },
            'updated_dataframe': df  # JSON에서는 제외, Excel만 저장
        }

def main():
    """메인 실행 함수"""
    print("=" * 80)
    print("고등학생 탐구주제 도서 추천 시스템 (통합 버전)")
    print("- Gemini 1.5 Pro API 사용 (최적 성능)")
    print("- API 사용량 및 비용 추적 기능")
    print("- Python 3.11 호환")
    print("=" * 80)
    
    try:
        # 시스템 초기화
        system = BookRecommendationSystem()
        
        # Excel 파일 처리
        input_file = '../원천파일/주제테스트_50.xlsx'
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"{input_file} 파일을 찾을 수 없습니다.")
        
        start_time = time.time()
        final_results = system.process_excel_file(input_file)
        processing_time = time.time() - start_time
        
        # 결과 저장
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON 결과 저장 (DataFrame 제외)
        json_filename = f'../결과파일/book_recommendations_{timestamp}.json'
        json_data = {
            'total_topics': final_results['total_topics'],
            'results': final_results['results'],
            'statistics': final_results['statistics']
        }
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        # Excel 결과 저장 (keywords 컬럼 추가됨)
        excel_filename = f'../결과파일/final_book_recommendations_{timestamp}.xlsx'
        final_results['updated_dataframe'].to_excel(excel_filename, index=False)
        
        # API 사용량 리포트 저장
        api_report_filename = system.api_tracker.save_usage_report(f'../결과파일/api_usage_report_{timestamp}.txt')
        
        # 최종 결과 출력
        print("\n" + "=" * 80)
        print("처리 완료!")
        print("=" * 80)
        stats = final_results['statistics']
        print(f"총 처리 시간: {stats['total_processing_time']}")
        print(f"처리된 탐구주제: {final_results['total_topics']}개")
        print(f"평균 도서 발견: {stats['average_books_per_topic']}권/주제")
        
        print(f"\n💰 API 비용 정보:")
        print(f"  총 API 호출: {stats['api_calls_total']}회")
        print(f"  예상 총 비용: ${stats['api_cost_usd']} USD (₩{stats['api_cost_krw']:,})")
        print(f"  주제당 평균 비용: ${stats['cost_per_topic_usd']} USD")
        
        print(f"\n📊 학문분야별 분포:")
        for field, count in stats['academic_fields'].items():
            print(f"  - {field}: {count}개")
        
        print(f"\n📁 생성된 파일:")
        print(f"  - JSON 결과: {json_filename}")
        print(f"  - Excel 결과: {excel_filename}")
        print(f"  - API 사용량 리포트: {api_report_filename}")
        
        # 샘플 결과 출력
        if final_results['results']:
            sample = final_results['results'][0]
            print(f"\n📚 샘플 결과 ('{sample['topic'][:30]}...'):")
            print(f"  키워드: {', '.join(sample['keywords'])}")
            print(f"  학문분야: {sample['topic_analysis'].get('academic_field', '미분류')}")
            
            if sample['recommended_books']:
                book = sample['recommended_books'][0]
                print(f"  추천도서 1위: {book['title']} (점수: {book['total_score']}점)")
                print(f"  ISBN: {book['isbn']}")
                print(f"  추천이유: {book['recommendation_reason'][:100]}...")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 