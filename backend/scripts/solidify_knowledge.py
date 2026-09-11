import argparse
import json
from pathlib import Path

from app.services.knowledge_solidification import CandidateMetric, KnowledgeSolidifier


def main() -> None:
    parser = argparse.ArgumentParser(description="生成需人工审核的关键词固化报告")
    parser.add_argument("input", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--approve", action="store_true")
    args = parser.parse_args()
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    report = KnowledgeSolidifier().evaluate(
        [CandidateMetric.model_validate(item) for item in raw], args.version
    )
    args.report.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if args.output:
        KnowledgeSolidifier.write_reviewed(report, args.output, approve=args.approve)


if __name__ == "__main__":
    main()
