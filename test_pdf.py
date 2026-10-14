
import os
from pathlib import Path

from dotenv import load_dotenv
from rag.pdf_processor import build_db

load_dotenv()

pdf_path = input("테스트할 PDF 경로: ").strip().strip('"')
api_key = os.getenv("OPENAI_API_KEY", "")

if not Path(pdf_path).is_file():
    raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

db, pages, chunks = build_db(pdf_path, api_key)

print(f"\n페이지 수: {len(pages)}")
print(f"청크 수: {len(chunks)}")
print("\n벡터 DB 생성 성공!")

question = input("\n검색할 질문을 입력하세요: ").strip()

if not question:
    raise ValueError("질문을 입력해주세요.")

results = db.similarity_search(question, k=3)

print("\n--- 검색 결과 ---")

for i, doc in enumerate(results, start=1):
    page = doc.metadata.get("page", 0) + 1

    print(f"\n[결과 {i} / 페이지 {page}]")
    print(doc.page_content[:400])
