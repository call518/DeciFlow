"""Evaluate the configured Laya request against labeled, non-sensitive samples."""

import argparse
import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from classifier import DecisionError, Result, classify_log
from config import Engine, get_engine
from profiles import PROFILES

ROOT = Path(__file__).resolve().parents[1]


async def evaluate(engine: Engine, cases: list[dict[str, str]]) -> list[Result]:
    """Compare actual predictions with expected labels; never call paid Jev."""
    if engine.name != "laya":
        raise ValueError("This evaluation requires Laya; it never calls paid Jev.")
    semaphore = asyncio.Semaphore(min(engine.concurrency, 2))
    async with httpx.AsyncClient() as client:

        async def handle_case(case: dict[str, str]) -> Result:
            async with semaphore:
                try:
                    result = await classify_log(
                        case["log"], engine, client, case.get("profile", "general")
                    )
                except DecisionError as error:
                    result = {**error.metadata, "error": str(error)}
            return {
                **case,
                "correct": result.get("decisions", {}).get("category", {}).get("choice")
                == case["expected"],
                "result": result,
            }

        return await asyncio.gather(*(handle_case(case) for case in cases))


def summarize(rows: list[Result]) -> Result:
    """Count mismatches and failures without treating confidence as accuracy."""
    categories = list(PROFILES["general"]["questions"]["category"]["criteria"])
    matrix = {key: dict.fromkeys([*categories, "failed"], 0) for key in categories}
    uncertain = failures = correct = certain = certain_correct = 0
    for row in rows:
        result = row["result"]
        failed = "error" in result
        predicted = "failed" if failed else result["decisions"]["category"]["choice"]
        matrix[row["expected"]][predicted] += 1
        failures += failed
        correct += row["correct"]
        assessment = result.get("decisionAssessments", {}).get("category", {})
        uncertain += assessment.get("uncertain") is True
        if not failed and assessment.get("uncertain") is False:
            certain += 1
            certain_correct += row["correct"]
    return {
        "total": len(rows),
        "correct": correct,
        "failed": failures,
        "uncertain": uncertain,
        "certain": certain,
        "certainCorrect": certain_correct,
        "confusionMatrix": matrix,
    }


def main() -> None:
    """Write a live evaluation report without modifying application settings."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
    )
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "tests/fixtures/log_evaluation.json"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/laya-validation.json")
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    engine = get_engine()
    if engine.name != "laya":
        parser.error(
            "Select Laya in Configurations (or .env without a UI override); this script never calls paid Jev."
        )
    cases = json.loads(args.cases.read_text())
    if not cases or any(
        not isinstance(case, dict)
        or not isinstance(case.get("log"), str)
        or case.get("expected")
        not in PROFILES["general"]["questions"]["category"]["criteria"]
        or case.get("profile", "general") not in PROFILES
        for case in cases
    ):
        parser.error("Cases require log text, a valid expected category and profile.")
    reports = []
    for model in args.model or [engine.model]:
        selected = replace(engine, model=model)
        _ = selected.head_tokens
        rows = asyncio.run(evaluate(selected, cases))
        correct = sum(row["correct"] for row in rows)
        reports.append({"model": model, **summarize(rows), "rows": rows})
        print(f"{model}: {correct}/{len(rows)} expected labels matched")
    args.output.write_text(
        json.dumps(
            {"evaluatedAt": datetime.now(UTC).isoformat(), "reports": reports}, indent=2
        )
    )
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
