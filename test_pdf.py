
import os
from pathlib import Path

from dotenv import load_dotenv
from rag.pdf_processor import build_db
from rag.qa_chain import build_qa_chain

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

PDF_PATH = BASE_DIR / "sample.pdf"


def main():
    print("=" * 40)
    print("PDF RAG 챗봇")
    print("=" * 40)

    if not PDF_PATH.is_file():
        raise FileNotFoundError(
            f"PDF 파일을 찾을 수 없습니다: {PDF_PATH}"
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not api_key:
        raise ValueError(
            ".env 파일에 OPENAI_API_KEY를 설정해주세요."
        )

    # 1. PDF 처리 및 벡터 DB 생성
    print(f"\nPDF 파일: {PDF_PATH.name}")
    print("PDF 처리 및 벡터 DB 생성 중...")

    db, pages, chunks = build_db(
        pdf_path=str(PDF_PATH),
        openai_key=api_key,
    )

    print("\n벡터 DB 생성 완료!")
    print(f"페이지 수: {len(pages)}")
    print(f"청크 수: {len(chunks)}")

    # 2. RAG 체인 생성
    qa_chain = build_qa_chain(db, api_key)

    print("\n챗봇이 준비되었습니다.")
    print("질문을 입력하세요. 종료하려면 q를 입력하세요.")

    # 3. 질문에 대한 답변 생성
    while True:
        question = input("\n질문: ").strip()

        if question.lower() == "q":
            print("챗봇을 종료합니다.")
            break

        if not question:
            print("질문을 입력해주세요.")
            continue

        try:
            answer = qa_chain.invoke(question)

            print("\n[챗봇 답변]")
            print(answer)

        except Exception as e:
            print(f"\n답변 생성 중 오류가 발생했습니다: {e}")


if __name__ == "__main__":
    main()
