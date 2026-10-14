
import uuid

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma


def load_and_split_pdf(pdf_path: str):
    """PDF를 로드하고 텍스트를 청크로 분할한다."""
    loader = PyPDFLoader(pdf_path)
    pages = loader.load()

    if not pages:
        raise ValueError("PDF에서 문서를 추출하지 못했습니다.")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
    )

    chunks = text_splitter.split_documents(pages)

    if not chunks:
        raise ValueError("PDF에서 분할할 텍스트를 찾지 못했습니다.")

    return pages, chunks


def build_db(pdf_path: str, openai_key: str):
    """PDF를 청킹하고 임베딩한 뒤 Chroma 벡터 DB를 생성한다."""
    if not openai_key or not openai_key.strip():
        raise ValueError("OpenAI API 키를 입력해주세요.")

    pages, chunks = load_and_split_pdf(pdf_path)

    embeddings_model = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=openai_key.strip(),
    )

    db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings_model,
        collection_name=f"pdf_{uuid.uuid4().hex}",
    )

    return db, pages, chunks
