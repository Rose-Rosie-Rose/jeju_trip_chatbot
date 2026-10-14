
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from rag.pdf_processor import build_db


# ---------- 기본 설정 ----------
BASE_DIR = Path(__file__).resolve().parent

PDF_DIR = BASE_DIR / "data" / "pdfs"
PDF_PATHS = list(PDF_DIR.glob("*.pdf"))

for pdf_path in PDF_PATHS:
    print(f"처리할 PDF: {pdf_path.name}")

MODEL = "gpt-4o-mini"
TOP_K = 4

load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("OPENAI_API_KEY", "").strip()

if not api_key:
    raise ValueError(
        "OPENAI_API_KEY가 프로젝트 폴더의 .env에 설정되어 있지 않습니다."
    )

client = OpenAI(api_key=api_key)


# ---------- 답변 생성 프롬프트 ----------
SYSTEM_PROMPT = """You are a friendly travel assistant for foreign visitors.

Answer ONLY using the document excerpts provided below.
The excerpts may be written in Korean. Read them carefully
and answer in clear, natural English.

Rules:
- If the answer is not in the excerpts, reply exactly:
  "I'm sorry, I couldn't find that information in the document."
- Never make up facts, prices, opening hours, or locations.
- For Korean place names, give the English romanization with
  the Korean in parentheses, e.g. Seongsan Ilchulbong (성산일출봉).
- At the end, list the pages you used, e.g. (Source: p.2, p.5).
"""


def to_korean_query(question: str) -> str:
    """영어 질문을 한국어 문서 검색용 질의로 번역한다."""
    res = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Translate the user's question into natural Korean "
                    "for searching a Korean document. "
                    "Output only the translation."
                ),
            },
            {
                "role": "user",
                "content": question,
            },
        ],
    )

    return res.choices[0].message.content.strip()


def retrieve(db, question: str):
    """원문 질문과 한국어 번역 질문으로 검색하고 중복을 제거한다."""
    korean_query = to_korean_query(question)

    print(f"(검색용 한국어 질의: {korean_query})")

    seen = set()
    docs = []

    for query in (question, korean_query):
        results = db.similarity_search(query, k=TOP_K)

        for doc in results:
            key = (
                doc.metadata.get("page"),
                doc.page_content,
            )

            if key not in seen:
                seen.add(key)
                docs.append(doc)

    return docs


def answer_in_english(question: str, docs) -> str:
    """검색된 PDF 내용을 근거로 영어 답변을 생성한다."""
    context = "\n\n".join(
        f"[p.{doc.metadata.get('page', 0) + 1}]\n"
        f"{doc.page_content}"
        for doc in docs
    )

    res = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"Document excerpts:\n{context}\n\n"
                    f"Question: {question}"
                ),
            },
        ],
    )

    return res.choices[0].message.content.strip()


def main():
    print("=" * 40)
    print("PDF RAG Travel Chatbot")
    print("=" * 40)

    # 1. PDF 폴더 확인
    if not PDF_DIR.is_dir():
        raise FileNotFoundError(
            f"PDF 폴더를 찾을 수 없습니다: {PDF_DIR}"
        )

    if not PDF_PATHS:
        raise FileNotFoundError(
            f"PDF 폴더에 PDF 파일이 없습니다: {PDF_DIR}"
        )

    # 2. 각 PDF를 처리해 문서 청크 수집
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_openai import OpenAIEmbeddings
    from langchain_chroma import Chroma

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
    )

    all_chunks = []
    total_pages = 0

    for pdf_path in PDF_PATHS:
        print(f"\nPDF 처리 중: {pdf_path.name}")

        loader = PyPDFLoader(str(pdf_path))
        pages = loader.load()
        chunks = splitter.split_documents(pages)

        # 출처 파일명을 메타데이터에 보존
        for chunk in chunks:
            chunk.metadata["source_file"] = pdf_path.name

        all_chunks.extend(chunks)
        total_pages += len(pages)

        print(f"  페이지 수: {len(pages)}")
        print(f"  청크 수: {len(chunks)}")

    # 3. 모든 PDF의 청크로 벡터 DB 생성
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key,
    )

    db = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        collection_name="travel_pdfs",
    )

    print("\n전체 PDF 벡터 DB 생성 성공!")
    print(f"PDF 파일 수: {len(PDF_PATHS)}")
    print(f"전체 페이지 수: {total_pages}")
    print(f"전체 청크 수: {len(all_chunks)}")

    # 4. 질의응답
    print("\n챗봇이 준비되었습니다. Enter 또는 q를 입력하면 종료합니다.")

    while True:
        question = input("\nQuestion: ").strip()

        if not question or question.lower() == "q":
            print("Bye!")
            break

        try:
            docs = retrieve(db, question)

            if not docs:
                print(
                    "\nI'm sorry, I couldn't find that information "
                    "in the document."
                )
                continue

            print("\n--- Answer ---")
            print(answer_in_english(question, docs))

            # 출처 PDF 파일명과 페이지 표시
            sources = sorted({
                (
                    doc.metadata.get("source_file", "Unknown"),
                    doc.metadata.get("page", 0) + 1,
                )
                for doc in docs
            })

            print("\n--- Sources ---")
            for filename, page in sources:
                print(f"{filename}: p.{page}")

        except Exception as e:
            print(f"\n오류가 발생했습니다: {e}")


if __name__ == "__main__":
    main()
