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
    decision: str
    integration_scope: str
    license_status: str
    dependency_status: str
    fallback_plan: str
    fields: list[str]
    failure_modes: list[str]
    notes: list[str]


def inspect_package(
    package: str,
    import_name: str,
    *,
    decision: str,
    integration_scope: str,
    license_status: str,
    dependency_status: str,
    fallback_plan: str,
    fields: list[str],
    notes: list[str],
) -> SpikeResult:
    spec = importlib.util.find_spec(import_name)
    status = "available" if spec is not None else "skipped"
    return SpikeResult(
        package=package,
        import_name=import_name,
        status=status,
        decision=decision,
        integration_scope=integration_scope,
        license_status=license_status,
        dependency_status=dependency_status,
        fallback_plan=fallback_plan,
        fields=fields,
        failure_modes=["network_failure", "schema_change", "rate_limit", "empty_response", "encoding_error"],
        notes=notes + (["package is importable; run manual dry-run before production adoption"] if spec else ["package is not installed; production dependencies unchanged"]),
    )


def run_spike() -> dict[str, Any]:
    results = [
        inspect_package(
            "adata",
            "adata",
            decision="adopted_for_research",
            integration_scope="research_api,smart_selection,capability_matrix; excluded from primary market data, provider priority, and daily bar storage",
            license_status="license_present_in_upstream_repo_recheck_before_distribution",
            dependency_status="research_optional_dependency_not_required_for_core_market_path",
            fallback_plan="research endpoints and smart selection degrade to controlled empty/neutral results when dependency or network is unavailable",
            fields=["a_share_list", "fundamental", "concept", "fund_flow"],
            notes=[
                "adopted as a research-assist provider only",
                "used by research API, smart selection assist chain, and capability display",
                "does not participate in primary quote or daily bar selection",
            ],
        ),
        inspect_package(
            "efinance",
            "efinance",
            decision="deferred",
            integration_scope="spike_only; not integrated into provider registry, production APIs, or default pages",
            license_status="mit_claimed_in_public_project_metadata_recheck_before_adoption",
            dependency_status="not_added_to_runtime_dependencies",
            fallback_plan="continue using existing eastmoney, sina, and tencent providers; revisit only for explicit fund, bond, or industry scope",
            fields=["quote", "fund_nav", "index", "industry"],
            notes=[
                "overlaps heavily with current EastMoney, Sina, and Tencent coverage",
                "incremental value is limited for the current A-share primary path",
                "re-evaluate only when a dedicated fund, bond, or industry roadmap exists",
            ],
        ),
    ]
    return {"status": "ready", "providers": [asdict(result) for result in results]}


if __name__ == "__main__":
    print(json.dumps(run_spike(), ensure_ascii=False, indent=2))
