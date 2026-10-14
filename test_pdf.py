import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from rag.pdf_processor import build_db

load_dotenv()

MODEL = "gpt-4o-mini"
TOP_K = 4

api_key = os.getenv("OPENAI_API_KEY", "")
if not api_key:
    raise ValueError("OPENAI_API_KEY가 .env에 설정되어 있지 않습니다.")

client = OpenAI(api_key=api_key)

SYSTEM_PROMPT = """You are a friendly travel assistant for foreign visitors.
Answer ONLY using the document excerpts provided below.
The excerpts may be written in Korean. Read them carefully and answer in clear, natural English.

Rules:
- If the answer is not in the excerpts, reply exactly:
  "I'm sorry, I couldn't find that information in the document."
- Never make up facts, prices, opening hours, or locations.
- For Korean place names, give the English romanization with the Korean in parentheses,
  e.g. Seongsan Ilchulbong (성산일출봉).
- At the end, list the pages you used, e.g. (Source: p.3, p.5)."""


def to_korean_query(question: str) -> str:
    """영어 질문을 한국어 문서 검색용 질의로 번역"""
    res = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "Translate the user's question into natural Korean "
                           "for searching a Korean document. Output only the translation.",
            },
            {"role": "user", "content": question},
        ],
    )
    return res.choices[0].message.content.strip()


def retrieve(db, question: str):
    """원문 질문 + 한국어 번역 질문으로 검색하고 중복 제거"""
    korean_query = to_korean_query(question)
    print(f"(검색용 한국어 질의: {korean_query})")

    seen, docs = set(), []
    for query in (question, korean_query):
        for doc in db.similarity_search(query, k=TOP_K):
            key = (doc.metadata.get("page"), doc.page_content[:100])
            if key not in seen:
                seen.add(key)
                docs.append(doc)
    return docs


def answer_in_english(question: str, docs) -> str:
    """검색된 문서 내용만 근거로 영어 답변 생성"""
    context = "\n\n".join(
        f"[p.{doc.metadata.get('page', 0) + 1}]\n{doc.page_content}" for doc in docs
    )
    res = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Document excerpts:\n{context}\n\nQuestion: {question}",
            },
        ],
    )
    return res.choices[0].message.content.strip()


# ---------- 실행 ----------
pdf_path = input("테스트할 PDF 경로: ").strip().strip('"')

if not Path(pdf_path).is_file():
    raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

db, pages, chunks = build_db(pdf_path, api_key)

print(f"\n페이지 수: {len(pages)}")
print(f"청크 수: {len(chunks)}")
print("\n벡터 DB 생성 성공!")

while True:
    question = input("\nAsk a question (press Enter to quit): ").strip()
    if not question:
        print("Bye!")
        break

    docs = retrieve(db, question)
    if not docs:
        print("\nI'm sorry, I couldn't find that information in the document.")
        continue

    print("\n--- Answer ---")
    print(answer_in_english(question, docs))

    used_pages = sorted({doc.metadata.get("page", 0) + 1 for doc in docs})
    print(f"\n(검색된 페이지: {used_pages})")