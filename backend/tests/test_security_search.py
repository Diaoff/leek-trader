from app.market.security_catalog import find_security_by_symbol, search_securities


def test_search_securities_prefers_tencent_source(monkeypatch) -> None:
    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "data": {
                    "stock": [
                        ["sz", "300750", "宁德时代", "ndsd"],
                        ["us", "BABA", "阿里巴巴", "albb"],
                        ["sh", "600519", "贵州茅台", "gzmt"],
                    ]
                }
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            assert params == {"q": "宁德"}
            return FakeResponse()

    monkeypatch.setattr("app.market.security_catalog.httpx.Client", FakeClient)

    results = search_securities("宁德")

    assert [item["symbol"] for item in results] == ["sz300750"]
    assert results[0]["market"] == "深A"


def test_search_securities_falls_back_to_local_catalog_on_remote_failure(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, params: dict[str, str]):
            raise RuntimeError("network down")

    monkeypatch.setattr("app.market.security_catalog.httpx.Client", FakeClient)

    results = search_securities("gzmt")

    assert results
    assert results[0]["symbol"] == "sh600519"


def test_find_security_by_symbol_fetches_remote_metadata_for_unknown_symbol(monkeypatch) -> None:
    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "data": {
                    "stock": [
                        ["sz", "123456", "测试股份", "csgf"],
                    ]
                }
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            assert params == {"q": "123456"}
            return FakeResponse()

    monkeypatch.setattr("app.market.security_catalog.httpx.Client", FakeClient)

    result = find_security_by_symbol("sz123456")

    assert result is not None
    assert result["name"] == "测试股份"
    assert result["market"] == "深A"

def test_search_securities_uses_raw_code_for_tencent_query(monkeypatch) -> None:
    queries: list[str] = []

    class FakeResponse:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {
                "data": {
                    "stock": [
                        ["sh", "600584", "长电科技", "cdkj"],
                    ]
                }
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get(self, url: str, params: dict[str, str]) -> FakeResponse:
            queries.append(params["q"])
            return FakeResponse()

    monkeypatch.setattr("app.market.security_catalog.httpx.Client", FakeClient)

    results = search_securities("600584")

    assert queries == ["600584"]
    assert results[0]["symbol"] == "sh600584"
    assert results[0]["name"] == "长电科技"


def test_screen_securities_filters_market_and_excludes_st(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.market.security_catalog.load_security_catalog",
        lambda: [
            {"symbol": "sh600519", "code": "600519", "name": "贵州茅台", "market": "沪A", "pinyin_abbr": "gzmt", "tags": []},
            {"symbol": "sz300750", "code": "300750", "name": "宁德时代", "market": "深A", "pinyin_abbr": "ndsd", "tags": ["创"]},
            {"symbol": "sh600001", "code": "600001", "name": "ST测试", "market": "沪A", "pinyin_abbr": "stcs", "tags": ["ST"]},
        ],
    )

    from app.market.security_catalog import screen_securities

    results = screen_securities(market="sh", exclude_st=True, limit=10)

    assert [item["symbol"] for item in results] == ["sh600519"]


def test_screen_securities_filters_keyword_and_tags(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.market.security_catalog.load_security_catalog",
        lambda: [
            {"symbol": "sh600519", "code": "600519", "name": "贵州茅台", "market": "沪A", "pinyin_abbr": "gzmt", "tags": []},
            {"symbol": "sz300750", "code": "300750", "name": "宁德时代", "market": "深A", "pinyin_abbr": "ndsd", "tags": ["创"]},
        ],
    )

    from app.market.security_catalog import screen_securities

    results = screen_securities(query="宁德", tags=["创"], limit=10)

    assert [item["symbol"] for item in results] == ["sz300750"]


def test_screen_securities_applies_market_cap_filter_before_limit(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.market.security_catalog.load_security_catalog",
        lambda: [
            {"symbol": f"sh600{index:03d}", "code": f"600{index:03d}", "name": f"测试{index}", "market": "沪A", "pinyin_abbr": f"cs{index}", "tags": []}
            for index in range(100)
        ],
    )

    class FakeQuote:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            self.name = symbol
            self.price = 10.0
            self.change_percent = 0.0
            self.market_cap = 1000.0 if symbol.endswith("090") else 100.0

    monkeypatch.setattr(
        "app.api.securities.quote_service.list_quotes",
        lambda symbols: [FakeQuote(symbol) for symbol in symbols],
    )

    response = client.get("/api/v1/securities/screen", params={"min_market_cap": 900.0, "limit": 50})

    assert response.status_code == 200
    results = response.json()
    assert [item["symbol"] for item in results] == ["sh600090"]
