
import os

from langchain import hub
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough


def create_rag_chain(db, openai_key: str):
    """
    Chroma DB와 API 키로 RAG 체인을 생성한다.
    """

    if db is None:
        raise ValueError("먼저 PDF를 업로드하고 처리해주세요.")

    if not openai_key or not openai_key.strip():
        raise ValueError("OpenAI API 키를 입력해주세요.")

    # 검색 질의를 여러 형태로 확장할 때 사용할 LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=openai_key.strip(),
    )

    # 질문을 여러 표현으로 바꿔 관련 문서를 검색
    retriever = MultiQueryRetriever.from_llm(
        retriever=db.as_retriever(
            search_kwargs={"k": 4}
        ),
        llm=llm,
    )

    # LangChain Hub에서 RAG 프롬프트 가져오기
    prompt = hub.pull("rlm/rag-prompt")

    def format_docs(docs):
        return "\n\n".join(
            f"[페이지 {doc.metadata.get('page', 0) + 1}]\n"
            f"{doc.page_content}"
            for doc in docs
        )

    # LCEL: 검색 결과 + 질문 → 프롬프트 → LLM → 문자열
    rag_chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return rag_chain


def answer(question: str, openai_key: str, db):
    """
    RAG 체인으로 답변을 생성하고 누적 텍스트를 스트리밍한다.
    """

    if db is None:
        raise ValueError("먼저 PDF를 업로드해주세요.")

    if not question or not question.strip():
        raise ValueError("질문을 입력해주세요.")

    rag_chain = create_rag_chain(db, openai_key)

    accumulated_text = ""

    for chunk in rag_chain.stream(question.strip()):
        accumulated_text += chunk
        yield accumulated_text
