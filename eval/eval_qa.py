"""
testqa CSV의 질문을 챗봇에 자동으로 넣고, 정답과 비교해 ✅ / △ / ❌ 로 채점한다.
test_pdf.py의 함수(retrieve, answer_in_english)를 그대로 가져다 쓰고,
벡터 DB는 test_pdf.py main()과 같은 방식(같은 청크 설정)으로 만든다.

사용법 (eval/ 폴더에 두고, 프로젝트 루트에서 실행):
    python eval/eval_qa.py eval/testqa20.csv                  # "개선 전" 열에 결과 기록
    python eval/eval_qa.py eval/testqa20.csv --col "개선 후"  # "개선 후" 열에 결과 기록

결과: eval/<입력파일명>_결과.csv (엑셀에서 바로 열림)
"""

import argparse
import json
import sys
from pathlib import Path

# eval/ 폴더에서 실행해도 프로젝트 루트의 test_pdf.py, rag/ 를 찾을 수 있게 경로 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

import test_pdf
from test_pdf import client, retrieve, answer_in_english

JUDGE_MODEL = "gpt-4o-mini"

# test_pdf.py main()의 splitter 설정과 동일하게 맞춘 기본값
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
NOT_FOUND = "I'm sorry, I couldn't find that information in the document."

JUDGE_PROMPT = """당신은 여행 안내 챗봇의 답변을 채점하는 평가자입니다.
질문, 기대 정답, 챗봇 답변(영어)을 보고 아래 기준으로 판정하세요.

- ✅ : 기대 정답의 핵심 내용과 일치한다. (표현·언어가 달라도 의미가 같으면 정답)
- △ : 일부만 맞거나, 핵심은 맞지만 빠진 정보·불필요한 오류가 섞여 있다.
- ❌ : 틀렸거나, 답을 해야 하는데 "찾을 수 없다"고 했다.

특별 규칙:
- 바로 아래 규칙은 기대 정답 자체가 "Information not available / 정보 없음"이라고 적혀 있을 때만 적용한다.
  기대 정답에 구체적인 내용이 있는데 챗봇이 "찾을 수 없다"고 했으면 무조건 ❌.
- 기대 정답이 "자료에 정보 없음/답변 유보"인 경우, 챗봇이 정보가 없다고 답하거나
  답변을 유보했으면 ✅, 지어낸 구체 정보(시간, 가격, 좌석 등)를 제시했으면 ❌.
- 기대 정답에 여러 후보가 나열되고 질문이 "N개 추천"처럼 일부만 요구하면,
  후보 중에서 요구 개수만큼 맞게 답하면 ✅.

JSON으로만 답하세요: {"verdict": "✅" | "△" | "❌", "reason": "한국어로 한두 문장"}
"""


def load_questions(csv_path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]  # "정답 " 같은 공백 제거
    if "No" not in df.columns:
        df.insert(0, "No", range(1, len(df) + 1))
    if "질문 유형" not in df.columns:
        df["질문 유형"] = "-"
    return df


def build_db(chunk_size=None, chunk_overlap=None):
    """test_pdf.py main()과 같은 방식으로 DB 생성 (설정마다 다른 컬렉션 이름 사용)."""
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_openai import OpenAIEmbeddings
    from langchain_chroma import Chroma

    size = chunk_size or CHUNK_SIZE
    overlap = chunk_overlap if chunk_overlap is not None else CHUNK_OVERLAP

    if not test_pdf.PDF_PATHS:
        raise FileNotFoundError(f"PDF 폴더에 PDF 파일이 없습니다: {test_pdf.PDF_DIR}")

    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)

    all_chunks = []
    for pdf_path in test_pdf.PDF_PATHS:
        chunks = splitter.split_documents(PyPDFLoader(str(pdf_path)).load())
        for chunk in chunks:
            chunk.metadata["source_file"] = pdf_path.name
        all_chunks.extend(chunks)

    embeddings = OpenAIEmbeddings(model="text-embedding-3-small", api_key=test_pdf.api_key)
    return Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        collection_name=f"eval_{size}_{overlap}",
    )


def format_sources(docs) -> str:
    """test_pdf.py main()의 출처 표시와 같은 형식: 파일명: p.N"""
    sources = sorted({
        (doc.metadata.get("source_file", "Unknown"), doc.metadata.get("page", 0) + 1)
        for doc in docs
    })
    return ", ".join(f"{filename}: p.{page}" for filename, page in sources)


def ask_bot(db, question: str):
    """챗봇에 질문하고 (답변, 출처 문자열)을 돌려준다."""
    docs = retrieve(db, question)
    if not docs:
        return NOT_FOUND, ""

    answer = answer_in_english(question, docs)
    return answer, format_sources(docs)


def is_no_info(expected: str) -> bool:
    """기대 정답이 '자료에 정보 없음' 유형인지 (CSV는 'Information not available'로 표기)."""
    return "not available" in expected.lower() or "정보 없음" in expected


def judge(question: str, expected: str, answer: str):
    # 정답이 있는 질문에 "찾을 수 없다"고 답하면 LLM에 묻지 않고 바로 ❌
    # (채점 모델이 '정보 없음 → ✅' 규칙을 잘못 적용하는 경우가 있어서)
    if "couldn't find that information" in answer and not is_no_info(expected):
        return "❌", "문서에 정답이 있는데 챗봇이 '찾을 수 없다'고 답했다."

    res = client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {
                "role": "user",
                "content": (
                    f"질문: {question}\n\n"
                    f"기대 정답: {expected}\n\n"
                    f"챗봇 답변: {answer}"
                ),
            },
        ],
    )
    data = json.loads(res.choices[0].message.content)
    return data.get("verdict", "?"), data.get("reason", "")


def run_eval(db, df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """모든 질문을 실행·채점하고 결과 DataFrame을 돌려준다."""
    rows = []
    for _, row in df.iterrows():
        question = str(row["English (EN)"])  # 챗봇은 영어 질문 기준
        expected = str(row["정답"])

        if verbose:
            print(f"\n[{row['No']}] {question}")
        try:
            answer, src = ask_bot(db, question)
            verdict, reason = judge(row["질문"], expected, answer)
        except Exception as e:
            answer, src, verdict, reason = f"(오류) {e}", "", "❌", "실행 중 오류"

        if verbose:
            print(f"  → {verdict} {reason}")
        rows.append({
            "No": row["No"],
            "질문 유형": row["질문 유형"],
            "판정": verdict,
            "챗봇 답변": answer,
            "출처": src,
            "판정 이유": reason,
        })
    return pd.DataFrame(rows)


def score(verdicts) -> float:
    """✅=1, △=0.5, ❌=0 → 100점 만점"""
    verdicts = list(verdicts)
    ok = verdicts.count("✅")
    part = verdicts.count("△")
    return (ok + part * 0.5) / len(verdicts) * 100


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", help="질문 리스트 CSV 경로")
    parser.add_argument("--col", default="개선 전", help='결과를 적을 열 ("개선 전" 또는 "개선 후")')
    args = parser.parse_args()

    csv_path = Path(args.csv)
    df = load_questions(csv_path)

    print("벡터 DB 생성 중...")
    db = build_db()

    result = run_eval(db, df)

    col = args.col.strip()
    df[col] = result["판정"].values
    df[f"{col} 챗봇 답변"] = result["챗봇 답변"].values
    df[f"{col} 출처"] = result["출처"].values
    df[f"{col} 판정 이유"] = result["판정 이유"].values

    out_path = csv_path.with_name(f"{csv_path.stem}_결과.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    v = list(result["판정"])
    print("\n" + "=" * 40)
    print("유형별 결과")
    print(pd.crosstab(df["질문 유형"], df[col]))
    print(f"\n전체: ✅ {v.count('✅')} / △ {v.count('△')} / ❌ {v.count('❌')}  (총 {len(v)}문항)")
    print(f"점수(✅=1, △=0.5): {score(v):.1f}점")
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
