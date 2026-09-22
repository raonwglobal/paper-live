from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from .execution import Fill, PaperAccount
from .execution_audit import ExecutionAuditTrail
from .pnl import PortfolioLedger, Side
from .reflection import SelfReflectionWorker, TradeEpisode
from .trade_facade import InternalTradeFacade, PortfolioPreflightResult


@dataclass(frozen=True)
class PaperExecutionResult:
    preflight: PortfolioPreflightResult
    fills: tuple[Fill, ...]
    pnl_audits: tuple[str, ...]
    reflection_episodes: tuple[str, ...]


@dataclass
class PaperExecutionOrchestrator:
    """Connect preflight -> paper fill -> PnL -> reflection for one run."""

    facade: InternalTradeFacade
    ledger: PortfolioLedger = field(default_factory=PortfolioLedger)
    reflection_worker: SelfReflectionWorker | None = None
    audit_trail: ExecutionAuditTrail | None = None

    def execute(
        self,
        rows: tuple[dict, ...] | list[dict],
        *,
        account: PaperAccount,
        latest_prices: dict[str, Decimal],
        markets: dict[str, str] | None = None,
        broker: str = "toss",
        order_type: str = "MARKET",
        lot_size: Decimal = Decimal("1"),
        run_manifest_id: str | None = None,
    ) -> PaperExecutionResult:
        """Fail closed on any preflight rejection; only the approved batch reaches the paper gateway."""
        if self.facade.controller.get_current_mode().value not in {"PAPER_SANDBOX", "VIRTUAL_BACKTEST"}:
            raise PermissionError("PaperExecutionOrchestrator requires PAPER_SANDBOX or VIRTUAL_BACKTEST")

        audit = self.audit_trail or self.facade.audit_trail
        preflight = self.facade.preflight_portfolio(
            rows,
            account=account,
            latest_prices=latest_prices,
            markets=markets,
            broker=broker,
            order_type=order_type,
            lot_size=lot_size,
        )
        if not preflight.all_approved:
            return PaperExecutionResult(preflight, (), (), ())

        row_by_symbol = {
            str(row.get("symbol", "")).strip(): row
            for row in rows
            if bool(row.get("portfolio_selected"))
        }
        fills: list[Fill] = []
        pnl_audits: list[str] = []
        episodes: list[str] = []

        for approved in preflight.approved:
            intent = approved.intent
            if intent is None:
                continue
            row = row_by_symbol.get(intent.symbol)
            if row is None:
                continue
            result = self.facade.submit_portfolio_row_revalidated(
                row,
                account=account,
                latest_prices=latest_prices,
                markets=markets,
                broker=broker,
                order_type=order_type,
                lot_size=lot_size,
                recommendation_run_id=run_manifest_id,
                portfolio_rank=(int(row["portfolio_rank"]) if row.get("portfolio_rank") is not None else int(row["rank"]) if row.get("rank") is not None else None),
                run_manifest_id=run_manifest_id,
            )
            if not isinstance(result, Fill):
                continue
            if result.quantity <= 0 or result.status not in {"FILLED", "PARTIALLY_FILLED"}:
                continue
            fills.append(result)

            if audit is None:
                continue
            submission = next(
                (
                    record
                    for record in reversed(audit.records)
                    if record.client_order_id == result.order_id and record.symbol == result.symbol
                ),
                None,
            )
            if submission is None:
                continue

            try:
                self.ledger.apply_fill(result.symbol, Side(result.side.value), result.quantity, result.price)
                mark = Decimal(str(latest_prices[result.symbol]))
                pnl = self.ledger.total_pnl(result.symbol, mark)
                audit.record_pnl(submission.audit_id, pnl, pnl_reference=f"ledger:{result.symbol}")
                pnl_audits.append(submission.audit_id)

                if self.reflection_worker is not None:
                    episode = TradeEpisode(
                        episode_id=f"episode-{uuid4().hex[:16]}",
                        symbol=result.symbol,
                        action=result.side.value,
                        entry_price=str(result.price),
                        exit_price=str(mark),
                        pnl=str(pnl),
                        decision_context={
                            "run_manifest_id": run_manifest_id,
                            "client_order_id": result.order_id,
                            "quantity": str(result.quantity),
                        },
                        outcome="POSITIVE" if pnl > 0 else "NEGATIVE" if pnl < 0 else "NEUTRAL",
                        created_at=datetime.now(UTC).isoformat(),
                    )
                    self.reflection_worker.reflect(episode)
                    audit.record_reflection(submission.audit_id, episode)
                    episodes.append(episode.episode_id)
            except (KeyError, ValueError):
                # Keep the fill auditable; PnL/reflection remain explicitly uncompleted.
                continue

        return PaperExecutionResult(preflight, tuple(fills), tuple(pnl_audits), tuple(episodes))
