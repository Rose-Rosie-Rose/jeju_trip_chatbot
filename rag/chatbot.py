"""제주 여행 PDF RAG 챗봇 핵심 로직 (검색 → 답변 생성 → 출처 추출).

app.py(Gradio)와 eval 스크립트에서 불러 씁니다. (기존 test_pdf.py)
"""

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from openai import OpenAI


# ---------- 기본 설정 ----------
BASE_DIR = Path(__file__).resolve().parent.parent  # 프로젝트 루트

PDF_DIR = BASE_DIR / "data" / "pdfs"
PDF_PATHS = list(PDF_DIR.glob("*.pdf"))

MODEL = "gpt-4o-mini"
TOP_K = 7      # 검색어·검색 방식마다 가져올 청크 수
MAX_DOCS = 10  # 답변 생성에 넘길 최대 청크 수 (RRF 상위)
RRF_K = 60

# 청크 설정 (eval/Tune_chunks.py 결과 1위: size=800, overlap=150 → 72.5점)
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

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
- If the message is a greeting, thanks, small talk, or a question about
  who you are or what you can do, ignore the excerpts and reply briefly
  and warmly. Introduce yourself as a Jeju travel assistant that can help
  with Jeju food, oreums and mountains, night tours, and ocean activities,
  and invite the user to ask a question. Do not add a USED line.
- Use only the excerpts that are relevant to the question and ignore
  the rest. Use restaurant names, addresses, and phone numbers only
  when the user asks where to go or eat.
- Never make up facts, prices, opening hours, or locations.
- One excerpt often describes several places. Attribute each fact (views,
  address, hiking time, etc.) only to the place it is written under, and
  never mix details between places.
- Pages often have an info block after the descriptions, listing each place
  in order with its address, 탐방시간 (total hiking/visit time), 난이도
  (difficulty), and nearby spots. Match the block to the right place and use
  it for questions about time, difficulty, or location.
- For hiking or visit time, answer with the 탐방시간 value from the info
  block. A description like "10분 정도면 오를 수 있다" is only the time to
  the summit; mention it as extra detail, never as the hiking time.
- 탐방시간 is the total time for the whole visit, already including going
  up and coming back. For "how long to go and come back", give that value
  as it is; never double it.
- When an excerpt (including a table of contents) lists places under a
  heading that matches the question, such as 초보자를 위한 오름 (oreums for
  beginners), recommend places from that heading only. Do not add places
  that appear under a different heading on the same page.
- The excerpts may not use the user's exact words. Answer from what the
  descriptions clearly imply (e.g. a trail described as flat and short suits
  beginners) instead of saying the information is missing.
- Earlier messages are the conversation so far. Use them to understand
  what the user is referring to, but take facts only from the excerpts.
- If NONE of the excerpts answer the question, reply exactly:
  "I'm sorry, I couldn't find that information in the document."
  and nothing else.
- If only part of the question is answered, answer that part and say
  what is missing in your own words, e.g. "The guide doesn't mention
  its opening hours." Do not use the exact sentence above in this case.
- For Korean place names, food names, and other proper nouns, give the
  English romanization with the Korean in parentheses,
  e.g. Seongsan Ilchulbong (성산일출봉), Dombae-gogi (돔베고기).
- When you mention prices, opening hours, or phone numbers, add a short
  note that they may have changed and should be checked before visiting.
- Write plain text without Markdown (no **bold** or # headings).
  Use "- " for lists. Keep it concise, under 150 words unless the user
  asks for detail.
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
# 답변 생성 시 함께 넘길 최근 대화 수 (user/assistant 메시지 기준)
HISTORY_TURNS = 6

QUERY_PROMPT = """You turn a traveler's latest message about Jeju into search
queries for Korean travel guidebooks (food, oreums and mountains, night tours,
ocean activities).

Use the conversation so far to resolve references such as "there", "it", or
"the places you recommended".

Return JSON only:
{"question": "<latest message rewritten as a standalone question in English>",
 "smalltalk": <true only for greetings, thanks, or questions about the assistant itself>,
 "queries": ["<Korean search query>", ...]}

Rules for "queries":
- The first query is a faithful Korean translation of the standalone question.
  Do not add words that are not in the question (e.g. 한국).
- Convert romanized or misspelled Korean names to correct Hangul
  (e.g. Seongsan Ilchulbong → 성산일출봉, heukdwaeji → 흑돼지).
- Add at most 2 more short queries, only when the question asks about several
  things (one query per thing), describes something by its features, asks
  which street, alley, or area is known for something, or asks for
  recommendations.
  For features, use the descriptive words a Korean guidebook would likely use
  instead of a literal translation (e.g. "not spicy" → 순하고 담백한,
  "for a rainy day" → 실내, 따뜻한 국물). Keep them specific.
- Turn negative descriptions into the positive words a guidebook would use
  (e.g. "not hot", "cold soup" → 시원한 국물, 물회; "not spicy" → 순한, 담백한).
- For questions asking which street, alley, or area is famous for something,
  add a query combining it with 거리, 골목, or 먹거리 골목
  (e.g. "alley famous for dombe-gogi" → 돔베고기 먹거리 골목 거리).
- For recommendation questions, add a query in the guidebook's heading style
  (e.g. "for beginners" → 초보자를 위한 오름, "for photos" → 사진 찍기 좋은 오름).
"""


def _recent_history(history) -> list[dict]:
    """최근 대화만 OpenAI messages 형식으로 추린다."""
    return [
        {"role": m["role"], "content": str(m["content"])}
        for m in (history or [])[-HISTORY_TURNS:]
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]


def plan_queries(question: str, history=None) -> tuple[str, list[str]]:
    """질문(과 이전 대화)으로 독립 질문과 한국어 검색어 목록을 만든다.

    반환값: (독립 질문(영어), 한국어 검색어 리스트 — 잡담이면 빈 리스트)
    """
    res = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": QUERY_PROMPT},
            *_recent_history(history),
            {"role": "user", "content": question},
        ],
    )

    try:
        data = json.loads(res.choices[0].message.content)
        standalone = str(data.get("question") or question).strip()
        queries = [str(q).strip() for q in data.get("queries", []) if str(q).strip()]
        if data.get("smalltalk") is True:
            queries = []
        elif not queries:
            queries = [standalone]
    except (json.JSONDecodeError, AttributeError):
        standalone, queries = question, [question]

    return standalone, queries[:3]


def _bigrams(text: str) -> list[str]:
    """공백을 뺀 글자 2-gram. 한국어 조사(서우봉은/서우봉을)와 상관없이 단어가 일치한다."""
    t = re.sub(r"\s+", "", text.lower())
    return [t[i:i + 2] for i in range(len(t) - 1)]


class BM25:
    """청크 키워드 검색 (글자 2-gram BM25). 벡터 검색이 약한 고유명사 검색을 보완한다."""

    def __init__(self, docs, k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tfs = [Counter(_bigrams(d.page_content)) for d in docs]
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avg_len = sum(self.lens) / max(len(self.lens), 1)
        df = Counter(g for tf in self.tfs for g in tf)
        n = len(docs)
        self.idf = {g: math.log(1 + (n - c + 0.5) / (c + 0.5)) for g, c in df.items()}

    def search(self, query: str, k: int) -> list:
        grams = set(_bigrams(query))
        scores = []
        for i, tf in enumerate(self.tfs):
            norm = self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg_len)
            score = sum(
                self.idf[g] * tf[g] * (self.k1 + 1) / (tf[g] + norm)
                for g in grams if g in tf
            )
            if score > 0:
                scores.append((score, i))
        scores.sort(reverse=True)
        return [self.docs[i] for _, i in scores[:k]]


_bm25_cache: dict[int, BM25] = {}


def _bm25_for(db) -> BM25:
    """벡터 DB에 저장된 청크로 BM25 색인을 만든다 (DB마다 한 번)."""
    key = id(db)
    if key not in _bm25_cache:
        data = db.get(include=["documents", "metadatas"])
        docs = [
            Document(page_content=text, metadata=meta or {})
            for text, meta in zip(data["documents"], data["metadatas"])
        ]
        _bm25_cache[key] = BM25(docs)
    return _bm25_cache[key]


def _doc_key(doc):
    return (
        doc.metadata.get("source_file"),
        doc.metadata.get("page"),
        doc.page_content,
    )


def search(db, queries) -> list:
    """검색어마다 벡터 검색 + 키워드(BM25) 검색을 하고 RRF로 합쳐 상위 MAX_DOCS개를 고른다.

    한국어가 없는 검색어(영어 질문)는 벡터 검색만 한다.
    """
    bm25 = _bm25_for(db)
    ranked_lists = []

    for query in queries:
        ranked_lists.append(db.similarity_search(query, k=TOP_K))
        if re.search(r"[가-힣]", query):
            ranked_lists.append(bm25.search(query, k=TOP_K))

    # Reciprocal Rank Fusion: 여러 검색 결과에서 고르게 상위에 오른 청크를 우선
    scores, docs_by_key = {}, {}
    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked):
            key = _doc_key(doc)
            docs_by_key.setdefault(key, doc)
            scores[key] = scores.get(key, 0) + 1 / (RRF_K + rank + 1)

    best = sorted(scores, key=scores.get, reverse=True)[:MAX_DOCS]
    return [docs_by_key[key] for key in best]


def retrieve(db, question: str, history=None):
    """원문 질문과 한국어 검색어들로 검색하고 중복을 제거한다."""
    standalone, queries = plan_queries(question, history)
    print(f"(검색용 질의: {standalone} / {queries})")
    return search(db, [standalone, *queries])


def ask(db, question: str, history=None):
    """질문 하나를 처리한다: 검색어 생성 → 검색 → 답변 생성.

    history: 이번 질문 이전의 대화 (OpenAI messages 형식, 없으면 None)
    반환값: (답변 텍스트, 실제로 사용한 문서 리스트)
    """
    standalone, queries = plan_queries(question, history)
    print(f"(검색용 질의: {standalone} / {queries})")

    # 인사·잡담이면 검색 없이 답변 (SYSTEM_PROMPT 의 인사 규칙)
    docs = search(db, [standalone, *queries]) if queries else []

    return answer_in_english(question, docs, history)


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


def answer_in_english(question: str, docs, history=None):
    """검색된 PDF 내용을 근거로 영어 답변을 생성한다.

    반환값: (답변 텍스트, 실제로 사용한 문서 리스트)
    """
    context = "\n\n".join(
        f"[#{i} | {pdf_title(doc)} | p.{page_no(doc)}]\n"
        f"{doc.page_content}"
        for i, doc in enumerate(docs, start=1)
    ) or "(no excerpts)"

    res = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            *_recent_history(history),
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

    # "USED: 1, 3" 줄을 찾아 떼어내고, 실제 사용한 문서만 추림
    used_docs = []
    match = re.search(r"^\s*USED\s*:\s*(.*)$", text, re.IGNORECASE | re.MULTILINE)
    if match:
        for num in re.findall(r"\d+", match.group(1)):
            idx = int(num)
            if 1 <= idx <= len(docs) and docs[idx - 1] not in used_docs:
                used_docs.append(docs[idx - 1])
        text = (text[:match.start()] + text[match.end():]).strip()

    # 답변 전체가 고정 문구일 때만 "답 없음"으로 처리 (부분 답변은 유지)
    if text.strip("\"' ") == NOT_FOUND:
        return NOT_FOUND, []

    # 답을 해 놓고 고정 문구를 덧붙이는 경우가 있어 그 문장만 제거
    text = text.replace(NOT_FOUND, "").strip()

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