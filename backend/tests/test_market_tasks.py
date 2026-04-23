from app.tasks.market_tasks import refresh_market_quotes, refresh_market_quotes_task


def test_refresh_market_quotes_task_warms_symbols(client, monkeypatch) -> None:
    import app.tasks.market_tasks as market_tasks

    monkeypatch.setattr(
        market_tasks.QuoteService,
        "refresh_quotes",
        lambda self, symbols=None: [
            type("Quote", (), {"symbol": "sh600519"})(),
            type("Quote", (), {"symbol": "sz000001"})(),
        ],
    )

    result = refresh_market_quotes_task(["sh600519", "sz000001"])

    assert result["status"] == "refreshed"
    assert result["task"] == "refresh_market_quotes"
    assert result["count"] == 2
    assert result["symbols"] == ["sh600519", "sz000001"]


def test_refresh_market_quotes_wrapper_uses_default_configured_symbols(client, monkeypatch) -> None:
    import app.tasks.market_tasks as market_tasks

    monkeypatch.setattr(
        market_tasks,
        "refresh_market_quotes_task",
        lambda symbols=None: {
            "status": "refreshed",
            "task": "refresh_market_quotes",
            "symbols": symbols,
            "count": len(symbols or []),
        },
    )

    result = refresh_market_quotes()

    assert result["symbols"] == market_tasks.settings.market_refresh_symbol_list
    assert result["count"] == len(market_tasks.settings.market_refresh_symbol_list)
