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
- 실행 시각: 08:30 KST (장 시작 전), 16:00 KST (장 마감 후)

```
screener.yml이 하는 일 (순서대로):
  1. Ubuntu 가상머신 켜기
  2. 이 레포 코드 다운로드 (git checkout)
  3. Python 3.12 설치
  4. requirements.txt의 라이브러리 설치 (pykrx, pandas, firebase-admin)
  5. python main.py 실행
  6. 완료 후 가상머신 종료 (비용 없음)
```

### 2. Python 스크리너 — "주식 분석기"

- `screener.py`: pykrx 라이브러리로 한국거래소(KRX) 데이터를 직접 긁어옴
  - KOSPI + KOSDAQ 전 종목 PER, PBR, 주가 수집
  - 3개월 모멘텀(주가 상승률) 계산
  - 조건 필터링 + 점수화 → 상위 50종목 선별
- `firebase_upload.py`: 선별된 결과를 Firebase에 저장
- `main.py`: 위 두 개를 순서대로 호출하는 진입점

### 3. Firebase Firestore — "데이터베이스"

- Google이 운영하는 클라우드 DB (NoSQL)
- Python(GitHub Actions)이 데이터를 **쓰고**, Next.js 대시보드가 데이터를 **읽음**
- **인증 방식**: GitHub Secrets에 저장된 서비스 계정 키로 인증
  - `FIREBASE_PROJECT_ID`, `FIREBASE_PRIVATE_KEY`, `FIREBASE_CLIENT_EMAIL`
  - 코드에 직접 적지 않고 환경변수로 주입 → 키 노출 방지

```
저장 구조 (Firestore):
  컬렉션: screener_results
    문서 ID: "2026-05-11_close"
      - run_at: 실행 시각
      - market_date: 기준 날짜
      - run_type: "open" or "close"
      - count: 종목 수
      - results: [ { ticker, name, price, PER, PBR, momentum_3m, score }, ... ]
```

### 4. Next.js 대시보드 — "웹 화면" (미구현)

- Vercel에 배포 → 별도 서버 없이 URL로 접속
- Firebase에서 최신 스크리닝 결과를 불러와서 테이블/차트로 표시
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

| 지표 | 조건 | 가중치 | 의미 |
|------|------|--------|------|
| PER | 5 ~ 20 | 30% | 저평가되어 있지만 적자는 아닌 종목 |
| PBR | 0.5 ~ 2.0 | 20% | 자산 대비 적정 가격 |
| 3개월 모멘텀 | > 5% | 50% | 최근 3개월간 주가 상승 중인 종목 |

점수 = PER점수×0.3 + PBR점수×0.2 + 모멘텀점수×0.5 → 상위 50종목 저장

---

## 파일 구조

```
QuantTrading/
├── .github/
│   └── workflows/
│       └── screener.yml      # GitHub Actions 스케줄 정의
├── screener/
│   ├── main.py               # 진입점
│   ├── screener.py           # pykrx 데이터 수집 + 필터링
│   ├── firebase_upload.py    # Firestore 업로드
│   └── requirements.txt      # Python 의존성
├── dashboard/                # (미구현) Next.js 대시보드
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
