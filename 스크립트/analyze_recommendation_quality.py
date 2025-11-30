#!/usr/bin/env python3.11
"""
추천 결과 품질 분석 스크립트
- 정상 추천 vs 오류 추천 vs 미추천 분류
- "시스템 오류로 인한 기본 추천입니다" 같은 문제 데이터 탐지
- 각 카테고리별 통계 및 샘플 출력
"""

import json
import pandas as pd
from collections import defaultdict
import re

def analyze_recommendation_data(json_file_path: str):
    """추천 데이터 품질 분석"""
    
    print("📊 추천 결과 품질 분석 시작")
    print("="*80)
    
    # JSON 파일 로드
    print("📂 데이터 로딩 중...")
    with open(json_file_path, 'r', encoding='utf-8') as f:
        json_data = json.load(f)
    
    # 실제 데이터는 results 키 안에 있음
    if isinstance(json_data, dict) and 'results' in json_data:
        data = json_data['results']
        total_topics = json_data.get('total_topics', len(data))
        print(f"✅ 총 {len(data):,}개 항목 로드 (전체 {total_topics:,}개)")
    else:
        # 이전 형태의 JSON (리스트)
        data = json_data
        print(f"✅ 총 {len(data):,}개 항목 로드")
    print("="*80)
    
    # 분류 카운터
    categories = {
        'normal_2_books': [],      # 정상 2권 추천
        'normal_1_book': [],       # 정상 1권 추천
        'system_error': [],        # 시스템 오류 메시지 포함
        'no_recommendation': [],   # 추천 없음
        'empty_reason': [],        # 추천 이유 누락
        'suspicious': []           # 의심스러운 데이터
    }
    
    # 오류 키워드들
    error_keywords = [
        "시스템 오류로 인한 기본 추천입니다",
        "시스템 오류",
        "기본 추천",
        "오류로 인한",
        "처리 실패",
        "임시 추천",
        "자동 생성된 추천",
        "default recommendation",
        "system error"
    ]
    
    print("🔍 데이터 분석 중...")
    
    for idx, item in enumerate(data):
        topic_id = item.get('id', f'unknown_{idx}')
        topic = item.get('topic', '')
        recommended_books = item.get('recommended_books', [])
        
        # 추천 도서 개수
        book_count = len(recommended_books)
        
        # 1. 추천 없음
        if book_count == 0:
            categories['no_recommendation'].append({
                'id': topic_id,
                'topic': topic[:100] + '...' if len(topic) > 100 else topic,
                'total_books_found': item.get('total_books_found', 0),
                'verified_books_count': item.get('verified_books_count', 0)
            })
            continue
        
        # 추천 이유들 수집
        all_reasons = []
        books_info = []
        has_error = False
        has_empty_reason = False
        
        for book in recommended_books:
            title = book.get('title', '')
            reason = book.get('recommendation_reason', '')
            rating = book.get('quality_rating', '')
            
            books_info.append({
                'title': title,
                'author': book.get('author', ''),
                'rating': rating,
                'reason': reason
            })
            
            all_reasons.append(reason)
            
            # 오류 메시지 체크
            reason_lower = reason.lower()
            if any(keyword in reason_lower for keyword in error_keywords):
                has_error = True
            
            # 빈 추천 이유 체크
            if not reason.strip():
                has_empty_reason = True
        
        # 2. 시스템 오류 메시지 포함
        if has_error:
            error_found = []
            for reason in all_reasons:
                for keyword in error_keywords:
                    if keyword in reason.lower():
                        error_found.append(keyword)
            
            categories['system_error'].append({
                'id': topic_id,
                'topic': topic[:100] + '...' if len(topic) > 100 else topic,
                'book_count': book_count,
                'books': books_info,
                'error_keywords': list(set(error_found))
            })
            continue
        
        # 3. 추천 이유 누락
        if has_empty_reason:
            categories['empty_reason'].append({
                'id': topic_id,
                'topic': topic[:100] + '...' if len(topic) > 100 else topic,
                'book_count': book_count,
                'books': books_info
            })
            continue
        
        # 4. 의심스러운 패턴 체크
        suspicious_issues = []
        
        for i, book in enumerate(books_info):
            reason = book['reason']
            
            # 너무 짧은 추천 이유
            if len(reason) < 50:
                suspicious_issues.append(f"도서{i+1}: 추천이유 너무 짧음 ({len(reason)}자)")
            
            # "추천"만 반복
            if "추천" in reason and len(reason) < 100:
                suspicious_issues.append(f"도서{i+1}: 단순 반복 의심")
            
            # F등급 도서가 추천됨
            if book['rating'] == 'F':
                suspicious_issues.append(f"도서{i+1}: F등급 추천")
        
        # 동일한 추천 이유
        if len(set(all_reasons)) < len(all_reasons):
            suspicious_issues.append("동일한 추천이유 반복")
        
        if suspicious_issues:
            categories['suspicious'].append({
                'id': topic_id,
                'topic': topic[:100] + '...' if len(topic) > 100 else topic,
                'book_count': book_count,
                'books': books_info,
                'issues': suspicious_issues
            })
            continue
        
        # 5. 정상 분류
        if book_count >= 2:
            categories['normal_2_books'].append({
                'id': topic_id,
                'topic': topic[:100] + '...' if len(topic) > 100 else topic,
                'book_count': book_count,
                'books': books_info
            })
        else:  # book_count == 1
            categories['normal_1_book'].append({
                'id': topic_id,
                'topic': topic[:100] + '...' if len(topic) > 100 else topic,
                'book_count': book_count,
                'books': books_info
            })
    
    # 결과 출력
    print("📊 분석 결과")
    print("="*80)
    
    total = len(data)
    
    print(f"🎯 정상 2권 이상 추천: {len(categories['normal_2_books']):,}개 ({len(categories['normal_2_books'])/total*100:.1f}%)")
    print(f"📚 정상 1권 추천: {len(categories['normal_1_book']):,}개 ({len(categories['normal_1_book'])/total*100:.1f}%)")
    print(f"❌ 시스템 오류 포함: {len(categories['system_error']):,}개 ({len(categories['system_error'])/total*100:.1f}%)")
    print(f"📭 추천 없음: {len(categories['no_recommendation']):,}개 ({len(categories['no_recommendation'])/total*100:.1f}%)")
    print(f"📝 추천이유 누락: {len(categories['empty_reason']):,}개 ({len(categories['empty_reason'])/total*100:.1f}%)")
    print(f"⚠️ 의심스러운 데이터: {len(categories['suspicious']):,}개 ({len(categories['suspicious'])/total*100:.1f}%)")
    
    print("\n" + "="*80)
    
    # 문제 데이터 상세 분석
    if categories['system_error']:
        print(f"🚨 시스템 오류 포함 데이터 샘플 (총 {len(categories['system_error'])}개)")
        print("-" * 60)
        for i, item in enumerate(categories['system_error'][:5]):
            print(f"{i+1}. ID: {item['id']}")
            print(f"   주제: {item['topic']}")
            print(f"   추천도서 수: {item['book_count']}권")
            for j, book in enumerate(item['books']):
                print(f"   도서{j+1}: {book['title']} ({book['rating']}등급)")
                print(f"   이유{j+1}: {book['reason'][:150]}...")
            print(f"   오류키워드: {item['error_keywords']}")
            print()
        if len(categories['system_error']) > 5:
            print(f"   ... 외 {len(categories['system_error'])-5}개 더")
        print()
    
    if categories['suspicious']:
        print(f"⚠️ 의심스러운 데이터 샘플 (총 {len(categories['suspicious'])}개)")
        print("-" * 60)
        for i, item in enumerate(categories['suspicious'][:3]):
            print(f"{i+1}. ID: {item['id']}")
            print(f"   주제: {item['topic']}")
            print(f"   추천도서 수: {item['book_count']}권")
            for j, book in enumerate(item['books']):
                print(f"   도서{j+1}: {book['title']} ({book['rating']}등급)")
                print(f"   이유{j+1}: {book['reason']}")
            print(f"   문제점: {item['issues']}")
            print()
        if len(categories['suspicious']) > 3:
            print(f"   ... 외 {len(categories['suspicious'])-3}개 더")
        print()
    
    # 추천 없음 상세 분석
    if categories['no_recommendation']:
        print(f"📭 추천 없음 데이터 샘플 (총 {len(categories['no_recommendation'])}개)")
        print("-" * 60)
        for i, item in enumerate(categories['no_recommendation'][:3]):
            print(f"{i+1}. ID: {item['id']}")
            print(f"   주제: {item['topic']}")
            print(f"   검색된 도서: {item['total_books_found']}권")
            print(f"   검증된 도서: {item['verified_books_count']}권")
            print()
        if len(categories['no_recommendation']) > 3:
            print(f"   ... 외 {len(categories['no_recommendation'])-3}개 더")
        print()
    
    # 정상 데이터 샘플
    if categories['normal_2_books']:
        print(f"✅ 정상 2권 이상 추천 샘플 (총 {len(categories['normal_2_books'])}개)")
        print("-" * 60)
        for i, item in enumerate(categories['normal_2_books'][:2]):
            print(f"{i+1}. ID: {item['id']}")
            print(f"   주제: {item['topic']}")
            print(f"   추천도서 수: {item['book_count']}권")
            for j, book in enumerate(item['books'][:2]):  # 최대 2권만 표시
                print(f"   도서{j+1}: {book['title']} ({book['rating']}등급)")
            print()
    
    # 통계 요약
    print("="*80)
    print("📈 요약 통계")
    successful = len(categories['normal_2_books']) + len(categories['normal_1_book'])
    problematic = len(categories['system_error']) + len(categories['empty_reason']) + len(categories['suspicious'])
    
    print(f"🎯 정상 추천 성공률: {successful/total*100:.1f}% ({successful:,}/{total:,})")
    print(f"🚨 문제 데이터 비율: {problematic/total*100:.1f}% ({problematic:,}/{total:,})")
    print(f"📭 추천 실패 비율: {len(categories['no_recommendation'])/total*100:.1f}% ({len(categories['no_recommendation']):,}/{total:,})")
    
    if problematic > 0:
        print(f"\n⚠️ 경고: {problematic:,}개의 문제 데이터가 발견되었습니다!")
        print("이 데이터들은 학생들에게 제공하기 전에 반드시 수정되어야 합니다.")
    
    print("="*80)
    
    return categories

def main():
    json_file = '../결과파일/book_recommendations_주제_테스트_250205_COMPLETE_20250716_041727.json'
    
    try:
        categories = analyze_recommendation_data(json_file)
        
        # 문제 데이터가 있으면 경고
        problem_count = len(categories['system_error']) + len(categories['empty_reason'])
        if problem_count > 0:
            print(f"\n🚨 심각한 문제: {problem_count}개의 오류 데이터가 발견되었습니다!")
            print("이 데이터들은 학생들에게 제공하기 전에 반드시 수정되어야 합니다.")
        
    except Exception as e:
        print(f"❌ 분석 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 