#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import pandas as pd
import requests
import time
import google.generativeai as genai
from dotenv import load_dotenv
from typing import List, Dict, Any, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from urllib.parse import quote

class IntelligentBookRecommendationSystem:
    """LLM 기반 지능형 도서 추천 시스템"""
    
    def __init__(self):
        """시스템 초기화"""
        # 환경 변수 로드
        load_dotenv('../설정파일/.env')
        
        # API 키 설정
        google_api_key = os.getenv('GOOGLE_API_KEY')
        naver_client_id = os.getenv('NAVER_CLIENT_ID')
        naver_client_secret = os.getenv('NAVER_CLIENT_SECRET')
        
        if not all([google_api_key, naver_client_id, naver_client_secret]):
            raise ValueError("필요한 API 키가 설정되지 않았습니다.")
        
        # Gemini 설정
        genai.configure(api_key=google_api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # 네이버 API 설정
        self.naver_client_id = naver_client_id
        self.naver_client_secret = naver_client_secret
        
        # 사용량 추적
        self.api_usage = {
            'gemini_calls': 0,
            'naver_calls': 0,
            'total_tokens': 0
        }
        
        self.lock = threading.Lock()
        
    def analyze_topic_with_llm(self, topic: str) -> Dict[str, Any]:
        """LLM을 사용한 심층적 주제 분석 및 검색 전략 수립"""
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
        "alternative_topics": ["대안 주제어1", "대안 주제어2"],
        "book_types": ["적합한 도서 유형들"]
    }},
    "expected_difficulty": "도서 찾기 난이도 (쉬움/보통/어려움)",
    "search_tips": "검색 시 주의사항이나 팁"
}}

고등학생 수준에 적합한 도서를 찾는 것이 목표입니다.
"""
        
        try:
            with self.lock:
                self.api_usage['gemini_calls'] += 1
            
            response = self.model.generate_content(prompt)
            
            # JSON 파싱
            content = response.text.strip()
            if content.startswith('```json'):
                content = content[7:-3].strip()
            elif content.startswith('```'):
                content = content[3:-3].strip()
                
            analysis = json.loads(content)
            return analysis
            
        except Exception as e:
            print(f"⚠️ 주제 분석 실패: {e}")
            # 기본 분석 반환
            return {
                "topic_summary": topic[:100],
                "core_concepts": [topic.split()[0] if topic.split() else "연구"],
                "academic_field": "일반",
                "difficulty_level": "중급",
                "search_strategy": {
                    "primary_keywords": [topic.split()[0] if topic.split() else "연구"],
                    "secondary_keywords": ["입문", "기초"],
                    "alternative_topics": ["관련 주제"],
                    "book_types": ["교양서", "입문서"]
                },
                "expected_difficulty": "보통",
                "search_tips": "다양한 키워드로 검색 필요"
            }
    
    def search_books_with_strategy(self, analysis: Dict[str, Any]) -> List[Dict]:
        """전략적 다단계 도서 검색"""
        all_books = []
        search_strategy = analysis.get('search_strategy', {})
        
        # 1차 검색: 주요 키워드
        print("📚 1차 검색: 주요 키워드")
        primary_keywords = search_strategy.get('primary_keywords', [])
        for keyword in primary_keywords[:3]:  # 최대 3개
            books = self.search_naver_books(keyword, max_results=8)
            all_books.extend(books)
            print(f"  '{keyword}': {len(books)}권 발견")
        
        # 중복 제거 후 수량 확인
        unique_books = self.remove_duplicates(all_books)
        print(f"📊 1차 검색 결과: 총 {len(unique_books)}권 (중복 제거 후)")
        
        # 2차 검색: 1차 결과가 부족한 경우
        if len(unique_books) < 5:
            print("📚 2차 검색: 보조 키워드")
            secondary_keywords = search_strategy.get('secondary_keywords', [])
            for keyword in secondary_keywords[:2]:  # 최대 2개
                books = self.search_naver_books(keyword, max_results=8)
                all_books.extend(books)
                print(f"  '{keyword}': {len(books)}권 발견")
            
            unique_books = self.remove_duplicates(all_books)
            print(f"📊 2차 검색 후: 총 {len(unique_books)}권")
        
        # 3차 검색: 여전히 부족한 경우 대안 주제
        if len(unique_books) < 3:
            print("📚 3차 검색: 대안 주제어")
            alternative_topics = search_strategy.get('alternative_topics', [])
            for topic in alternative_topics[:2]:  # 최대 2개
                books = self.search_naver_books(topic, max_results=10)
                all_books.extend(books)
                print(f"  '{topic}': {len(books)}권 발견")
            
            unique_books = self.remove_duplicates(all_books)
            print(f"📊 3차 검색 후: 총 {len(unique_books)}권")
        
        return unique_books[:20]  # 최대 20권으로 제한
    
    def search_naver_books(self, query: str, max_results: int = 10) -> List[Dict]:
        """네이버 도서 API 검색"""
        try:
            with self.lock:
                self.api_usage['naver_calls'] += 1
            
            url = "https://openapi.naver.com/v1/search/book.json"
            headers = {
                "X-Naver-Client-Id": self.naver_client_id,
                "X-Naver-Client-Secret": self.naver_client_secret
            }
            params = {
                "query": query,
                "display": max_results,
                "sort": "sim"  # 정확도순
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            
            data = response.json()
            books = []
            
            for item in data.get('items', []):
                # HTML 태그 제거
                title = self.clean_html_tags(item.get('title', ''))
                author = self.clean_html_tags(item.get('author', ''))
                publisher = self.clean_html_tags(item.get('publisher', ''))
                description = self.clean_html_tags(item.get('description', ''))
                
                book = {
                    'title': title,
                    'author': author,
                    'publisher': publisher,
                    'pubdate': item.get('pubdate', ''),
                    'isbn': item.get('isbn', ''),
                    'description': description,
                    'image': item.get('image', ''),
                    'search_keyword': query
                }
                books.append(book)
            
            time.sleep(0.1)  # API 호출 간격
            return books
            
        except Exception as e:
            print(f"⚠️ 네이버 검색 실패 ({query}): {e}")
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
    
    def intelligent_book_evaluation(self, topic: str, books: List[Dict], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """LLM 기반 지능형 도서 평가"""
        if not books:
            return self.suggest_alternative_books(topic, analysis)
        
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

주제 분석:
- 핵심 개념: {', '.join(analysis.get('core_concepts', []))}
- 학문 분야: {analysis.get('academic_field', '')}
- 난이도: {analysis.get('difficulty_level', '')}

다음 도서들을 평가해주세요:

{books_text}

평가 기준:
1. 주제와의 관련성 (매우 높음/높음/보통/낮음/매우 낮음)
2. 고등학생 적합성 (매우 적합/적합/보통/부적합/매우 부적합)
3. 학술적 가치 (높음/보통/낮음)

다음 형식으로 응답해주세요:

{{
    "evaluation_summary": "전체 도서 품질에 대한 한 줄 평가",
    "recommendation_decision": "추천/조건부추천/추천불가",
    "recommended_books": [
        {{
            "book_number": 1,
            "title": "도서명",
            "relevance": "관련성 평가",
            "appropriateness": "적합성 평가", 
            "academic_value": "학술적 가치",
            "recommendation_reason": "추천 이유 (100-150자)",
            "overall_rating": "A/B/C/D/F"
        }}
    ],
    "alternative_suggestion": "더 나은 도서를 찾기 위한 제안 (추천불가인 경우)"
}}

- 최대 2권까지만 추천
- 정말 적합한 도서가 없다면 솔직히 "추천불가"로 판정
- 억지로 추천하지 말고 품질을 우선시
"""
        
        try:
            with self.lock:
                self.api_usage['gemini_calls'] += 1
            
            response = self.model.generate_content(prompt)
            
            # JSON 파싱
            content = response.text.strip()
            if content.startswith('```json'):
                content = content[7:-3].strip()
            elif content.startswith('```'):
                content = content[3:-3].strip()
            
            evaluation = json.loads(content)
            
            # 추천 도서에 원본 정보 추가
            if evaluation.get('recommended_books'):
                for rec_book in evaluation['recommended_books']:
                    book_num = rec_book.get('book_number', 1) - 1
                    if 0 <= book_num < len(books):
                        original_book = books[book_num]
                        rec_book.update(original_book)
            
            return evaluation
            
        except Exception as e:
            print(f"⚠️ 도서 평가 실패: {e}")
            return {
                "evaluation_summary": "평가 중 오류 발생",
                "recommendation_decision": "추천불가",
                "recommended_books": [],
                "alternative_suggestion": "검색어를 바꿔서 다시 검색해보세요."
            }
    
    def suggest_alternative_books(self, topic: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """도서를 찾지 못한 경우 LLM이 직접 추천"""
        prompt = f"""
고등학생 탐구주제: "{topic}"

주제 분석:
- 핵심 개념: {', '.join(analysis.get('core_concepts', []))}
- 학문 분야: {analysis.get('academic_field', '')}

네이버 도서 검색에서 적합한 도서를 찾지 못했습니다.
이 주제를 연구하는 고등학생에게 도움이 될 수 있는 도서를 직접 추천해주세요.

다음 형식으로 응답해주세요:

{{
    "evaluation_summary": "도서 검색 결과 요약",
    "recommendation_decision": "직접추천/추천불가",
    "recommended_books": [
        {{
            "title": "추천 도서명",
            "author": "저자명 (알려진 경우)",
            "publisher": "출판사 (알려진 경우)",
            "recommendation_reason": "이 도서를 추천하는 이유 (100-150자)",
            "search_tip": "이 도서를 찾는 방법이나 대체 검색어",
            "overall_rating": "A/B/C"
        }}
    ],
    "alternative_suggestion": "다른 접근 방법이나 추가 조언"
}}

- 실제 존재하는 도서만 추천
- 고등학생 수준에 적합한 도서
- 최대 2권까지
- 정말 관련 도서가 없다면 솔직히 "추천불가"
"""
        
        try:
            with self.lock:
                self.api_usage['gemini_calls'] += 1
            
            response = self.model.generate_content(prompt)
            
            # JSON 파싱
            content = response.text.strip()
            if content.startswith('```json'):
                content = content[7:-3].strip()
            elif content.startswith('```'):
                content = content[3:-3].strip()
            
            return json.loads(content)
            
        except Exception as e:
            print(f"⚠️ 대안 도서 제안 실패: {e}")
            return {
                "evaluation_summary": "관련 도서를 찾을 수 없습니다",
                "recommendation_decision": "추천불가",
                "recommended_books": [],
                "alternative_suggestion": "다른 키워드나 관련 주제로 검색해보세요."
            }
    
    def clean_html_tags(self, text: str) -> str:
        """HTML 태그 제거"""
        import re
        clean_text = re.sub('<.*?>', '', text)
        return clean_text.strip()
    
    def process_single_topic(self, topic: str) -> Dict[str, Any]:
        """단일 주제 처리"""
        print(f"\n🔍 주제 분석: {topic[:50]}...")
        
        # 1단계: LLM 주제 분석
        analysis = self.analyze_topic_with_llm(topic)
        print(f"📋 학문분야: {analysis.get('academic_field', '')}")
        print(f"📈 예상 난이도: {analysis.get('expected_difficulty', '')}")
        
        # 2단계: 전략적 도서 검색
        books = self.search_books_with_strategy(analysis)
        
        # 3단계: LLM 지능형 평가
        evaluation = self.intelligent_book_evaluation(topic, books, analysis)
        
        # 결과 정리
        result = {
            "topic": topic,
            "topic_analysis": analysis,
            "total_books_found": len(books),
            "evaluation": evaluation,
            "recommendation_decision": evaluation.get("recommendation_decision", "추천불가"),
            "recommended_books": evaluation.get("recommended_books", []),
            "verified_books_count": len(evaluation.get("recommended_books", []))
        }
        
        print(f"✅ 최종 결과: {result['recommendation_decision']} ({result['verified_books_count']}권)")
        
        return result
    
    def process_multiple_topics(self, df: pd.DataFrame, max_workers: int = 5) -> List[Dict[str, Any]]:
        """여러 주제 병렬 처리"""
        results = []
        start_time = time.time()
        
        print(f"🚀 {len(df)}개 주제 처리 시작 (병렬 {max_workers}개)")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 작업 제출
            future_to_topic = {}
            for _, row in df.iterrows():
                topic = row['task']
                future = executor.submit(self.process_single_topic, topic)
                future_to_topic[future] = topic
            
            # 결과 수집
            for future in as_completed(future_to_topic):
                try:
                    result = future.result()
                    results.append(result)
                    
                    topic = future_to_topic[future]
                    print(f"✅ 완료 ({len(results)}/{len(df)}): {topic[:30]}...")
                    
                except Exception as e:
                    topic = future_to_topic[future]
                    print(f"❌ 실패: {topic[:30]}... - {e}")
                    results.append({
                        "topic": topic,
                        "error": str(e),
                        "verified_books_count": 0
                    })
        
        end_time = time.time()
        print(f"⏱️ 총 처리 시간: {end_time - start_time:.1f}초")
        
        return results
    
    def save_results(self, results: List[Dict[str, Any]], output_prefix: str = None):
        """결과 저장"""
        if not output_prefix:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_prefix = f"intelligent_recommendations_{timestamp}"
        
        # JSON 저장
        json_path = f"../결과파일/{output_prefix}.json"
        output_data = {
            "total_topics": len(results),
            "system_type": "intelligent_llm_system",
            "results": results,
            "api_usage": self.api_usage
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 결과 저장: {json_path}")
        
        # 통계 출력
        total_topics = len(results)
        recommended_topics = sum(1 for r in results if r.get('verified_books_count', 0) > 0)
        no_recommendation = total_topics - recommended_topics
        
        print(f"\n📊 최종 통계:")
        print(f"  전체 주제: {total_topics}개")
        print(f"  추천 성공: {recommended_topics}개 ({recommended_topics/total_topics*100:.1f}%)")
        print(f"  추천 없음: {no_recommendation}개 ({no_recommendation/total_topics*100:.1f}%)")
        print(f"  API 사용량: Gemini {self.api_usage['gemini_calls']}회, 네이버 {self.api_usage['naver_calls']}회")

def main():
    """메인 실행 함수"""
    print("🤖 지능형 LLM 도서 추천 시스템")
    print("=" * 50)
    
    # 시스템 초기화
    system = IntelligentBookRecommendationSystem()
    
    # 입력 파일 확인 (50개 주제만)
    input_file = "../원천파일/주제테스트_50.xlsx"
    
    if not os.path.exists(input_file):
        print(f"❌ 입력 파일을 찾을 수 없습니다: {input_file}")
        return
    
    # 데이터 로드
    print(f"📂 입력 파일: {input_file}")
    df = pd.read_excel(input_file)
    print(f"📊 총 {len(df)}개 주제 로드")
    
    # 처리 시작
    results = system.process_multiple_topics(df, max_workers=3)
    
    # 결과 저장
    system.save_results(results)
    
    print("\n✅ 모든 처리가 완료되었습니다!")

if __name__ == "__main__":
    main() 