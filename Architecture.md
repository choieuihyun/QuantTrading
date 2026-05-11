# Architecture.md — 시스템 구조

## 전체 흐름

```
[GitHub Actions]
  하루 2회 자동 실행 (오전 9시, 오후 4시 KST)
        ↓
[Python 스크리너]
  pykrx로 한국 주식 데이터 수집
  pandas로 필터링 + 지표 계산
  백테스트 결과 산출
        ↓
[Firebase Firestore]
  스크리닝 결과 저장
  타임스탬프별 이력 관리
        ↓
[Next.js 대시보드]
  Vercel 배포 (무료)
  PC + 모바일 반응형
  Tremor 컴포넌트로 차트/테이블 표시
```

## 컴포넌트 상세

### 1. Python 스크리너 (`screener/`)

| 파일 | 역할 |
|------|------|
| `main.py` | 진입점, 전체 파이프라인 실행 |
| `screener.py` | 종목 필터링 로직 (PER, PBR, 모멘텀 등) |
| `backtest.py` | 백테스트 로직 |
| `firebase_upload.py` | Firestore 업로드 |

### 2. GitHub Actions (`.github/workflows/`)

| 파일 | 역할 |
|------|------|
| `screener.yml` | 스케줄 실행 + Python 환경 설정 |

### 3. Next.js 대시보드 (`dashboard/`)

| 경로 | 역할 |
|------|------|
| `app/page.tsx` | 메인 대시보드 |
| `app/stocks/[ticker]/page.tsx` | 개별 종목 상세 |
| `components/ScreenerTable.tsx` | 스크리닝 결과 테이블 |
| `components/StockChart.tsx` | 주가 차트 |
| `lib/firebase.ts` | Firebase 클라이언트 초기화 |

## 데이터 모델 (Firestore)

### Collection: `screener_results`
```json
{
  "timestamp": "2026-05-11T09:00:00+09:00",
  "date": "2026-05-11",
  "stocks": [
    {
      "ticker": "005930",
      "name": "삼성전자",
      "price": 75000,
      "per": 12.3,
      "pbr": 1.2,
      "momentum_3m": 0.08,
      "score": 87.5
    }
  ]
}
```

## 스크리닝 기준 (초안)

| 지표 | 조건 | 가중치 |
|------|------|--------|
| PER | 5 ~ 20 | 30% |
| PBR | 0.5 ~ 2.0 | 20% |
| 3개월 모멘텀 | > 5% | 30% |
| 거래량 증가율 | > 평균 대비 150% | 20% |

## 변경 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-05-11 | 초안 작성 |
