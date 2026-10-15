"""
청크 설정(chunk_size, chunk_overlap) 여러 개를 평가 CSV로 채점하고,
설정마다 "점수 + 어디서 틀렸는지"를 각각 파일로 저장한다.

사용법 (프로젝트 루트에서):
    python eval/tune_chunks.py                 # 기본 질문 CSV, 설정마다 1회
    python eval/tune_chunks.py --repeat 3      # 설정마다 3회 돌려 평균

결과 (실행할 때마다 새 폴더, 이전 결과는 덮어쓰지 않음):
    eval/results/chunk_YYYYMMDD_HHMM/
        size300_overlap50_리포트.md     ← 점수, 유형별 점수, 틀린 문항(△/❌) 목록
        size300_overlap50_상세.csv      ← 전체 문항 답변·출처·판정·이유
        size500_overlap100_리포트.md
        size500_overlap100_상세.csv
        ...
        00_요약.csv                     ← 설정별 점수 비교 (점수 높은 순)
        00_문항별_비교.csv              ← 문항 × 설정 판정표 (어느 설정에서 틀렸는지 한눈에)
"""

import argparse
import contextlib
import io
import sys
from datetime import datetime
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVAL_DIR))  # eval_qa import용

import pandas as pd

from eval_qa import DEFAULT_CSV, build_db, load_questions, run_eval, score

# 실험할 설정: (chunk_size, chunk_overlap)
# overlap은 보통 size의 10~20% 정도로 잡는다.
CONFIGS = [
    (300, 50),
    (500, 100),   # 현재 기본값
    (800, 150),
    (1000, 200),
    (1500, 300),
]


def config_name(size, overlap) -> str:
    return f"size{size}_overlap{overlap}"


def write_report(path: Path, size, overlap, n_chunks, result: pd.DataFrame, scores):
    """설정 하나의 점수와 틀린 문항을 마크다운 리포트로 저장한다."""
    v = list(result["판정"])
    lines = [
        f"# 청크 설정: size={size}, overlap={overlap}",
        "",
        f"- 청크 수: {n_chunks}",
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
        lines.append(
            f"| {t} | {score(gv):.1f} | {gv.count('✅')} | {gv.count('△')} | {gv.count('❌')} |"
        )

    wrong = result[result["판정"] != "✅"]
    lines += ["", f"## 틀린 문항 (△/❌) — {len(wrong)}건", ""]
    if wrong.empty:
        lines.append("없음")
    for _, r in wrong.iterrows():
        round_tag = f" ({r['회차']}회차)" if "회차" in r and len(scores) > 1 else ""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default=str(DEFAULT_CSV), help="질문 리스트 CSV 경로")
    parser.add_argument(
        "--repeat", type=int, default=1,
        help="설정마다 반복 횟수 (답변이 매번 조금씩 달라서 2~3회 평균을 내면 더 믿을 만함)",
    )
    args = parser.parse_args()

    df = load_questions(Path(args.csv))
    df["No"] = df["No"].astype(str)  # 번호가 1, 2, 3 숫자여도 문자열로 통일

    out_dir = EVAL_DIR / "results" / f"chunk_{datetime.now():%Y%m%d_%H%M}"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"결과 폴더: {out_dir}")

    summary_rows = []
    compare = df[["No", "질문 유형", "질문"]].copy()

    for size, overlap in CONFIGS:
        name = config_name(size, overlap)
        print("\n" + "=" * 50)
        print(f"청크 설정: size={size}, overlap={overlap}")
        print("=" * 50)

        db = build_db(chunk_size=size, chunk_overlap=overlap)
        n_chunks = db._collection.count()

        rounds, scores = [], []
        for r in range(1, args.repeat + 1):
            # retrieve()가 찍는 "(검색용 한국어 질의: ...)" 출력은 숨김
            with contextlib.redirect_stdout(io.StringIO()):
                res = run_eval(db, df, verbose=False)
            s = score(res["판정"])
            scores.append(s)
            res.insert(0, "회차", r)
            rounds.append(res)
            print(f"  [{r}회차] 점수 {s:.1f}")

        result = pd.concat(rounds, ignore_index=True)

        # 설정별 파일 2개: 상세 CSV + 리포트(점수·틀린 문항)
        result.to_csv(out_dir / f"{name}_상세.csv", index=False, encoding="utf-8-sig")
        write_report(out_dir / f"{name}_리포트.md", size, overlap, n_chunks, result, scores)
        print(f"  저장: {name}_리포트.md, {name}_상세.csv")

        # 문항별 비교표: 회차가 여러 번이면 "✅✅△"처럼 이어 붙임
        verdicts = result.groupby("No", sort=False)["판정"].apply("".join)
        compare[name] = compare["No"].map(verdicts)

        v = list(result["판정"])
        row = {
            "설정": name,
            "chunk_size": size,
            "chunk_overlap": overlap,
            "청크 수": n_chunks,
            "평균 점수": round(sum(scores) / len(scores), 1),
            "✅": v.count("✅"),
            "△": v.count("△"),
            "❌": v.count("❌"),
            "틀린 문항": ", ".join(sorted(result.loc[result["판정"] != "✅", "No"].unique())),
        }
        for t, g in result.groupby("질문 유형", sort=False):
            row[f"{t} 점수"] = round(score(g["판정"]), 1)
        summary_rows.append(row)

        # 중간에 멈춰도 여기까지 결과는 남도록 매번 저장
        pd.DataFrame(summary_rows).to_csv(out_dir / "00_요약.csv", index=False, encoding="utf-8-sig")
        compare.to_csv(out_dir / "00_문항별_비교.csv", index=False, encoding="utf-8-sig")

    summary = pd.DataFrame(summary_rows).sort_values("평균 점수", ascending=False)
    summary.to_csv(out_dir / "00_요약.csv", index=False, encoding="utf-8-sig")

    print("\n" + "=" * 50)
    print("설정별 결과 (점수 높은 순)")
    print("=" * 50)
    print(summary[["설정", "청크 수", "평균 점수", "✅", "△", "❌", "틀린 문항"]].to_string(index=False))

    best = summary.iloc[0]
    print(
        f"\n최적 설정: chunk_size={int(best['chunk_size'])}, "
        f"chunk_overlap={int(best['chunk_overlap'])}  (평균 {best['평균 점수']}점)"
    )
    print("→ test_pdf.py의 CHUNK_SIZE / CHUNK_OVERLAP 에 넣으세요.")
    print(f"\n결과 폴더: {out_dir}")


if __name__ == "__main__":
    main()