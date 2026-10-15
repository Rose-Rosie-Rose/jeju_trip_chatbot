"""
app.py 챗봇(rag/chatbot.py)을 평가 CSV로 채점한다.
app.py와 똑같이 rag.chatbot.ask()를 호출하므로, 화면에서 받는 답변과 같은 결과로 채점된다.

사용법 (프로젝트 루트에서):
    python eval/eval_app.py                           # 기본 CSV, 1회
    python eval/eval_app.py --repeat 3                # 3회 돌려 평균
    python eval/eval_app.py --label 개선후            # 결과 폴더 이름에 표시
    python eval/eval_app.py --chunk-size 500 --chunk-overlap 100   # 청크 설정만 바꿔서 비교

결과: eval/results/app_YYYYMMDD_HHMM[_라벨]/
    리포트.md   점수, 유형별 점수, 틀린 문항(△/❌) — 질문·정답·답변·출처·판정 이유
    상세.csv    전체 문항 결과 (엑셀에서 바로 열림)
"""

import argparse
import contextlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EVAL_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))  # rag 패키지 import용

import pandas as pd

from rag import chatbot as rag

DEFAULT_CSV = PROJECT_ROOT / "jeju_chatbot_evaluation_20.csv"
JUDGE_MODEL = "gpt-4o-mini"

# 앞 질문의 대화를 이어받아야 하는 문항: {후속 질문 번호: 앞 질문 번호}
# 예) Q16 "알려준 오름 2곳의 탐방 시간 비교" ← Q12 "초보자 오름 추천"
FOLLOW_UPS = {16: 12}

JUDGE_PROMPT = """당신은 여행 안내 챗봇의 답변을 채점하는 평가자입니다.
질문, 기대 정답, 챗봇 답변(영어)을 보고 아래 기준으로 판정하세요.

- ✅ : 기대 정답의 핵심 내용과 일치한다. (표현·언어가 달라도 의미가 같으면 정답)
- △ : 일부만 맞거나, 핵심은 맞지만 빠진 정보·불필요한 오류가 섞여 있다.
- ❌ : 틀렸거나, 답을 해야 하는데 "찾을 수 없다"고 했다.

특별 규칙:
- 기대 정답이 "자료에 정보 없음/답변 유보"인 경우에만: 챗봇이 정보가 없다고 하거나
  "가이드에 나와 있지 않다"처럼 답변을 유보했으면 ✅, 지어낸 구체 정보
  (시간, 가격, 좌석, 영업 여부 등)를 제시했으면 ❌.
- 기대 정답에 구체적인 내용이 있는데 챗봇이 "찾을 수 없다"고 했으면 ❌.
- 기대 정답에 여러 후보가 나열되고 질문이 "N개 추천"처럼 일부만 요구하면,
  후보 중에서 요구 개수만큼 맞게 답하면 ✅.

JSON으로만 답하세요: {"verdict": "✅" | "△" | "❌", "reason": "한국어로 한두 문장"}
"""


# ---------- 데이터 ----------
def load_questions(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]  # "정답 " 같은 공백 제거
    if "No" not in df.columns:
        df.insert(0, "No", range(1, len(df) + 1))
    if "질문 유형" not in df.columns:
        df["질문 유형"] = "-"
    df["No"] = df["No"].astype(str)
    return df


def q_num(no: str) -> int | None:
    """'Q05' / '5' → 5"""
    digits = "".join(ch for ch in str(no) if ch.isdigit())
    return int(digits) if digits else None


# ---------- 챗봇 호출 / 채점 ----------
def ask_bot(db, question: str, history=None):
    """app.py와 같은 rag.ask() 호출. (답변, 출처 문자열)"""
    with contextlib.redirect_stdout(io.StringIO()):  # "(검색용 질의: ...)" 출력 숨김
        answer, used_docs = rag.ask(db, question, history)
    sources = rag.format_sources(used_docs) if used_docs else ""
    return answer, sources


def is_no_info(expected: str) -> bool:
    return "not available" in expected.lower() or "정보 없음" in expected


def judge(question: str, expected: str, answer: str):
    # 정답이 있는데 고정 문구로 "못 찾음"이면 LLM에 묻지 않고 바로 ❌
    if answer.strip() == rag.NOT_FOUND and not is_no_info(expected):
        return "❌", "문서에 정답이 있는데 챗봇이 '찾을 수 없다'고 답했다."

    res = rag.client.chat.completions.create(
        model=JUDGE_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {
                "role": "user",
                "content": f"질문: {question}\n\n기대 정답: {expected}\n\n챗봇 답변: {answer}",
            },
        ],
    )
    data = json.loads(res.choices[0].message.content)
    return data.get("verdict", "?"), data.get("reason", "")


def score(verdicts) -> float:
    """✅=1, △=0.5, ❌=0 → 100점 만점"""
    v = list(verdicts)
    return (v.count("✅") + v.count("△") * 0.5) / len(v) * 100 if v else 0.0


def run_eval(db, df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    answers_by_num = {}  # 후속 질문용: 번호 → (질문, 답변)

    for _, row in df.iterrows():
        question = str(row["English (EN)"])  # 챗봇은 영어 질문 기준
        expected = str(row["정답"])
        num = q_num(row["No"])

        # 후속 질문이면 앞 질문의 대화를 history로 넘김 (app.py에서 이어서 묻는 것과 동일)
        history = None
        prev = FOLLOW_UPS.get(num)
        if prev in answers_by_num:
            prev_q, prev_a = answers_by_num[prev]
            history = [
                {"role": "user", "content": prev_q},
                {"role": "assistant", "content": prev_a},
            ]

        try:
            answer, src = ask_bot(db, question, history)
            verdict, reason = judge(row["질문"], expected, answer)
        except Exception as e:
            answer, src, verdict, reason = f"(오류) {e}", "", "❌", "실행 중 오류"

        answers_by_num[num] = (question, answer)
        print(f"  [{row['No']}] {verdict} {reason}")

        rows.append({
            "No": row["No"],
            "질문 유형": row["질문 유형"],
            "질문": row["질문"],
            "English (EN)": question,
            "정답": expected,
            "판정": verdict,
            "챗봇 답변": answer,
            "출처": src,
            "판정 이유": reason,
            "이전 대화 사용": "Q" + str(prev) if history else "",
        })
    return pd.DataFrame(rows)


# ---------- 리포트 ----------
def write_report(path: Path, title: str, result: pd.DataFrame, scores):
    v = list(result["판정"])
    lines = [
        f"# {title}",
        "",
        f"- 점수(✅=1, △=0.5): **{sum(scores) / len(scores):.1f}점**"
        + (f"  (회차별: {', '.join(f'{s:.1f}' for s in scores)})" if len(scores) > 1 else ""),
        f"- ✅ {v.count('✅')} / △ {v.count('△')} / ❌ {v.count('❌')}  (총 {len(v)}건)",
        "",
        "## 유형별 점수",
        "",
        "| 질문 유형 | 점수 | ✅ | △ | ❌ |",
        "|---|---|---|---|---|",
    ]
    for t, g in result.groupby("질문 유형", sort=False):
        gv = list(g["판정"])
        lines.append(f"| {t} | {score(gv):.1f} | {gv.count('✅')} | {gv.count('△')} | {gv.count('❌')} |")

    wrong = result[result["판정"] != "✅"]
    lines += ["", f"## 틀린 문항 (△/❌) — {len(wrong)}건", ""]
    if wrong.empty:
        lines.append("없음")
    for _, r in wrong.iterrows():
        round_tag = f" ({r['회차']}회차)" if len(scores) > 1 else ""
        answer = str(r["챗봇 답변"]).replace("\n", " ")
        sources = str(r["출처"]).replace("Sources:", "").replace("\n", " ").strip() or "-"
        lines += [
            f"### {r['No']} {r['판정']}{round_tag} · {r['질문 유형']}",
            f"- 질문: {r['질문']}",
            f"- 정답: {r['정답']}",
            f"- 챗봇 답변: {answer}",
            f"- 출처: {sources}",
            f"- 판정 이유: {r['판정 이유']}",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------- 실행 ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default=str(DEFAULT_CSV), help="질문 리스트 CSV 경로")
    parser.add_argument("--repeat", type=int, default=1, help="반복 횟수 (평균 점수)")
    parser.add_argument("--label", default="", help="결과 폴더 이름에 붙일 라벨 (예: 개선후)")
    parser.add_argument("--chunk-size", type=int, default=rag.CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=rag.CHUNK_OVERLAP)
    args = parser.parse_args()

    df = load_questions(Path(args.csv))

    suffix = f"_{args.label}" if args.label else ""
    out_dir = EVAL_DIR / "results" / f"app_{datetime.now():%Y%m%d_%H%M}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)

    size, overlap = args.chunk_size, args.chunk_overlap
    print(f"청크 설정: size={size}, overlap={overlap} / TOP_K={rag.TOP_K}, MAX_DOCS={rag.MAX_DOCS}")
    print("벡터 DB 생성 중...")
    db = rag.build_vector_db(
        chunk_size=size,
        chunk_overlap=overlap,
        collection_name=f"eval_app_{size}_{overlap}",
        verbose=False,
    )

    rounds, scores = [], []
    for r in range(1, args.repeat + 1):
        print(f"\n[{r}회차]")
        res = run_eval(db, df)
        s = score(res["판정"])
        scores.append(s)
        res.insert(0, "회차", r)
        rounds.append(res)
        print(f"  → {r}회차 점수 {s:.1f}")

    result = pd.concat(rounds, ignore_index=True)
    result.to_csv(out_dir / "상세.csv", index=False, encoding="utf-8-sig")
    title = f"app.py 챗봇 평가 (size={size}, overlap={overlap}){' · ' + args.label if args.label else ''}"
    write_report(out_dir / "리포트.md", title, result, scores)

    v = list(result["판정"])
    print("\n" + "=" * 50)
    print("유형별 점수")
    print(result.groupby("질문 유형", sort=False)["판정"].apply(score).round(1).to_string())
    print(f"\n전체: ✅ {v.count('✅')} / △ {v.count('△')} / ❌ {v.count('❌')}")
    print(f"평균 점수: {sum(scores) / len(scores):.1f}점")
    wrong = sorted(result.loc[result["판정"] != "✅", "No"].unique())
    print(f"틀린 문항: {', '.join(wrong) or '없음'}")
    print(f"\n결과 폴더: {out_dir}")


if __name__ == "__main__":
    main()