from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from app.market.data_service import MarketDataService
from app.market.providers.adata_research import ADataResearchProvider
from app.market.providers.base import ProviderProfile
from app.market.providers.baostock import BaoStockDailyBarProvider
from app.market.service import QuoteService


class ProviderCapabilityService:
    def __init__(
        self,
        *,
        quote_service: QuoteService | None = None,
        market_data_service: MarketDataService | None = None,
    ) -> None:
        self.quote_service = quote_service or QuoteService()
        self.market_data_service = market_data_service or MarketDataService(quote_service=self.quote_service)

    def list_profiles(self) -> list[dict[str, object]]:
        profiles: dict[str, ProviderProfile] = {}
        for provider in self._all_providers():
            profile = getattr(provider, "profile", None)
            if isinstance(profile, ProviderProfile):
                profiles[profile.name] = profile

        return [self._profile_to_dict(profile) for profile in sorted(profiles.values(), key=lambda item: item.name)]

    def _all_providers(self) -> Iterable[object]:
        yield from self.quote_service.providers
        yield from self.market_data_service.history_providers
        yield from self.market_data_service.intraday_providers
        yield BaoStockDailyBarProvider()
        yield ADataResearchProvider()

    @staticmethod
    def _profile_to_dict(profile: ProviderProfile) -> dict[str, object]:
        payload = asdict(profile)
        payload["capabilities"] = [asdict(capability) for capability in profile.capabilities]
        return payload
