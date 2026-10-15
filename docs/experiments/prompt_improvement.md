# 프롬프트 개선 기록

대상: `test_pdf.py`의 `SYSTEM_PROMPT`(답변 생성)와 `to_korean_query()`(검색용 번역)

## v1. 답변 품질 규칙 보강 (적용 완료, 결과 측정 전)

아래 7개 항목을 모두 `test_pdf.py`에 반영했다. 항목별 개별 효과는 분리 측정하지 않았으므로, 우선 기존 프롬프트 대비 v1 전체를 비교한다.

| # | 문제 | 근거 | 개선안 |
| --- | --- | --- | --- |
| 1 | 음식 이름에 한글 병기가 안 됨 | 기존 답변의 `Dombegogi`, `Okdom Guk` 등에 한글 없음. 규칙이 "place names"로 한정됨 | 대상을 "Korean place names, food names, and other proper nouns"로 확대 |
| 2 | 부분적으로만 답할 수 있는 질문의 답변 전체가 버려짐 | 코드가 `NOT_FOUND in text`로 판단하므로, "영업시간은 문서에 없다"는 식으로 고정 문구를 섞으면 답변 전체가 삭제됨 | 고정 문구는 **전혀 답할 수 없을 때만** 사용하고, 일부 정보가 없으면 "The guide doesn't mention ..."처럼 다른 표현으로 쓰도록 지시 |
| 3 | 관련 낮은 청크(식당 목록 표 등)가 섞임 | p.24 식당 목록이 "유명 음식" 질문에 검색됨 | "Ignore excerpts that are not relevant to the question." 추가. 식당 이름·주소·연락처는 "어디서 먹을 수 있는지" 물을 때만 사용 |
| 4 | 답변 형식·길이 기준 없음 | 터미널에 `**bold**` 마크다운이 그대로 출력됨 | 출력 환경에 맞춰 지정 (CLI: plain text / Gradio: markdown 허용), 길이 예: "Keep it concise, under 150 words unless asked for detail" |
| 5 | 정보 시점 미고지 | 가격·영업시간·연락처는 PDF 발행 이후 바뀔 수 있음 | 가격·영업시간·연락처를 안내할 때 "may have changed; check before visiting" 한 줄 추가 |
| 6 | 번역 질의가 고유명사를 망칠 수 있음 | `Seongsan Ilchulbong`, `Dombegogi` 같은 로마자 표기를 번역 프롬프트가 한글 고유명사로 되돌린다는 보장이 없음 | 번역 프롬프트에 "Convert romanized Korean names back to Hangul (e.g. Seongsan Ilchulbong → 성산일출봉)" 추가 |
| 7 | 실험 재현성 | `temperature=0.2`라 같은 질문에도 답변이 달라질 수 있음 | 비교 실험 중에는 `temperature=0`으로 고정 |

**코드 변경 (2·7번)**

- `answer_in_english()`: `USED:` 줄을 먼저 떼어낸 뒤, 남은 답변 **전체가** 고정 문구와 일치할 때만 "답 없음"으로 처리 (기존: 고정 문구가 포함만 돼도 답변 전체 폐기)
- 답변 생성 `temperature` 0.2 → 0 (번역 질의는 원래 0)

## 비교 테스트 계획

같은 질문 세트를 기존 프롬프트 / v1에 동일 조건(`temperature=0`, 동일 청크 설정, similarity search `k=4`)으로 실행해 기록한다.

| 질문 | 확인 포인트 | 기존 결과 | v1 결과 |
| --- | --- | --- | --- |
| what is famous food in jeju? | 한글 병기(1), 무관 청크 무시(3) | | |
| Where can I eat black pork? | 식당 목록 활용(3), 정보 시점 안내(5) | | |
| What time does Dongmun Market open? | 부분 답변 처리(2) | | |
| How do I get to Seongsan Ilchulbong? | 번역 질의 고유명사(6) | | |
| Is there a casino in Jeju? | 문서에 없는 정보 → 고정 문구 | | |

## 주의 사항

- 프롬프트 변경은 검색 결과에 영향을 주지 않으므로(6번 제외), 검색 품질 문제(`rag_search_baseline.md`)와 분리해서 평가한다.
- 한 번에 한 항목씩 바꿔야 어떤 변경이 효과가 있었는지 구분할 수 있다.
