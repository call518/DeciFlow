# Laya 로그 검증

[English](laya-validation.md) | [한국어](laya-validation.ko.md) | [문서 안내](README.ko.md) | [README](../README.ko.md)

`scripts/evaluate_laya.py`로 설정한 Laya 모델을 정답 로그와 비교합니다.
각 요청은 로그를 `state`로 보내고 분류(`choice`), 긴급도(`score`), 작업 티켓
필요성(`noul`)을 함께 묻습니다. 분류 코드는 세 답변을 모두 검증하지만,
정답 라벨과의 비교는 **분류 범주만** 평가합니다.
긴급도·티켓 확률의 정확도는 측정하지 않으며 Jev 호출은 거부합니다.

## 평가 실행

`.env`에서 `DECISION_ENGINE=laya`와 `LAYA_MODEL`을 설정하세요.
선택한 모델이 Laya 서버에 준비되어 있어야 합니다. 실행 방식은 하나를 선택합니다:

- **Docker Compose:** UI 컨테이너 안에서 실행합니다.
  `http://laya:8000/v1/systemone`으로 선택한 CPU·CUDA 서비스에 연결합니다.
- **로컬 Python:** uv와 프로젝트 의존성이 설치된 복제 저장소에서 실행합니다.
  `LAYA_API_URL`은 접근 가능한 Laya 주소로 설정하세요. 같은 호스트의 Laya는
  `http://127.0.0.1:8000/v1/systemone`을 사용합니다.

Docker Compose:

```bash
docker compose exec ui uv run --no-sync python -m scripts.evaluate_laya \
  --output /tmp/laya-validation.json
docker compose cp ui:/tmp/laya-validation.json /tmp/laya-validation.json
```

로컬 Python:

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

기본값은 [5개 프로필의 합성 사례 36개](../tests/fixtures/log_evaluation.json)이며,
동시 요청은 최대 두 개로 제한합니다. 평가에는 [`profiles/`](../profiles/)의 번들
기준을 사용하며 UI에서 수정·저장한 기준은 읽지 않습니다.
UI에서 편집한 기준은 같은 정답 로그를 UI에서 분석해 검증하세요.

준비된 모델을 비교하려면 선택한 명령에 `--model` 옵션을 반복해서 추가합니다:

```text
--model english --model multilingual --model typed-decisions
```

자체 사례는 UTF-8 JSON 목록으로 작성하고 `--cases PATH`로 지정하세요:

```json
[
  {
    "log": "application: database connection failed",
    "expected": "error",
    "profile": "application"
  }
]
```

각 사례에는 로그 문자열과 기대 범주(`normal`·`warning`·`error`·`security`·`other` 중 하나)가
필요합니다. `profile` 기본값은 `general`이며 번들 프로필 이름이어야 합니다.
사례 파일 경로는 평가 스크립트를 실행하는 환경에서 읽을 수 있어야 합니다.

## 보고서 확인

생성한 JSON은 UTC `evaluatedAt`과 모델별 항목을 담은 `reports` 목록을 포함합니다:

| 필드 | 의미 |
| --- | --- |
| `model` | 요청한 체크포인트 이름 |
| `total` / `correct` | 전체 사례 수 / 기대 범주와 일치한 예측 수 |
| `failed` | 거절된 요청·유효하지 않은 답변·연결 및 API 오류 |
| `uncertain` | Uncertain으로 표시한 성공 판정 수 |
| `certain` / `certainCorrect` | Uncertain이 아닌 성공 판정 수 / 그중 기대 범주와 일치한 수 |
| `confusionMatrix` | 행은 기대 범주, 열은 예측 범주이며 실패 열도 포함 |
| `rows` | 입력 사례·일치 여부·분류 결과. 성공 시 세 질문과 답변 포함 |

Certain은 DeciFlow의 확률·선택지 구별 검사를 통과했다는 뜻이며 정답 보장이 아닙니다.
대표 정답 로그로 오분류와 검토량을 평가하세요. 합성 사례는 회귀 검증용이며 운영
정확도 추정 자료가 아닙니다. 모델·판정 기준·입력 예산이 결과에 영향을 주므로
실행 결과를 비교할 때 같은 조건을 유지하세요.

응답 스키마는 [요청·결과 JSON](results.ko.md), 검토 임계값은
[불확실성 규칙](usage.ko.md#불확실성과-사람의-검토)을 참고하세요.
