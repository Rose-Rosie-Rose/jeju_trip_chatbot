import os
import re
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

# 청크 설정 (eval/tune_chunks.py 결과로 가장 점수가 높은 값을 넣으세요)
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100

# 외국인 사용자에게 보여줄 PDF 영어 제목 (파일명 → 제목)
PDF_TITLES = {
    "jjfood": "Jeju Food Guide",
    "jjmountain": "Jeju Oreum & Mountain Guide",
    "jjnight": "Jeju Night Tour Guide",
    "jjocean": "Jeju Ocean Guide",
}

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

Each excerpt starts with a tag like [#3 | Jeju Food Guide | p.5].

Rules:
- If the answer is not in the excerpts, reply exactly:
  "I'm sorry, I couldn't find that information in the document."
  and nothing else.
- Never make up facts, prices, opening hours, or locations.
- For Korean place names, give the English romanization with
  the Korean in parentheses, e.g. Seongsan Ilchulbong (성산일출봉).
- Do NOT write any source list or page numbers in your answer.
- If you did answer, add one last line with the excerpt numbers
  you actually used, exactly in this format: USED: 1, 3
"""

NOT_FOUND = "I'm sorry, I couldn't find that information in the document."


# ---------- 벡터 DB ----------
def build_vector_db(
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    collection_name: str = "travel_pdfs",
    verbose: bool = True,
):
    """PDF들을 청크로 나눠 벡터 DB를 만든다. (청크 튜닝 스크립트에서도 사용)"""
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_openai import OpenAIEmbeddings
    from langchain_chroma import Chroma

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    all_chunks = []
    total_pages = 0

    for pdf_path in PDF_PATHS:
        pages = PyPDFLoader(str(pdf_path)).load()
        chunks = splitter.split_documents(pages)

        # 출처 파일명을 메타데이터에 보존
        for chunk in chunks:
            chunk.metadata["source_file"] = pdf_path.name

        all_chunks.extend(chunks)
        total_pages += len(pages)

        if verbose:
            print(f"\nPDF 처리 중: {pdf_path.name}")
            print(f"  페이지 수: {len(pages)}")
            print(f"  청크 수: {len(chunks)}")

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=api_key,
    )

    db = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        collection_name=collection_name,
    )

    if verbose:
        print("\n전체 PDF 벡터 DB 생성 성공!")
        print(f"PDF 파일 수: {len(PDF_PATHS)}")
        print(f"전체 페이지 수: {total_pages}")
        print(f"전체 청크 수: {len(all_chunks)}")
        print(f"청크 설정: size={chunk_size}, overlap={chunk_overlap}")

    return db


# ---------- 검색 / 답변 ----------
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
                doc.metadata.get("source_file"),
                doc.metadata.get("page"),
                doc.page_content,
            )

            if key not in seen:
                seen.add(key)
                docs.append(doc)

    return docs


def pdf_file(doc) -> str:
    """원본 PDF 파일명 (예: jjfood.pdf)"""
    return doc.metadata.get("source_file", "Unknown")


def pdf_title(doc) -> str:
    """외국인에게 보여줄 PDF 영어 제목 (없으면 파일명)"""
    stem = Path(pdf_file(doc)).stem
    return PDF_TITLES.get(stem, stem)


def page_no(doc) -> int:
    """PDF 페이지 번호 (metadata['page']는 0부터 시작하므로 +1)"""
    return doc.metadata.get("page", 0) + 1


def answer_in_english(question: str, docs):
    """검색된 PDF 내용을 근거로 영어 답변을 생성한다.

    반환값: (답변 텍스트, 실제로 사용한 문서 리스트)
    """
    context = "\n\n".join(
        f"[#{i} | {pdf_title(doc)} | p.{page_no(doc)}]\n"
        f"{doc.page_content}"
        for i, doc in enumerate(docs, start=1)
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

    text = res.choices[0].message.content.strip()

    # 문서에 답이 없으면 출처 없이 반환
    if NOT_FOUND in text:
        return NOT_FOUND, []

    # "USED: 1, 3" 줄을 찾아 떼어내고, 실제 사용한 문서만 추림
    used_docs = []
    match = re.search(r"^\s*USED\s*:\s*(.*)$", text, re.IGNORECASE | re.MULTILINE)
    if match:
        for num in re.findall(r"\d+", match.group(1)):
            idx = int(num)
            if 1 <= idx <= len(docs) and docs[idx - 1] not in used_docs:
                used_docs.append(docs[idx - 1])
        text = (text[:match.start()] + text[match.end():]).strip()

    return text, used_docs


# ---------- 출처 표시 ----------
def _format_pages(pages) -> str:
    """[3, 4, 5, 9] → 'pages 3–5, 9' / [7] → 'page 7'"""
    pages = sorted(set(pages))
    ranges = []
    start = prev = pages[0]
    for p in pages[1:]:
        if p == prev + 1:
            prev = p
            continue
        ranges.append(f"{start}–{prev}" if start != prev else f"{start}")
        start = prev = p
    ranges.append(f"{start}–{prev}" if start != prev else f"{start}")

    label = "page" if len(pages) == 1 else "pages"
    return f"{label} {', '.join(ranges)}"


def format_sources(docs) -> str:
    """외국인 사용자용 출처 문자열을 만든다.

    예)
    Sources:
      • Jeju Food Guide (jjfood.pdf) — pages 24–25
      • Jeju Night Tour Guide (jjnight.pdf) — page 7
    """
    by_pdf = {}
    for doc in docs:
        key = (pdf_title(doc), pdf_file(doc))
        by_pdf.setdefault(key, []).append(page_no(doc))

    lines = ["Sources:"]
    for (title, filename), pages in sorted(by_pdf.items()):
        lines.append(f"  • {title} ({filename}) — {_format_pages(pages)}")
    return "\n".join(lines)


# ---------- 실행 ----------
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

    # 2~3. PDF 청크 → 벡터 DB
    db = build_vector_db()

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
                print(f"\n{NOT_FOUND}")
                continue

            answer, used_docs = answer_in_english(question, docs)

            print("\n--- Answer ---")
            print(answer)

            # 답을 찾았을 때만, 실제 사용한 페이지를 출처로 표시
            if used_docs:
                print()
                print(format_sources(used_docs))

        except Exception as e:
            print(f"\n오류가 발생했습니다: {e}")


if __name__ == "__main__":
    main()