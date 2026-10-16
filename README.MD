# 제주 여행 소개 챗봇

제주도 테마북 PDF 문서를 기반으로 질문에 답변하는 RAG(Retrieval-Augmented Generation) 챗봇입니다.


## 개발 환경

| 항목 | 버전 / 내용 |
| --- | --- |
| Python | **3.11.9** |
| LLM | OpenAI `gpt-4o-mini` |
| 임베딩 | OpenAI `text-embedding-3-small` |
| 벡터 DB | Chroma (`langchain-chroma`, 인메모리) |
| 프레임워크 | LangChain 0.3.x |

## 폴더 구조

```
jeju_trip_chatbot/
├── .github/
│   └── workflows/
│       └── branch-rule.yml        # PR 병합 브랜치 규칙 검사
├── data/                          # (git 제외) 로컬 데이터
│   └── pdfs/                      # ★ PDF 파일 배치 위치
│       ├── jjfood.pdf
│       ├── jjmountain.pdf
│       ├── jjnight.pdf
│       └── jjocean.pdf
├── docs/
│   └── experiments/
│       ├── rag_search_baseline.md # RAG 검색 실험 기록
│       └── sources.md             # 데이터 출처
├── rag/
│   ├── __init__.py
│   ├── pdf_processor.py           # PDF 로드·청킹·임베딩 → Chroma DB 생성
│   └── qa_chain.py                # 검색 결과 기반 질의응답 체인 (LCEL)
├── .env                           # (git 제외) OPENAI_API_KEY 설정
├── .gitignore
├── README.MD
├── requirements.txt
└── test_pdf.py                    # data/pdfs 의 PDF로 CLI 챗봇 실행
```

## PDF 파일 배치

PDF 파일은 반드시 아래 경로에 넣어야 합니다.

```
jeju_trip_chatbot/data/pdfs/
```

- `test_pdf.py`는 `data/pdfs/*.pdf`를 모두 읽어 처리합니다. 폴더가 없거나 PDF가 하나도 없으면 오류가 발생합니다.
- `data/` 폴더와 `*.pdf` 파일은 `.gitignore`에 의해 저장소에 올라가지 않으므로, 클론 후 직접 폴더를 만들고 PDF를 넣어주세요.

```powershell
mkdir data\pdfs
```

## 설치 및 실행

### 1. 가상환경 생성 (Python 3.11.9)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
```

> macOS / Linux: `python3.11 -m venv .venv && source .venv/bin/activate`

### 2. 의존성 설치

```powershell
pip install -r requirements.txt
```

### 3. 환경변수 설정

프로젝트 루트에 `.env` 파일을 만들고 OpenAI API 키를 입력합니다.

```env
OPENAI_API_KEY=sk-...
```

### 4. 실행

```powershell
python app.py
```

PDF 처리 후 `Question:` 프롬프트가 나타나면 질문을 입력합니다. 빈 줄 또는 `q`를 입력하면 종료합니다.

## 브랜치 규칙

`.github/workflows/branch-rule.yml`에서 PR 병합 출처를 검사합니다.

- `main` ← `develop` 브랜치만 병합 가능
- `develop` ← `feature/*` 브랜치만 병합 가능
