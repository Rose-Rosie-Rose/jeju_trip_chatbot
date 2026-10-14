
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough


def format_docs(docs):
    """검색된 문서 청크들을 하나의 참고자료로 합친다."""
    formatted_docs = []

    for doc in docs:
        page = doc.metadata.get("page", 0) + 1

        formatted_docs.append(
            f"[PDF {page}페이지]\n{doc.page_content}"
        )

    return "\n\n".join(formatted_docs)


def build_qa_chain(db, api_key):
    """검색된 PDF 내용을 바탕으로 답변하는 RAG 체인을 생성한다."""

    # 1. 벡터 DB에서 관련 문서 3개를 검색
    retriever = db.as_retriever(
        search_kwargs={"k": 3}
    )

    # 2. LLM에게 전달할 프롬프트
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
            당신은 PDF 문서를 기반으로 답변하는 여행 안내 챗봇입니다.

            반드시 제공된 [참고자료]만 근거로 답변하세요.

            규칙:
            1. 질문에 대한 답을 한국어로 자연스럽게 설명하세요.
            2. 질문과 관련된 정보만 활용하세요.
            3. 참고자료에 없는 사실은 추측하거나 지어내지 마세요.
            4. 답을 확인할 수 없다면
               "제공된 문서에서 답변을 확인할 수 없습니다."
               라고 답하세요.
            5. 참고자료에 페이지 정보가 있다면
               답변 끝에 출처 페이지를 표시하세요.
            """
        ),
        (
            "human",
            """
            [참고자료]
            {context}

            [질문]
            {question}
            """
        ),
    ])

    # 3. 답변을 생성할 LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=api_key,
    )

    # 4. 검색 → 프롬프트 구성 → LLM 답변 생성
    qa_chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )

    return qa_chain
