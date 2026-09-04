from decimal import Decimal

from paper_live import EnvironmentController, ExecutionGateway, PaperAccount, VirtualMatchingEngine
from paper_live.e2e import PaperTradingCycle
from paper_live.risk import RiskGuardian


def test_e2e_buy_cycle():
    account = PaperAccount(Decimal("100000"))
    controller = EnvironmentController()
    gateway = ExecutionGateway(controller, VirtualMatchingEngine(account))
    cycle = PaperTradingCycle(gateway, RiskGuardian(controller, account))
    result = cycle.run(
        "ABC",
        {
            "macro_regime": "BULLISH",
            "fundamental_signal": "BUY",
            "technical_signal": "BUY",
            "sentiment_signal": "POSITIVE",
        },
        Decimal("10"),
        Decimal("100"),
    )
    assert result.action == "BUY"
    assert result.approved
    assert account.positions["ABC"] == Decimal("10")
