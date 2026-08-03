# Architecture.md — 시스템 구조

## 전체 흐름 (한눈에)

```
내 PC가 꺼져있어도 자동으로 돌아가는 구조

[GitHub Actions]  ← GitHub 서버가 알아서 스케줄 실행
        ↓
[Python 스크리너]  ← 주식 데이터 수집 + 필터링
        ↓
[Firebase Firestore]  ← 결과를 DB에 저장 (구글 클라우드)
        ↓
[Next.js 대시보드]  ← 저장된 결과를 웹에서 조회
```

---

## 각 부분이 하는 일

### 1. GitHub Actions — "자동 실행기"

- GitHub 서버 안에 있는 가상 컴퓨터(Ubuntu Linux)를 무료로 빌려 쓰는 개념
- `.github/workflows/screener.yml` 파일에 스케줄을 적어두면 GitHub이 알아서 실행
- **내 PC가 꺼져있어도 돌아가는 이유**: 실행 주체가 GitHub 서버이기 때문
- 실행 시각: 08:30 KST (장 시작 전 / 미장 마감 후), 18:00 KST (KRX 일봉 확정 후)
  - 18:00으로 잡은 이유: 15:30 마감 직후에는 일봉이 확정되지 않은 경우가 있음

```
screener.yml이 하는 일 (순서대로):
  1. Ubuntu 가상머신 켜기
  2. 이 레포 코드 다운로드 (git checkout)
  3. Python 3.12 설치
  4. requirements.txt의 라이브러리 설치 (FinanceDataReader, pandas, firebase-admin)
  5. python main.py 실행 (한국/미국/코인 3개 시장 순차)
  6. 완료 후 가상머신 종료 (비용 없음)
```

### 2. Python 스크리너 — "주식 분석기"

- `market_config.py`: 시장별 설정 (유니버스, 벤치마크, 임계값, 유동성 기준, 거래비용)
- `screener.py`: FinanceDataReader로 시세 수집 → 지표 계산 → 8개 패턴 점수화
  - `get_universe()`: 종목 리스트 + 우선주/스팩/시총 필터
  - `calc_signals_from_df()`: 지표 계산 (스크리너·백테스트 공용)
  - `score_pattern()`: 필수조건 게이트 + 가중합 점수 (스크리너·백테스트 공용)
- `backtest.py`: 유니버스 표본을 과거 시점부터 스캔해 신호 성과 측정
- `dart_fetcher.py`: DART `finstate_all`로 최근 8분기 재무 수집 → 파생지표 계산 (KR만)
  - `account_id`(IFRS 코드)로 매칭, 손익은 `IS`/`CIS` 둘 다 탐색, 연결(CFS)→별도(OFS) 폴백
  - `derive()`: TTM 매출/이익, ROE/ROA/마진/부채비율, 재고 QoQ/YoY/회전율
  - `add_valuation()`: `Marcap` ÷ TTM 재무값 = PER/PBR/PSR (주가는 DART에 없어 시총과 결합)
- `firebase_upload.py`: 결과를 Firestore에 저장 (`save_fundamentals()`로 재무 히스토리 별도 저장)
- `main.py`: 위 모듈들을 순서대로 호출하는 진입점

### 3. Firebase Firestore — "데이터베이스"

- Google이 운영하는 클라우드 DB (NoSQL)
- Python(GitHub Actions)이 데이터를 **쓰고**, Next.js 대시보드가 데이터를 **읽음**
- **인증 방식**: GitHub Secrets에 저장된 서비스 계정 키로 인증
  - `FIREBASE_PROJECT_ID`, `FIREBASE_PRIVATE_KEY`, `FIREBASE_CLIENT_EMAIL`
  - 코드에 직접 적지 않고 환경변수로 주입 → 키 노출 방지

```
저장 구조 (Firestore):
  컬렉션: screener_results
    문서 ID: "2026-08-02_auto"
      - run_at: 실행 시각
      - market_date: 기준 날짜
      - run_type: "auto" / "open" / "close"
      - kr_common_trend: [ { ticker, name, price, rsi, vol_ratio, avg_value_20,
                             momentum_3m, rs, pos_52w, atr_14, stop_swing, score }, ... ]
      - kr_common_trend_count: 종목 수
      - us_*, crypto_* : 동일 구조 (마켓 prefix로 분리)
      - (KR 종목 row에는 marcap, per, pbr, psr, roe 등 파생지표 포함)
      - backtest: { kr: { common_trend: {...}, ... }, us: {...}, crypto: {...} }

  컬렉션: fundamentals          ← 분기 재무 히스토리 (재고 사이클/차트용, 종목별)
    문서 ID: "005930" (종목코드)
      - corp_code: DART 고유번호
      - updated_at: 갱신 시각
      - quarters: { "2026Q1": { rev, op, net, cogs, inventory, assets,
                                liab, equity, receivables, cash, eps, ... }, ... }
      ※ screener_results 문서 1MB 한도를 피하려 재무 원본은 여기 분리 저장
      ※ 대시보드가 종목 모달에서 지연 로딩 → Firestore 규칙에 읽기 허용 필요
```

**주의 — DART 데이터 성격 차이 (실측 확인)**
- 손익계산서(IS/CIS) `thstrm_amount` = **당기 3개월 단독값** → 차감 불필요
- 현금흐름표(CF) `thstrm_amount` = **기초부터 누적값** → 분기 단독값은 차감 필요
- 재무상태표(BS) = 시점값
- 업종 구분은 FDR `Dept`가 비어 있어 DART `induty_code`(KSIC) 사용

### 4. Next.js 대시보드 — "웹 화면"

- Vercel에 배포 → 별도 서버 없이 URL로 접속
- Firebase에서 최신 스크리닝 결과를 불러와서 테이블/차트로 표시
- `/` 스크리닝 화면, `/backtest` 백테스트 통계 화면 (둘 다 🇰🇷🇺🇸₿ 마켓 선택)
- 로컬 실행 시 `dashboard/.env.local`에 `NEXT_PUBLIC_FIREBASE_API_KEY`,
  `NEXT_PUBLIC_FIREBASE_PROJECT_ID` 필요 (gitignore 대상이라 머신마다 개별 생성)
- PC + 모바일 둘 다 대응

---

## GitHub Secrets가 필요한 이유

GitHub Actions가 Firebase에 데이터를 쓰려면 "나 허가된 사용자야"라는 증명이 필요함.
이 증명서(서비스 계정 키)를 코드에 직접 넣으면 GitHub에 공개되므로,
GitHub Secrets에 따로 저장해두고 실행 시점에만 환경변수로 주입하는 방식을 사용.

```
GitHub Secrets (암호화 저장)
        ↓ 실행 시 주입
screener.yml → python main.py
                    ↓
              firebase_upload.py
              os.environ["FIREBASE_PROJECT_ID"] 로 읽음
                    ↓
              Firebase 인증 성공 → 데이터 저장
```

---

## 스크리닝 기준

### 3단계 필터

```
1) 유니버스 필터  — get_universe()
   시총 1000억↑ · 보통주만(코드 끝자리 0) · 스팩/리츠 제외
   KOSPI+KOSDAQ 2763종목 → 약 1240종목

2) 거래가능 필터  — _base_ok()
   20일 평균 거래대금 10억↑ · 거래정지/가격고정 종목 제외
   약 1240종목 → 약 700종목

3) 패턴 점수      — score_pattern()
   필수조건 게이트 통과 → 가중합 60점 이상
```

### 필수조건 게이트를 둔 이유

가중합만 쓰면 패턴의 정의와 무관한 조건들로도 임계값을 넘김.
예: Stage 2는 `price > MA120`(25점) + `MA120 우상향`(25점) = 50점으로
기존 임계값 40을 통과 → 상승장에서 수백 종목이 걸려 필터 역할을 못 함.

각 패턴이 성립하려면 반드시 참이어야 하는 조건을 `REQUIRED_FNS`로 분리하고,
미충족 시 점수를 0으로 만듦. 결과적으로 패턴당 4개 내외의 실질 조건을 요구.

| 패턴 | 필수조건 |
|------|---------|
| Stage 2 | MA120 위 + MA120 우상향 + 부분정배열 + RS > 0 |
| VCP | 볼린저 수축 + 거래량 수축 + 부분정배열 |
| Wyckoff | OBV 상승 + 볼린저 수축 + MA20 위 |
| CAN SLIM | 52주 위치 ≥ 0.75 + RS > 0 + 거래량 조건 |
| Darvas | 52주 위치 ≥ 0.80 + 거래량 급증 |

### 최종 출력 (★가 본체)

| 키 | 조건 |
|----|------|
| `common_trend` | Stage2 / CAN SLIM / Darvas 중 2개 이상 |
| `common_accum` | Wyckoff + VCP 둘 다 |
| `common_all` | P1 / P2 / P3 중 2개 이상 |

---

## 백테스트 방법론

`backtest.py`는 **스크리너 결과와 무관한 유니버스 표본**을 과거 시점부터 스캔함.

```
유니버스(약 1240종목) → 무작위 표본 150종목 (seed 고정)
        ↓
각 종목의 1100일 히스토리를 10거래일 간격으로 슬라이딩 스캔
        ↓
스캔 시점 데이터만으로 신호 판정 (hist.iloc[:i+1])
        ↓
20일/60일 보유 · ATR 손절 도달 시 조기 청산
        ↓
수수료·세금·슬리피지 차감한 순수익률로 통계
```

**설계 의도**

| 항목 | 처리 |
|------|------|
| 선택 편향 | 오늘 선정된 종목이 아닌 유니버스 표본을 스캔 (선정 종목만 되짚으면 "이미 오른 종목의 과거"를 재게 됨) |
| 미래 참조 | 신호 계산 시 `hist.iloc[:i+1]`로 창을 잘라 미래 봉 차단 |
| 벤치마크 | 스캔 시점의 벤치마크 3개월 수익률을 전달해 RS를 라이브와 동일하게 계산 |
| 거래비용 | 수수료·거래세·슬리피지를 시장별로 차감 (KR 왕복 약 0.41%) |
| 손절 | 스크리너가 화면에 표시하는 ATR 손절선을 그대로 적용, 갭하락 시 시가 체결 |
| 중복 신호 | 스캔 간격 10거래일로 20일 보유와의 겹침 축소 |

**남아있는 한계** — 유니버스가 현재 상장 종목 기준이라 상장폐지 종목이 빠져 있음(생존 편향).
신호가 시간적으로 겹칠 수 있어 실제 독립 표본 수는 표시된 신호 수보다 적음.

---

## 파일 구조

```
QuantTrading/
├── .github/
│   └── workflows/
│       └── screener.yml      # GitHub Actions 스케줄 정의
├── screener/
│   ├── main.py               # 진입점 (3개 시장 순차 실행)
│   ├── market_config.py      # 시장별 설정 (유니버스/임계값/거래비용)
│   ├── screener.py           # 시세 수집 + 지표 + 패턴 점수화
│   ├── backtest.py           # 유니버스 표본 히스토리 스캔
│   ├── dart_fetcher.py       # DART finstate_all 8분기 재무 + 파생지표/밸류에이션 (KR)
│   ├── firebase_upload.py    # Firestore 업로드
│   └── requirements.txt      # Python 의존성
├── dashboard/
│   ├── app/page.tsx          # 종목 스크리닝 화면
│   ├── app/backtest/page.tsx # 백테스트 통계 화면
│   ├── components/           # StockTable, ScoreBar, 상세 모달
│   └── lib/                  # firebase, fetcher, types
├── CLAUDE.md
├── 작업명세서.md
└── Architecture.md
```

---

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-05-11 | 초안 작성 |
| 2026-05-11 | GitHub Actions + Firebase 연동 구조 상세 설명 추가 |
| 2026-08-02 | 스크리닝 3단계 필터 · 필수조건 게이트 · 백테스트 방법론 섹션 추가, 파일 구조 현행화 |
