# 보안 정책

이 저장소는 공개 저장소입니다. 아래 원칙을 지킵니다.

## 비밀 값
- API 키·토큰·서명 키는 코드에 쓰지 않습니다. 로컬은 `.env`(커밋 금지, `.env.example` 참고), GitHub Actions 는 **Settings → Secrets and variables → Actions** 에만 둡니다: `GOV24_API_KEY`, `PII_DENYLIST`.
- `.gitignore` 가 `.env`, `*.jks`, `*.keystore`, 서비스 계정 JSON, `google-services.json` 을 막습니다.
- APK 서명 키(`android/release.jks`)와 비밀번호는 저장소 밖(본인 PC)에만 보관합니다.
- 키가 실수로 올라가면 **먼저 그 키를 폐기·재발급**하고, 그다음 기록을 지웁니다.

## 자동 점검 (`scripts/security_check.py`)
GitHub Actions 가 수집 전·후에 실행하고, 하나라도 걸리면 커밋·배포를 멈춥니다.
- API 키·토큰·개인키·서비스 계정 패턴, 비밀 파일이 추적 대상인지
- 주민등록번호 형식, `PII_DENYLIST`(내 이름·학번 등 — Secret 으로 등록)에 든 문자열
- HY-in 데이터에 학생 본인 제출 파일명이 섞였는지, http(s) 가 아닌 링크

## 개인정보
- 서버·저장소에는 개인정보를 저장하지 않습니다. ‘내 조건’(학교·소득구간·평점·주소지)은 각자의 휴대폰/브라우저에만 저장됩니다.
- HY-in 동기화는 장학 공지만 가져오고, 로그인한 학생 본인의 제출 서류·신청 상태·비고는 수집하지 않습니다(스크립트와 서버 양쪽에서 차단).
- 학생 포털 비밀번호는 어디에도 입력·저장하지 않습니다.

## 서버·앱
- 관리 API(`/api/refresh`, `/api/import/hyin`)는 24자 이상 `ADMIN_TOKEN` 이 있어야 켜지고, 상수 시간 비교로 검사합니다. 업로드는 크기·필드를 제한합니다.
- 응답에 CSP, `X-Frame-Options: DENY`, `nosniff`, Referrer-Policy, Permissions-Policy, HSTS 를 붙입니다. API 문서 페이지는 끕니다.
- 화면은 모든 데이터를 이스케이프하고, 링크는 http(s) 만 허용합니다. 원격 데이터 주소는 https 만 받습니다.
- 안드로이드: 파일·콘텐츠 접근 끔, 혼합 콘텐츠 차단, 백업 끔, 외부 링크는 http(s)만 브라우저로, 경로 탐색 차단.
- GitHub Actions 는 기본 읽기 권한이고, 필요한 작업에만 쓰기 권한을 줍니다. Dependabot 이 매주 의존성을 점검합니다.

## 문제 신고
보안 문제를 발견하면 공개 이슈 대신 저장소 소유자에게 비공개로 알려 주세요 (Security → Report a vulnerability).
