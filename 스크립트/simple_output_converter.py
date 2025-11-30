#!/usr/bin/env python3.11
"""
간단한 출력 변환기
- 기존 상세 결과에서 핵심 정보만 추출
- 사용자 친화적인 형태로 변환
- 해당 스크립트는 주제에 대한 추천도서에 대한 점수를 내부 계산에만 유지하고, 최종 출력에서는 제거하는 변환 스크립트이다!!!!!!
"""

import json
import pandas as pd
from datetime import datetime
import os

class SimpleOutputConverter:
    def __init__(self):
        """변환기 초기화"""
        self.input_file = '../결과파일/book_recommendations_fixed.json'
        self.output_file = f'../결과파일/simple_recommendations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        self.excel_file = f'../결과파일/simple_recommendations_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    def convert_to_simple_format(self):
        """복잡한 결과를 간단한 형태로 변환"""
        
        # 기존 결과 파일 로드
        if not os.path.exists(self.input_file):
            print(f"오류: {self.input_file} 파일을 찾을 수 없습니다.")
            return
        
        with open(self.input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        simple_results = []
        
        for i, result in enumerate(data['results'], 1):
            topic = result['topic']
            keywords = result['keywords']
            recommended_books = result['recommended_books']
            
            # 간단한 형태로 변환
            simple_result = {
                "번호": i,
                "탐구주제": topic,
                "키워드": keywords,
                "추천도서_개수": len(recommended_books),
                "추천도서": []
            }
            
            # 추천도서 정보 간단하게 정리
            for book in recommended_books[:2]:  # 최대 2권만
                simple_book = {
                    "순위": book['rank'],
                    "도서명": book['title'],
                    "저자": book['author'],
                    "출판사": book['publisher'],
                    "출간일": book['publication_date'],
                    "ISBN": book['isbn'],
                    "추천이유": book['recommendation_reason']
                }
                simple_result["추천도서"].append(simple_book)
            
            simple_results.append(simple_result)
        
        # JSON 파일로 저장
        output_data = {
            "생성일시": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "전체주제수": len(simple_results),
            "추천도서가_있는_주제": len([r for r in simple_results if r["추천도서_개수"] > 0]),
            "추천도서가_없는_주제": len([r for r in simple_results if r["추천도서_개수"] == 0]),
            "결과": simple_results
        }
        
        with open(self.output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 간단한 형태의 JSON 결과 생성: {self.output_file}")
        
        # Excel 파일로도 저장
        self.create_excel_output(simple_results)
        
        return output_data
    
    def create_excel_output(self, simple_results):
        """원본 엑셀 구조를 유지하면서 점수 제거한 형태로 출력"""
        
        excel_data = []
        
        for result in simple_results:
            # 기본 정보
            row = {
                "번호": result["번호"],
                "탐구주제": result["탐구주제"],
                "키워드": ", ".join(result["키워드"]),
                "학문분야": "미분류",  # 원본에서 가져올 수 있으면 가져오기
                "발견도서수": result["추천도서_개수"],
            }
            
            # 추천도서 정보 (원본 구조처럼 1행에 모두 포함)
            for i in range(1, 3):  # 추천도서1, 추천도서2
                if i <= len(result["추천도서"]):
                    book = result["추천도서"][i-1]
                    row.update({
                        f"추천도서{i}_제목": book["도서명"],
                        f"추천도서{i}_저자": book["저자"],
                        f"추천도서{i}_출판사": book["출판사"],
                        f"추천도서{i}_출간일": book["출간일"],
                        f"추천도서{i}_ISBN": book["ISBN"],
                        f"추천도서{i}_추천이유": book["추천이유"][:100] + "..." if len(book["추천이유"]) > 100 else book["추천이유"]
                    })
                else:
                    # 추천도서가 없는 경우 빈 값으로 채우기
                    row.update({
                        f"추천도서{i}_제목": "",
                        f"추천도서{i}_저자": "",
                        f"추천도서{i}_출판사": "",
                        f"추천도서{i}_출간일": "",
                        f"추천도서{i}_ISBN": "",
                        f"추천도서{i}_추천이유": ""
                    })
            
            excel_data.append(row)
        
        df = pd.DataFrame(excel_data)
        df.to_excel(self.excel_file, index=False, engine='openpyxl')
        print(f"✅ Excel 결과 생성 (원본 구조 유지): {self.excel_file}")
    
    def create_excel_output_with_original_structure(self):
        """원본 JSON 파일에서 직접 읽어서 원본 구조 유지하며 점수만 제거"""
        
        # 원본 JSON 파일 로드
        with open(self.input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 원본 Excel 파일에서 ID 가져오기
        original_excel_df = pd.read_excel('../원천파일/주제테스트_50.xlsx')
        ids = original_excel_df['id'].tolist()
        
        excel_data = []
        
        for idx, result in enumerate(data['results'], 1):
            # 기본 정보 (ID 포함)
            row = {
                "id": ids[idx-1] if idx-1 < len(ids) else f"hz-topic::{idx}",
                "탐구주제": result['topic'],
                "키워드": ", ".join(result['keywords']),
                "학문분야": result['topic_analysis'].get('academic_field', '미분류'),
                "발견도서수": result['total_books_found'],
            }
            
            # 추천도서 정보 (원본 구조처럼 1행에 모두 포함)
            recommended_books = result.get('recommended_books', [])
            
            for i in range(1, 3):  # 추천도서1, 추천도서2
                if i <= len(recommended_books):
                    book = recommended_books[i-1]
                    row.update({
                        f"추천도서{i}_제목": book['title'],
                        f"추천도서{i}_저자": book['author'],
                        f"추천도서{i}_출판사": book['publisher'],
                        f"추천도서{i}_출간일": book['publication_date'],
                        f"추천도서{i}_ISBN": book['isbn'],
                        f"추천도서{i}_추천이유": book['recommendation_reason'][:150] + "..." if len(book['recommendation_reason']) > 150 else book['recommendation_reason']
                    })
                else:
                    # 추천도서가 없는 경우 빈 값으로 채우기
                    row.update({
                        f"추천도서{i}_제목": "",
                        f"추천도서{i}_저자": "",
                        f"추천도서{i}_출판사": "",
                        f"추천도서{i}_출간일": "",
                        f"추천도서{i}_ISBN": "",
                        f"추천도서{i}_추천이유": ""
                    })
            
            excel_data.append(row)
        
        df = pd.DataFrame(excel_data)
        
        # 파일명 변경 (원본 구조 유지 표시)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.excel_file = f'../테스트결과파일/clean_recommendations_{timestamp}.xlsx'
        
        df.to_excel(self.excel_file, index=False, engine='openpyxl')
        print(f"✅ Excel 결과 생성 (원본 구조 유지, 점수 제거): {self.excel_file}")
        
        return len(excel_data)
    
    def print_summary(self, data):
        """요약 정보 출력"""
        print("\n" + "="*60)
        print("📊 간단한 형태 변환 완료!")
        print("="*60)
        print(f"📅 생성일시: {data['생성일시']}")
        print(f"📚 전체 주제 수: {data['전체주제수']}개")
        print(f"✅ 추천도서가 있는 주제: {data['추천도서가_있는_주제']}개")
        print(f"❌ 추천도서가 없는 주제: {data['추천도서가_없는_주제']}개")
        print(f"📈 추천 성공률: {data['추천도서가_있는_주제']/data['전체주제수']*100:.1f}%")
        
        print("\n🎯 포함된 정보:")
        print("  - 탐구주제")
        print("  - 키워드")
        print("  - 추천도서 (최대 2권)")
        print("  - 저자, 출판사, ISBN")
        print("  - 추천이유")
        
        print("\n🚫 제거된 정보:")
        print("  - 점수 및 세부 평가")
        print("  - 내부 처리 정보")
        print("  - 검색 메타데이터")

def main():
    """메인 실행 함수"""
    print("📝 원본 구조 유지 변환 시작...")
    print("📋 원본 엑셀 구조를 유지하면서 점수만 제거한 깔끔한 Excel 파일을 생성합니다.")
    
    converter = SimpleOutputConverter()
    
    # 원본 구조 유지 방식 (점수만 제거)
    total_rows = converter.create_excel_output_with_original_structure()
    
    print(f"\n✅ 원본 구조 유지 Excel 생성 완료!")
    print(f"📊 총 {total_rows}개 주제 처리")
    print(f"📁 생성된 파일: {converter.excel_file}")
    
    print(f"\n🎯 변경 사항:")
    print(f"  ✅ 원본 엑셀 구조 유지 (한 주제 = 한 행)")
    print(f"  ✅ 점수 관련 컬럼 제거 (추천도서1_점수, 추천도서2_점수)")
    print(f"  ✅ 핵심 정보만 유지 (제목, 저자, 출판사, 출간일, ISBN, 추천이유)")
    print(f"  ✅ 한국어 컬럼명 사용 (번호, 탐구주제, 키워드, 학문분야, 발견도서수)")
    
    print(f"\n💡 사용법:")
    print(f"  생성된 Excel 파일을 열어서 필요한 정보만 활용하세요.")
    print(f"  기존 상세 결과(JSON)는 그대로 유지되므로 필요시 참고 가능합니다.")

if __name__ == "__main__":
    main() 