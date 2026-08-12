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
- 화면 4개 (모두 🇰🇷🇺🇸₿ 마켓 선택)
  - `/` 스크리닝 · `/backtest` 신호 단위 통계
  - `/track` **성적표** — N일 전 리스트가 지금 몇 %인지. 날짜·패턴 선택 + 종목 검색 (자동 갱신)
  - `/replay` 3년치 통계 — 87스캔일 전체 평균 (수동 갱신)
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

### 원전 재구현 (2026-08-12)

이름만 빌려온 상태였던 5개 기법을 원전 규칙에 맞췄다. 재구현 전후 차이:

| 기법 | 이전 | 현재 |
|------|------|------|
| CAN SLIM | L = 코스피 대비 +5% (절대 초과수익) | L = **IBD RS Rating 백분위 70↑** + M(시장 방향) 추가 |
| VCP | 볼린저 수축 (단일 시점 변동성) | **Trend Template 8개** + 연속 수축이 점점 얕아지는지 |
| Stage 2 | MA120 위 + 우상향 (상승 '상태') | **30주선(150일) + 베이스 저항 돌파** (상승 '전환') |
| Darvas | 52주 고점 근처 + 거래량 | **박스 천장/바닥 실제 탐지** + 돌파. 손절 = 박스 바닥 |
| Wyckoff | OBV 신고점 | **거래범위 + Spring/SOS + 매도 소진** (OBV는 Wyckoff 사후 지표) |

**효과 측정** — Stage 2 동점률 96% → 5%. 이전에는 점수의 81%가 만점이라 상위 30이 통째로
동점이었고, 순위가 사실상 임의였다. 신호 발생률도 패턴당 1.4~5.2%로 원전답게 희소해졌다.

**패턴 간 중복** (자카드) — 원전 기법끼리 최대 30.5%(canslim∩darvas, 둘 다 신고가+거래량 요구).
VCP와 Wyckoff는 요구 국면이 반대(상승추세 vs 횡보)라 거의 배타적 — 예전 `common_accum`의
순환 논리(둘 다 `bb_squeeze` 요구)가 사라졌다.

**RS Rating 2단계 구조** — 백분위라 종목 하나만 봐서는 못 구한다.
```
1) calc_signals_from_df  → rs_strength (종목별, IBD 가중 ROC)
2) attach_rs_rating      → 거래가능 유니버스 내 백분위 1~99
3) score_pattern         → s["rs_rating"] 사용
```
라이브(`all_df`)와 재현(`groupby("date")`)이 **같은 모집단(거래 가능 종목)** 을 쓴다.
어긋나면 `verify`가 못 잡는다 — 그건 종목 하나를 자기 자신과 비교하는 검사라서.

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

## 실전 성적표 (`tracker.py`)

**"N일 전 이 패턴에 떴던 종목, 지금 몇 %?"** 에 답하는 경로. 일일 스크리너 안에서
자동으로 계산되며 수동 실행이 필요 없다.

```
매 실행마다:
  screener.run()이 유니버스 전체 시세를 이미 받아둠 → {ticker: 현재가}
        ↓
  screener_results에서 최근 75일치 과거 문서를 읽음 (실제로 화면에 떴던 목록)
        ↓
  그때 표시됐던 price vs 오늘 price 비교
        ↓
  scorecard/{market}_{date} 로 저장 → /track 화면
```

**replay.py와 나눠 쓰는 이유** — 묻는 질문이 다르다.

| | tracker.py | replay.py |
|---|---|---|
| 데이터 | 실제로 화면에 떴던 기록 | 과거를 재구성 |
| 기간 | 운영 시작 이후 (2026-05-11~) | 3년 |
| 갱신 | **자동, 하루 2회** | 수동 (몇 시간 소요) |
| 편향 | 없음 (사실 그대로) | 재구성 가정에 의존 |
| 용도 | "지금 얼마" — 투자 판단 | "이 패턴이 통하나" — 통계 |

성적표는 추가 조회가 없다. 과거 목록은 이미 Firestore에 있고 현재가는 스크리닝 과정에서
받은 것을 재사용한다. 과거 문서에서 `backtest` 블록은 용량 대부분을 차지하므로
`select()`로 필요한 필드만 읽는다.

**주의** — 표시 가격은 신호일 종가다. 실제 체결은 다음날 시가라 조금 다르고, 수수료·세금이
반영되지 않은 단순 등락률이다. 오늘 유니버스에서 사라진 종목(폐지·거래정지·유동성 미달)은
`gone`으로 표시하고 평균에서 제외한다.

---

## 과거 재현 (`replay.py`)

`backtest.py`가 "신호 뜬 종목 전부"를 사는 가정인 반면, 재현은 **화면에 뜨는 상위 N종목
리스트를 통째로 샀을 때**를 측정한다. 실제 사용 행동과 일치하는 쪽은 후자다.

```
1단계 build  (느림, 1회)
  상장폐지 포함 유니버스 → 종목별 OHLCV 캐시(parquet)
        ↓
  벤치마크 거래일을 기준 달력으로 삼아 N봉 간격 스캔
        ↓
  시점별 신호 + 5/20/60일 미래수익률 → panel_{market}.parquet

2단계 eval / publish  (빠름, 반복)
  패널 로드 → 8패턴 + 3공통 스코어링 → 날짜별 상위 N 선정
        ↓
  동일가중 수익률을 유니버스 평균·지수와 비교
```

**backtest.py와 다른 점**

| 항목 | backtest.py | replay.py |
|------|-------------|-----------|
| 평가 단위 | 신호 발생 종목 전부 | 스코어 상위 N종목 리스트 |
| 대상 패턴 | 공통 3개 | 8패턴 + 공통 3개 |
| 유니버스 | 현재 상장 150종목 표본 | 폐지 포함 전 종목 (KR 약 2,650) |
| 진입 시점 | 신호일 종가 | **신호 다음날 시가** |
| 기준선 | 없음 (절대수익) | 유니버스 평균 + 지수 |
| 재실행 | 매번 전체 스캔 | 패널 1회 적재 후 조건만 교체 |

**측정 설계**

| 항목 | 처리 |
|------|------|
| 생존 편향 | `KRX-DELISTING`으로 폐지 종목까지 유니버스에 포함. 보유 중 폐지되면 마지막 체결가로 청산(행을 버리면 편향이 되돌아옴) |
| 시총 필터 | 미적용 — 과거 시총을 알 수 없어 오늘 시총으로 거르면 미래 정보가 샘. 유동성은 `avg_value_20`로 시점별 판정 |
| 진입 편향 | 신호는 종가 확정 후에야 알 수 있으므로 다음날 시가 진입. 당일 종가로 사면 거래량 급등일의 갭상승을 공짜로 먹음 |
| 우측 끝 | 아직 미래가 없는 최근 스캔일은 해당 보유기간을 기록하지 않음 (60일 보유를 3일로 재는 것 방지) |
| 가중 방식 | 지수는 시총가중이라 대형주 장세에서 동일가중 포트폴리오가 구조적으로 뒤짐. **유니버스 동일가중 평균**을 기준선으로 둬 종목 선정력만 분리 |
| 동점 처리 | 고정 시드 난수로 타이브레이크. 행 순서로 두면 적재 순서(≈종목코드)가 순위가 되어 없는 선정력이 생김 |
| 거래정지 | FDR은 정지일 시/고/저를 0으로 준다. 그대로 두면 저가 0이 손절 도달로 잡혀 0원 청산(-100%)이 되므로 `sanitize_ohlc`가 종가로 채움 |
| 라이브 일치 | `verify`가 조회 봉 수(300 vs 전체)를 달리해 같은 신호가 나오는지 확인. 시작일만 달리하면 내부에서 같은 300봉으로 수렴해 항상 통과함 |

**Firestore 저장 구조**

```
scorecard/{market}_index         # 성적표 진입일 목록 (자동, 하루 2회)
scorecard/{market}_{date}        # 그날 리스트의 현재 손익
replay_results/{market}          # 집계 그리드 (패턴 × 보유일 × 상위N = 198조합)
replay_picks/{market}_index      # 선택 가능한 날짜 목록 + 거래일 경과
replay_picks/{market}_{date}     # 그날의 패턴별 종목 내역 (문서당 약 45KB)
```

날짜별로 문서를 쪼갠 이유 — 전 기간 종목 내역을 한 문서에 담으면 Firestore 1MB 한도를 넘는다.
화면은 사용자가 고른 날짜 하나만 읽는다.

**신호의 창 길이 의존성 제거** — OBV는 `cumsum`이라 절대값이 조회 구간 시작점에 따라 달라진다.
신고점 판정을 `최고값 × 0.98`로 하면 기준선이 같이 움직여 라이브와 재현이 다른 값을 냈다
(표본 8종목 중 1종목에서 플래그가 뒤집힘). 60일 변동폭 대비 상대 위치로 바꾸고,
`lookback_bars`로 두 경로의 조회 봉 수를 고정했다.

**실행**

```bash
python replay.py verify  --market kr              # 라이브/재현 동일성
python replay.py build   --market kr --days 1100  # 패널 적재
python replay.py eval    --market kr --hold 20 --top 30
python replay.py picks   --market kr --pattern common_trend --date 2026-07-13 --top 10
python replay.py picks   --market kr --pattern p3 --date 2026-06-01 --hold 20
python replay.py publish --market kr              # 집계 그리드 + 종목 내역 → Firebase
```

**두 가지 청산 가정** — 묻는 질문이 다르므로 둘 다 제공한다.

| | `--hold now` (기본) | `--hold 5/20/60` |
|---|---|---|
| 청산 | 안 팔고 현재가 | N거래일 뒤 매도 |
| 손절 | 미적용 (터치 여부만 표시) | ATR 손절 도달 시 청산 |
| 보유일 | 날짜마다 다름 | 고정 |
| 쓰임 | **"그날 샀으면 지금 얼마"** — 실제 손익 확인 | 패턴 간 공정 비교 (보유일이 같아야 성립) |

`eval`은 집계(패턴별 평균), `picks`는 특정 날짜의 **종목별 내역**을 낸다.

일일 스크리너와 분리된 `replay.yml`(수동 실행)로 돌린다 — 유니버스 전체를 과거 시점마다
재스캔하므로 90분 예산 안에 들어가지 않는다.

---

## 파일 구조

```
QuantTrading/
├── .github/
│   └── workflows/
│       ├── screener.yml      # GitHub Actions 스케줄 정의 (하루 2회)
│       └── replay.yml        # 과거 재현 (수동 실행, 최대 300분)
├── screener/
│   ├── main.py               # 진입점 (3개 시장 순차 실행)
│   ├── market_config.py      # 시장별 설정 (유니버스/임계값/거래비용/조회봉수)
│   ├── screener.py           # 시세 수집 + 지표 + 패턴 점수화 + RS Rating
│   ├── patterns.py           # 차트 구조 탐지 (박스·연속수축·거래범위·Wyckoff)
│   ├── backtest.py           # 유니버스 표본 히스토리 스캔 (신호 단위)
│   ├── tracker.py            # 실전 성적표 — 과거 실제 기록 vs 현재가 (자동)
│   ├── replay.py             # 상위 N종목 리스트 재현 (리스트 단위, 수동)
│   ├── dart_fetcher.py       # DART finstate_all 8분기 재무 + 파생지표/밸류에이션 (KR)
│   ├── firebase_upload.py    # Firestore 업로드
│   ├── .cache/               # OHLCV + 신호 패널 (gitignore)
│   └── requirements.txt      # Python 의존성
├── dashboard/
│   ├── app/page.tsx          # 종목 스크리닝 화면
│   ├── app/backtest/page.tsx # 백테스트 통계 화면
│   ├── app/track/page.tsx    # 성적표 — N일 전 리스트가 지금 몇 %인지
│   ├── app/replay/page.tsx   # 3년치 통계 (보유일·상위N 선택)
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
| 2026-08-12 | 5개 원전 기법 재구현 — RS Rating(IBD 백분위)·Trend Template·박스/수축/거래범위 실제 탐지. RSI·ATR을 Wilder 평활로 정정 |
| 2026-08-12 | 실전 성적표(`tracker.py`) 추가 — 일일 스크리너에서 자동 계산. 업로드 순서를 스크리닝 먼저로 변경 |
| 2026-08-12 | 과거 재현(`replay.py`) 섹션 추가 — 리스트 단위 측정, 생존편향 보정, 유니버스 기준선. OBV 창 의존성 수정 및 `lookback_bars` 도입 반영 |
