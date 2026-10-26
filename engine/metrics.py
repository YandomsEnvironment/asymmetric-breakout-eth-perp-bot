"""
metrics.py - Performance and Statistical Metrics Engine
Calculates standard institutional quantitative metrics:
- Sharpe Ratio (Annualized)
- Sortino Ratio (Annualized)
- Maximum Drawdown (%) & Max DD Duration
- Calmar Ratio
- Win Rate, Profit Factor, Expectancy
- Statistical significance (t-stat, p-value) of edge
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Any, List


def compute_metrics(
    trades: List[Dict[str, Any]],
    equity_curve: pd.Series,
    interval: str = "1h",
    initial_capital: float = 10000.0
) -> Dict[str, Any]:
    """
    Computes institutional performance metrics from a trade list and equity series.
    """
    if len(trades) == 0 or equity_curve.empty:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "cumulative_return_pct": 0.0,
            "cagr_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "calmar_ratio": 0.0,
            "avg_trade_return_pct": 0.0,
            "win_loss_ratio": 0.0,
            "t_stat": 0.0,
            "p_value": 1.0,
            "has_stat_edge": False
        }

    # Annualization factor
    periods_per_year = 365.25 * 24 if interval == "1h" else 365.25 * 96

    # Returns per bar
    bar_returns = equity_curve.pct_change().dropna()
    total_bars = len(equity_curve)
    years = total_bars / periods_per_year if total_bars > 0 else 1.0

    # Capital & Return
    ending_capital = equity_curve.iloc[-1]
    cumulative_return = (ending_capital - initial_capital) / initial_capital
    cagr = ((ending_capital / initial_capital) ** (1.0 / max(years, 0.01))) - 1.0 if ending_capital > 0 else -1.0

    # Trade statistics
    trade_returns = [t["return_pct"] for t in trades]
    wins = [r for r in trade_returns if r > 0]
    losses = [r for r in trade_returns if r <= 0]
    
    total_trades = len(trades)
    win_rate = len(wins) / total_trades if total_trades > 0 else 0.0
    
    total_win_amount = sum([t["pnl"] for t in trades if t["pnl"] > 0])
    total_loss_amount = abs(sum([t["pnl"] for t in trades if t["pnl"] < 0]))
    profit_factor = (total_win_amount / total_loss_amount) if total_loss_amount > 0 else (999.0 if total_win_amount > 0 else 0.0)

    avg_win = np.mean(wins) if len(wins) > 0 else 0.0
    avg_loss = abs(np.mean(losses)) if len(losses) > 0 else 0.0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    avg_trade_return = np.mean(trade_returns) if trade_returns else 0.0

    # Drawdown
    running_max = equity_curve.cummax()
    drawdowns = (equity_curve - running_max) / running_max
    max_drawdown = abs(drawdowns.min())

    # Sharpe Ratio (annualized)
    mean_ret = bar_returns.mean()
    std_ret = bar_returns.std()
    if std_ret > 0:
        sharpe = (mean_ret / std_ret) * np.sqrt(periods_per_year)
    else:
        sharpe = 0.0

    # Sortino Ratio (annualized)
    downside_returns = bar_returns[bar_returns < 0]
    downside_std = downside_returns.std()
    if downside_std > 0:
        sortino = (mean_ret / downside_std) * np.sqrt(periods_per_year)
    else:
        sortino = 0.0

    # Calmar Ratio
    calmar = (cagr / max_drawdown) if max_drawdown > 0 else 0.0

    # Statistical significance of trade edge (1-sample t-test testing mean trade return > 0)
    if len(trade_returns) >= 15 and np.std(trade_returns) > 0:
        t_res = stats.ttest_1samp(trade_returns, 0.0, alternative='greater')
        t_stat = float(t_res.statistic)
        p_val = float(t_res.pvalue)
    else:
        t_stat = 0.0
        p_val = 1.0

    has_stat_edge = (p_val < 0.05 and avg_trade_return > 0 and profit_factor > 1.1)

    return {
        "total_trades": total_trades,
        "win_rate": win_rate * 100.0,
        "profit_factor": profit_factor,
        "cumulative_return_pct": cumulative_return * 100.0,
        "cagr_pct": cagr * 100.0,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown_pct": max_drawdown * 100.0,
        "calmar_ratio": calmar,
        "avg_trade_return_pct": avg_trade_return * 100.0,
        "win_loss_ratio": win_loss_ratio,
        "t_stat": t_stat,
        "p_value": p_val,
        "has_stat_edge": has_stat_edge,
        "ending_capital": ending_capital
    }
