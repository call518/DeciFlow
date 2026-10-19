"""Describe and validate typed decisions independently of input and provider."""

import math
from typing import Any


def is_probability(value: object) -> bool:
    """Reject nonfinite numbers, booleans and out-of-range probabilities."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 1
    )


def validate_answer(question: dict[str, Any], answer: dict[str, Any]) -> None:
    """Validate a provider answer against the exact question sent."""
    kind = question["type"]
    # Keep the ±0.02 boundary inclusive despite binary floating-point rounding.
    tolerance = 0.02 + 1e-12
    if kind == "noul":
        if answer["type"] != kind or not is_probability(answer["noul"]):
            raise ValueError(
                "Noul answers must have type noul and a finite yes probability between 0 and 1."
            )
        return
    probabilities = answer["probabilities"]
    criteria = question["criteria"]
    keys = set(criteria) if kind == "choice" else {str(i) for i in range(len(criteria))}
    if not isinstance(probabilities, dict):
        raise TypeError("Probabilities must be a JSON object.")
    if set(probabilities) != keys:
        missing = sorted(keys - set(probabilities))
        unexpected = sorted(set(probabilities) - keys)
        raise ValueError(
            f"Probability keys must match the criteria; missing: {missing}; "
            f"unexpected: {unexpected}."
        )
    if not all(is_probability(p) for p in probabilities.values()):
        raise ValueError("Probabilities must be finite numbers between 0 and 1.")
    total = sum(probabilities.values())
    if abs(total - 1) > tolerance:
        raise ValueError(f"Probabilities must sum to 1 (±0.02); received {total:g}.")
    if kind == "choice":
        if answer.get("type", "choice") != "choice":
            raise ValueError("Choice answers must have type choice.")
        if answer["choice"] not in criteria:
            raise ValueError("The selected choice must match a declared criterion.")
        if not is_probability(answer["confidence"]):
            raise ValueError("Confidence must be a finite number between 0 and 1.")
        return
    score = answer["score"]
    if answer["type"] != kind:
        raise ValueError("Score answers must have type score.")
    if (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not math.isfinite(score)
        or not 0 <= score <= len(criteria) - 1
    ):
        raise ValueError(
            f"Score must be a finite number between 0 and {len(criteria) - 1}."
        )
    if answer["legend"] != {str(i): text for i, text in enumerate(criteria)}:
        raise ValueError("The score legend must match the declared levels exactly.")
    expected = sum(int(k) * p for k, p in probabilities.items())
    if abs(score - expected) > tolerance:
        raise ValueError(
            f"Score must match the probability-weighted value (±0.02); "
            f"expected {expected:g}, received {score:g}."
        )


def answer_value(answer: dict[str, Any]) -> Any:
    """Return the typed scalar used for human corrections."""
    return answer.get("choice", answer.get("score", answer.get("noul")))


UNCERTAINTY_REASONS = frozenset(
    {
        "low_answer_probability",
        "close_probabilities",
        "collapsed_options",
    }
)


def review_options(definition: dict[str, Any]) -> list[str]:
    """Read the explicit Choice options that require human review."""
    return definition.get("reviewOptions", [])


def result_definitions(result: dict[str, Any]) -> dict[str, Any]:
    """Read the frozen typed definitions, or none for failed source reads."""
    return result.get("decisionDefinitions", {})


def result_answers(result: dict[str, Any]) -> dict[str, Any]:
    """Read AI answers without incorporating reviewer corrections."""
    return result.get("decisions", {})


def decision_assessments(result: dict[str, Any]) -> dict[str, Any]:
    """Assess each frozen decision; absent evidence stays unassessed, never Certain."""
    if "decisionAssessments" in result:
        return result["decisionAssessments"]
    if result.get("error"):
        return {}
    assessments = {}
    answers = result_answers(result)
    usage = result.get("providerResponse", {}).get("usage", {})
    for identity, definition in result_definitions(result).items():
        reasons: list[str] = []
        shortened = usage.get("criteria_tokens_dropped", {}).get(identity, 0)
        if type(shortened) is int and shortened > 0:
            reasons.append("criteria_shortened")
        assessment: dict[str, Any] = {"uncertain": None, "reviewReasons": reasons}
        answer = answers.get(identity, {})
        if definition["type"] == "choice":
            probabilities = answer.get("probabilities", {})
            choice = answer.get("choice")
            if (
                choice in probabilities
                and len(probabilities) >= 2
                and all(is_probability(value) for value in probabilities.values())
            ):
                ranked = sorted(
                    probabilities, key=lambda key: probabilities[key], reverse=True
                )
                probability = probabilities[choice]
                margin = round(probabilities[ranked[0]] - probabilities[ranked[1]], 6)
                if probability < 0.7:
                    reasons.append("low_answer_probability")
                if margin < 0.1:
                    reasons.append("close_probabilities")
                options = usage.get("options", {}).get(identity, {})
                if result.get("engine") == "laya" and options.get(
                    "distinct", 0
                ) < options.get("total", 0):
                    reasons.append("collapsed_options")
                assessment.update(
                    uncertain=bool(UNCERTAINTY_REASONS.intersection(reasons)),
                    answerProbability=probability,
                    probabilityMargin=margin,
                    candidates=ranked[:2],
                )
            if choice in review_options(definition):
                reasons.append("other_category")
        assessment["reviewReasons"] = list(dict.fromkeys(reasons))
        assessments[identity] = assessment
    return assessments


def needs_review(result: dict[str, Any]) -> bool:
    """Count a record once when any decision or record-level issue needs review."""
    return not result.get("error") and bool(
        result.get("review")
        or result.get("recordReviewReasons")
        or any(item["reviewReasons"] for item in decision_assessments(result).values())
    )


def decision_bucket(definition: dict[str, Any], answer: dict[str, Any]) -> str | None:
    """Return the chart/filter bucket for a valid scalar, excluding missing answers."""
    kind = definition["type"]
    value = answer.get(kind)
    if kind == "choice":
        return value if value in definition["criteria"] else None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        return None
    if kind == "score":
        levels = definition["criteria"]
        index = min(len(levels) - 1, max(0, int(value + 0.5)))
        return f"{index} · {levels[index].split(':')[0]}"
    return ("0–<25%", "25–<50%", "50–<75%", "75–100%")[min(3, max(0, int(value * 4)))]
