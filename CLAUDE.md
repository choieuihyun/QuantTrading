# CLAUDE.md — AI 행동 지침

## 프로젝트 개요
개인용 퀀트 스크리너 + 기업 분석 트레이딩 시스템.
PC 없이 GitHub Actions가 하루 2번 자동 실행 → Firebase에 저장 → Next.js 대시보드로 확인.

## 기술 스택
- **자동화**: GitHub Actions
- **데이터**: pykrx + pandas (한국 주식)
- **저장**: Firebase Firestore
- **프론트**: Next.js + Tailwind CSS + Tremor
- **배포**: Vercel (무료)

## 디렉토리 구조
```
QuantTrading/
├── .github/workflows/      # GitHub Actions 자동화 워크플로
├── screener/               # Python 스크리너 + 백테스트
│   ├── main.py
│   ├── screener.py
│   ├── backtest.py
│   └── firebase_upload.py
├── dashboard/              # Next.js 웹 대시보드
│   ├── app/
│   ├── components/
│   └── lib/
├── CLAUDE.md
├── 작업명세서.md
└── Architecture.md
```

## AI 행동 규칙

### 작업 완료 시 반드시 수행
1. `작업명세서.md`에 작업 이력 추가 (날짜, 내용, 변경 파일)
2. `Architecture.md`에 구조 변경사항 반영
3. 변경된 파일 목록 명시

### 코딩 원칙
- 주석은 WHY가 명확할 때만 작성 (WHAT 설명 금지)
- 불필요한 추상화, 에러 핸들링, 미래 기능 금지
- 보안 취약점(SQL injection, XSS 등) 절대 도입 금지
- Firebase credentials는 환경변수로만 처리, 코드에 하드코딩 금지

### 응답 스타일
- 간결하게, 핵심만
- 파일 경로는 마크다운 링크 형식으로 (`[파일명](경로)`)
- 작업 완료 후 "다음 단계" 한 줄로 안내

## 환경변수 (GitHub Secrets + Vercel)
```
FIREBASE_PROJECT_ID
FIREBASE_PRIVATE_KEY
FIREBASE_CLIENT_EMAIL
NEXT_PUBLIC_FIREBASE_API_KEY
NEXT_PUBLIC_FIREBASE_PROJECT_ID
```
