# 자산흐름

대체투자 부동산의 투자 가정과 월별 운영자료를 같은 원문·계산 기준으로 대조하는 KIC 공모전 시제품입니다. 모든 시연·평가 자료는 합성 자료입니다.

[실행 데모](https://kic-property-flow-1024.basicchord7.chatgpt.site/)

공개 화면은 로그인 없이 열 수 있습니다. 증빙 보완·기준 저장·재계산·검토 메모는 ChatGPT 로그인 후 계정별 서버 작업공간에서 사용합니다.

## 전체 소스 복원과 실행

[source_release.py](source_release.py)에 Python·웹·합성 자료·평가 코드·보고서 374개 파일을 포함했습니다. Python 3.11 이상에서 아래 명령으로 복원합니다. 복원 프로그램은 외부 통신이나 추출한 코드 실행을 하지 않으며 ZIP과 파일별 해시를 검사합니다. 이미 내용이 있는 폴더는 덮어쓰지 않습니다.

```bash
git clone https://github.com/rnlcksgdk-000/kic-property-flow.git
cd kic-property-flow
python source_release.py --verify-only
python source_release.py --output source
cd source/python
python -m property_flow.cli --asset PF-A --case combined
python -m property_flow.cli --mock-agent --output output/agent_report.json
```

위 두 계산 명령에는 API 키나 추가 패키지가 필요 없습니다. 대표 결과는 세전 배분안 4,050,000원, 저장 기준 대비 차이 -1,170,000원, 보완 전 확인 항목 4개입니다.

## 주요 파일

| 역할 | 복원 후 경로 | 바로 읽는 동일 소스 |
| --- | --- | --- |
| 원화 계산과 운영 대조 | `source/python/property_flow/engine.py` | [engine.py](review/engine.py) |
| 4개 도구의 실행 순서·중단·기록 | `source/python/property_flow/llm_agent.py` | [llm_agent.py](review/llm_agent.py) |
| 웹 계산과 보완 규칙 | `source/web/public/core.mjs` | [core.mjs](review/core.mjs) |
| CSV·PDF 후보 입력 | `source/python/INPUT_GUIDE.md` | 전체 복원본에 포함 |
| 평가 자료·고정 정답·채점 | `source/python/EVALUATION_GUIDE.md` | 전체 복원본에 포함 |
| 웹 서버·D1·로그인별 저장 | `source/web/` 및 `source/python/WEB_GUIDE.md` | 전체 복원본에 포함 |

`review/`는 검토 편의를 위한 동일 소스 복사본입니다. 실행에는 `source_release.py`로 복원한 전체 폴더를 사용합니다.

## 검증 재현

`source/python` 폴더에서 실행합니다.

```bash
python -m pip install -r requirements-lock.txt
python -m unittest discover -s tests
python scripts/evaluate_stage5.py
python scripts/verify_stage2.py --web-source ../web
```

웹의 핵심 24개 검사는 패키지 설치 없이 실행됩니다.

```bash
cd ../web
node scripts/test-stage4.mjs
```

웹 설치·빌드는 Node 22.13 이상에서 `npm ci`, `npx tsc --noEmit`, `npm run build` 순서입니다. 현재 서버는 ChatGPT 인증 헤더와 D1 계약을 사용합니다. 다른 환경으로 옮길 때 임의 클라이언트 헤더를 사용자 인증으로 신뢰하면 안 됩니다. `web/.openai/hosting.json`의 프로젝트 ID는 현재 데모의 값이며 새 프로젝트에는 해당 프로젝트의 ID를 사용합니다. 자세한 저장 검증 명령은 복원본의 README와 WEB_GUIDE에 있습니다.

## 확인 결과와 한계

- 게시된 소스를 다시 읽어 원본과 같은 파일 해시를 확인하고 복원했습니다. 복원본에서 Python 126개·웹 24개 검사와 대표 CLI 실행이 통과했습니다.
- 기존 Python/JavaScript 사례 12개가 일치했습니다. 새 합성 자산 6개·24개 사례에서 금액·상태·이슈·배분안이 일치했고 금액 비교는 120/120입니다.
- 별도 잘못된 입력 12/12를 거부했습니다. 정해진 모의 Agent 계약 24/24 통과, 잘못된 최종 응답 7/7 거부를 확인했습니다.
- 기존 라벨 규칙을 새 표 형식 TXT 12개에 적용한 필드 일치는 0/48입니다. PDF 후보는 사람이 확인하며 범용 표 추출·OCR로 제시하지 않습니다.
- 배포 웹에서 로그인 후 보완·재계산·검토 메모를 저장하고 새로고침 뒤 버전 8·메모·변경 이력 8건 유지를 확인했습니다.
- 웹은 규칙 계산입니다. Python에 선택적 실제 모델용 모듈이 있지만 실제 API 호출은 0회입니다. 모의 실행과 실제 모델의 도구 선택·자유 서술 성능을 구분합니다.
- 실제 금융 정확도·투자 성과·업무시간 절감·모델 지연과 청구 비용은 검증하지 않았습니다. 합성 결과는 작성자가 설계한 자기 검증입니다.

## 출처와 이용 조건

웹 원본 커밋: `f9e29e2fe9cf3c5b87b05edcaf3dffb9f316b364`.

복원 ZIP SHA256: `f97a2bb16611dcd76c0d23b5ad46572646d91ff2dcd03d2aa8ca6b5045a8133a`.

자체 코드의 외부 공개 라이선스는 지정하지 않았습니다. 복원본의 `python/LICENSE_STATUS.md`, `THIRD_PARTY_NOTICES.json`과 의존성별 이용 조건을 확인하세요. FinQA·TAT-QA·ReAct와 공개 수상작은 설계 참고이며 해당 코드를 복제하지 않았습니다. 출처와 도입 여부는 `python/REFERENCE_REGISTRY.json`에 있습니다. API 키·쿠키·토큰·실제 고객 자료는 포함하지 않습니다.

금액은 합성 자료의 검토용 세전 초안입니다. 실제 투자·송금·세무 신고나 최종 정산 승인을 수행하지 않습니다.
