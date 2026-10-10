# Laya 로그 검증 — 2026-10-10

[English](laya-validation.md) | [한국어](laya-validation.ko.md)

**표시·입력 예산 수정은 검증했지만, 로그 분류는 아직 신뢰하기 어렵습니다.**
원격 CUDA 서버에서 General system 대표 사례 13건을 시험했습니다. 기대 범주는
[검증 샘플](../tests/fixtures/general_evaluation.json)에 기록한 운영 관점의 판단이며,
독립적인 정확도 벤치마크는 아닙니다. 유료 Jev 호출은 하지 않았습니다.

| 체크포인트 | 최종 기대 범주 일치 | 최종 Certain 결과 |
| --- | --- | --- |
| English | 9/13 | 0/13 |
| Multilingual | 5/13 | 4/13 |
| Typed-decisions | 6/13 | 0/13 |

Certain은 선택 범주 확률·확률 차이 기준을 통과했다는 뜻이며 정답이라는 뜻이
아닙니다. confidence 척도를 고쳐도 Certain 결과를 억지로 만들지는 않습니다.

## 반영한 변경

- 차트의 **Truncated**는 전체 그룹에서 `usage.truncated=true`로 확인된 응답 수를
  표시합니다. 거절한 판정이므로 요청 실패에도 포함합니다.
- 화면에는 선택 범주의 확률을 표시합니다. 확률 70% 미만 또는 상위 두 범주의
  차이 10%p 미만이면 Uncertain입니다. 엔진 고유 confidence는 JSON에 유지합니다.
- English 질문 예산을 192에서 256으로 늘리고 요청 윈도는 512로 유지했습니다.
  공식 토크나이저 기준으로 192에서는 지시문 89토큰 중 26토큰이 빠지고,
  256에서는 전부 들어갑니다. Multilingual·Typed-decisions는 기존 256에서도
  지시문이 전부 들어갑니다. 서버가 캐시한 토크나이저 버전을 알려주지 않으므로
  토큰 검사는 공식 저장소의 현재 토크나이저 기준입니다.

`usage.truncated`는 로그 본문 잘림이며 질문 잘림이 아닙니다. 질문 예산을 늘리면
로그에 남는 공간이 줄 수 있습니다. 거절한 로그 원문은 계속 확인할 수 있습니다.

## 적용하지 않은 실험

세 체크포인트에 기존 질문, 늘린 질문 예산, 짧은 긍정형 기준, 짧은 기준과 syslog
헤더 제거를 적용해 156건을 비교했습니다. 짧은 기준은 Typed-decisions의 일치를
7/13에서 10/13으로 늘렸지만 `falseticker`를 Security로, 동기화 실패를 Warning으로
오판했습니다. 헤더 제거도 모든 모델을 개선하지는 않았습니다. 기존 Typed-decisions
요청을 반복한 최종 검증에서는 6/13이 나와, 작은 표본의 결과만으로 운영 기준을
변경하거나 모델을 자동 전환할 만큼 안정적이지 않았습니다.

남은 문제는 로그 의미 판정입니다. 임계값이나 입력 공간을 바꿔도 모델이 익숙하지
않은 서비스 메시지의 뜻을 배우지는 않습니다. 이 범주로 조치를 자동 실행하기 전
더 다양한 실제 로그와 정답으로 검증해야 합니다.

## 최종 검증 재실행

`DECISION_ENGINE=laya`이며 선택한 체크포인트가 서버에 준비된 상태에서:

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

준비된 세 체크포인트를 비교하려면 `--model`을 반복합니다:

```bash
uv run python -m scripts.evaluate_laya \
  --model english \
  --model multilingual \
  --model typed-decisions \
  --output /tmp/laya-validation.json
```

스크립트는 현재 운영 기준을 사용하고 동시 요청을 최대 두 개로 제한하며 개별 응답과
오판을 기록합니다. Jev는 호출을 거부합니다. 과거 비교 실험과 최종 응답은
[laya-validation.json](laya-validation.json)에서 확인할 수 있습니다.
