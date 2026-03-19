# Frontend Design Advancement Roadmap

## Goal
EduInsightAI 웹 프론트엔드를 `입력 -> 분석 -> 결과` 흐름 중심으로 고도화하고, 시각적 신뢰감과 결과 전달력을 강화한다.

## Current Baseline (2026-03-12)
- 프론트 코드가 `frontend/`로 분리됨
- 시각 토큰 1차 정리 완료 (`styles.css`)
- 분석 워크플로우 섹션 추가
- 결과 점수 미터(시각 바) 추가
- `innerHTML` 기반 렌더링 제거로 안전성 개선

## Phase 1 (Done)
1. 프론트 코드 구조 분리
2. 디자인 토큰 정리
3. 요약 점수 시각화
4. 안전한 DOM 렌더링 패턴 적용

## Phase 2 (Next)
1. 정보 위계 개선
- 결과 요약 영역을 상단 2열 구성으로 재배치
- 핵심 지표(총점, 위험 신호, 추천 액션) 우선 노출

2. 상태/피드백 디자인
- 분석 시작/진행/완료/오류 상태별 색상과 아이콘 체계 도입
- 다운로드 버튼에 완료 상태 배지 추가

3. 데이터 시각화 강화
- 카테고리 점수: 바 차트 + 전회 대비(증감) 슬롯 추가
- chunk별 분석: 중요도 강조(High/Medium/Low) 배지 추가

## Phase 3
1. 컴포넌트 구조화
- CSS를 컴포넌트 파일로 분리 (`tokens.css`, `layout.css`, `components/*.css`)
- JS도 렌더/상태/유틸 단위로 분리

2. 접근성 고도화
- 키보드 탐색 순서 점검 및 landmarks 보강
- 폼 에러 메시지 실시간 안내 (`aria-live` 세분화)

3. 성능/품질
- 폰트 로딩 전략 최적화 (preload, display 전략)
- Lighthouse 기준 성능/접근성 점검 루프 수립

## Suggested Execution Order
1. Phase 2-1 정보 위계 개선
2. Phase 2-2 상태/피드백 디자인
3. Phase 2-3 데이터 시각화 강화
4. Phase 3-1 컴포넌트 구조화

## Definition of Done
- 모바일(360px) / 데스크톱(1280px) 레이아웃 모두 깨짐 없음
- 분석 시나리오 1회 전체 흐름에서 사용자 행동 유도 명확
- 주요 UI 상태(대기/진행/완료/오류) 모두 시각적으로 구분 가능
- 핵심 결과(강점/개선/추천) 10초 내 스캔 가능
