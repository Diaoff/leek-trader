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
