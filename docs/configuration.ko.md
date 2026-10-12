# 설정

[English](configuration.md) | [한국어](configuration.ko.md) | [README](../README.ko.md)

DeciFlow 설정은 `.env`에서 관리하며 프로세스 환경변수가 우선합니다.
Laya 서버 설정은 Laya 호스트에서 별도로 관리합니다.

| 환경변수 | 기본값 | 역할 |
| --- | --- | --- |
| `DECISION_ENGINE` | `laya` | `laya` 또는 `jev` |
| `DECIFLOW_DATA_DIR` | `/var/lib/deciflow-data` | Actions·Criteria 공통 저장 루트; 쓰기 권한 필요 |
| `DECIFLOW_ACTIONS_DIR` | `DECIFLOW_DATA_DIR/actions` | Actions 경로만 개별 재정의; Criteria에는 영향 없음 |
| `PORT` | `4000` | DeciFlow 웹 포트 |
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | 프록시 접두사를 포함한 전체 Laya URL |
| `LAYA_API_KEY` | `changeme` | Laya 서버와 동일한 키 |
| `LAYA_MODEL` | `multilingual` | 내장 모델 또는 등록한 사용자 체크포인트 이름; 서버에 모델 필요 |
| `LAYA_MAX_TOKENS` | 빈 값 | `max_len`으로 전달; 빈 값은 내장 모델 기본값 유지, 사용자 모델은 필수 |
| `LAYA_HEAD_TOKENS` | `256` | `head_max_len`으로 전달; 질문·선택지 예산이며 전체 윈도 미만 |
| `LAYA_CONCURRENCY` | `4` | 실행별 최대 Laya 동시 요청 수; 양의 정수 |
| `JEV_API_KEY` | 미설정 | Jev API 키 |
| `JEV_MODEL` | `jev-1.13.0` | TypeSafe 지원 버전 ID 또는 `jev-latest` 등의 별칭 |
| `JEV_MAX_INPUT_BYTES` | `30000` | Jev 요청 JSON의 UTF-8 바이트 예산; 1~30000 허용 |
| `JEV_CONCURRENCY` | `4` | 실행별 최대 Jev 동시 요청 수; 양의 정수 |

`LAYA_HEAD_TOKENS=384`이면 매 Laya 요청에 `"head_max_len": 384`를 전송합니다.
`LAYA_MAX_TOKENS=1024`는 `"max_len": 1024`를 전송합니다. 해당 요청에서
체크포인트 기본값을 덮어씁니다. `.env` 변경 후 DeciFlow를 재시작하세요.
DeciFlow 설정이므로 이 값을 전송하기 위해 원격 Docker를 변경할 필요는 없습니다.

**내장 모델은 `LAYA_MAX_TOKENS=`를 비워두는 것을 권장합니다.** DeciFlow가
`LAYA_MODEL`에 따라 English 512, Multilingual·Typed-decisions 8192를 자동 적용합니다.
빈 값이면 내장 모델을 바꿀 때 `LAYA_MODEL`만 변경하고 토큰 예산은 수정하지 않아도
됩니다. 사용자 모델은 예산을 명시해야 합니다. 숫자를 직접 지정하면 자동 선택 대신
그 값을 사용합니다. English는 최대 512,
다른 모델은 최대 8192를 허용합니다. 질문 예산은 양의 정수이며 전체 윈도 미만이어야
합니다. 256은 기본값이며 Laya API 최대값이 아닙니다. 이는 **DeciFlow 검증 범위**입니다.
공식 체크포인트 기본값은 English 512/192, 나머지 1024/256 토큰입니다.
서버는 별도로 `LAYA_MAX_TOKEN_BUDGET`(기본 8192)을 두 예산에 적용하며 초과하면
422를 반환합니다. 요청 예산은 결과 JSON의 `inputBudget`에 기록됩니다.

예산은 고정 예약량이 아닙니다. 실제 로그 공간은 렌더링된 질문에 따라 달라지므로
단순히 `max_len - head_max_len`으로 계산하면 안 됩니다. `usage.truncated`는 로그
잘림 정보이며 지시문 전체 보존을 뜻하지 않습니다. Laya가 범주 선택지의 구별 손실을
보고하면 DeciFlow는 Uncertain·Needs review로 표시하고 이유를 보여줍니다.
원래 판정 범주·확률·응답은 그대로 보존합니다.

사용자 체크포인트는 원격 서버의 `LAYA_EXTRA_MODELS`에 이름을 등록한 뒤
`LAYA_MODEL`에 그 이름을 넣고, 검증한 입력 용량 내에서 `LAYA_MAX_TOKENS`를
명시하세요. 이름은 영문자로 시작하며 영문자·숫자·`_`·`-`를 허용합니다.
URL·경로는 받지 않습니다. 응답의 `routing.model`이 지정한 사용자 모델을
확인해 주지 않으면 거절하여 다른 모델로 조용히 전환되는 것을 막습니다.
DeciFlow가 모델을 설치하거나 학습하지는 않습니다.

동시 요청 수는 Paste·Batch·Realtime 모두에 적용됩니다. Laya v0.4.1 추론 워커는
1개입니다. `LAYA_CONCURRENCY`는 클라이언트 요청 수, 서버 `LAYA_MAX_CONCURRENT`는
수용 제한입니다(기본 16, 초과하면 503). GPU 추론 병렬도 설정은 아닙니다.
잘림·라우팅 정보를 위해 서버 `LAYA_JEV_STRICT=0`을 유지하고 CPU `LAYA_THREADS`는
물리 코어 수 이하로 설정하세요. 파일 Batch는 여전히 개별 요청을 전송하며
실제 추론 배치 API를 사용하지 않습니다.

Jev는 Laya 예산을 무시합니다. Jev API는 `head_max_len`에 해당하는 옵션이 없으며
Jev 1.13은 state + 가장 긴 질문 32k, 전체 요청 64k 토큰 제한을 적용합니다.
`JEV_MAX_INPUT_BYTES`는 보수적 바이트 검사이며 토큰 할당량이 아닙니다.
Jev 모델 가용성은 계정·API에 따르며 별칭의 제한은 바뀔 수 있습니다.

파라미터 동작과 반영·보류 사항은 [연동 검토](laya-integration-review.ko.md)를
참고하세요. 5개 프로필의 정답 라벨을 붙인 합성 사례 36개(헤더 변경 사례 포함)를
평가하려면 다음을 실행합니다:

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

보고서는 오분류 행렬, 요청 실패, Uncertain 수와 Certain 중 정답 수를 포함합니다.
사례는 회귀 검증용이며 운영 정확도 추정 자료는 아닙니다.
`--cases PATH`로 자체 정답 JSON(`log`, `expected`, 선택 사항 `profile`)을,
`--model NAME`으로 비교할 체크포인트를 지정합니다. Laya만 사용하며 유료 Jev는
호출하지 않습니다.

