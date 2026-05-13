from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SpikeResult:
    package: str
    import_name: str
    status: str
    fields: list[str]
    failure_modes: list[str]
    notes: list[str]


def inspect_package(package: str, import_name: str, *, fields: list[str], notes: list[str]) -> SpikeResult:
    spec = importlib.util.find_spec(import_name)
    status = "available" if spec is not None else "skipped"
    return SpikeResult(
        package=package,
        import_name=import_name,
        status=status,
        fields=fields,
        failure_modes=["network_failure", "schema_change", "rate_limit", "empty_response", "encoding_error"],
        notes=notes + (["package is importable; run manual dry-run before production adoption"] if spec else ["package is not installed; production dependencies unchanged"]),
    )


def run_spike() -> dict[str, Any]:
    results = [
        inspect_package(
            "adata",
            "adata",
            fields=["a_share_list", "fundamental", "concept", "fund_flow"],
            notes=["candidate for A-share fundamentals, concept boards, fund flows, and stock lists"],
        ),
        inspect_package(
            "efinance",
            "efinance",
            fields=["quote", "fund_nav", "index", "industry"],
            notes=["candidate for Eastmoney-style quote wrappers, fund NAV, index, and industry data"],
        ),
    ]
    return {"status": "ready", "providers": [asdict(result) for result in results]}


if __name__ == "__main__":
    print(json.dumps(run_spike(), ensure_ascii=False, indent=2))
