# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python-based quantitative trading system for A-share (Chinese stock) market. Supports strategy development, backtesting, and live trading across multiple platforms:

- **JoinQuant (聚宽)**: Learning and strategy backtesting
- **PTrade (国金证券)**: Live trading
- **QMT/迅投 (华泰证券)**: Live trading
- **Backtrader**: Local backtesting engine

## Directory Structure

```
quant_project/
├── JoinQuantEgs/          # JoinQuant platform strategies and backtests
│   ├── small_cap_strategy.py       # Small-cap swing strategy v1.0
│   ├── sector_sentinel_strategy.py # Sector sentiment detection
│   ├── etf_rotation_strategy.py    # ETF rotation with EPO optimization
│   └── Backtest_details/           # Backtest logs
├── PtradeEgs/             # PTrade platform strategies (most active development)
│   ├── multi_strategy_controller.py   # Multi-strategy controller with capital isolation
│   ├── small_cap_strategy.py          # Small-cap swing v5.4 for PTrade
│   ├── etf_rotation_strategy.py       # ETF rotation v3.0 for PTrade
│   ├── sector_sentinel_strategy.py    # Sector sentinel v0.1 for PTrade
│   └── PROGRESS.md                    # Development progress and API mappings
├── lessons_egs/           # Learning tutorials and course materials
│   ├── meteor/            # Course examples (NumPy, Pandas, Matplotlib)
│   └── 国金证券/           # PTrade API documentation from brokerage
├── docs/                  # JQData reference notebooks (14 Jupyter notebooks)
├── tests/                 # Learning exercises and practice code
├── IFLOW.md               # Comprehensive project documentation and learning roadmap
├── requirements.txt       # Python dependencies
└── env.sh                 # Ubuntu environment setup script
```

## Core Principles

- **JoinQuant code is the golden standard**: Strategy logic in PTrade must match JoinQuant behavior. Fix PTrade to converge on JoinQuant, never modify JoinQuant to accommodate PTrade limitations. (See [PtradeEgs/PROGRESS.md](PtradeEgs/PROGRESS.md))
- **Platform isolation**: Each platform has its own `.py` files with platform-specific API calls. Do not mix platform code.
- **Strategy lifecycle pattern**: All strategies follow `initialize()` -> `before_trading_start()` -> `handle_data()` -> `after_trading_end()`.
- **Global state convention**: Strategies use `g.*` global namespace (JoinQuant/PTrade convention) rather than OOP classes.

## Code Conventions

- UTF-8 encoding (no BOM), LF line endings (Linux standard, no CRLF)
- `# -*- coding: utf-8 -*-` header in Python files
- PEP 8 style, 4-space indent, 88-char line limit
- Chinese comments are intentional and should be preserved
- File naming: lowercase with underscores (`my_strategy.py`)

## Key Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run environment setup (Ubuntu 22.04)
chmod +x env.sh && ./env.sh

# Run a strategy on JoinQuant platform
# Upload the .py file to JoinQuant web interface and run backtest there

# Run a strategy on PTrade platform
# Deploy the .py file to PTrade trading terminal

# Run local backtesting with Backtrader
python scripts/run_single.py --symbol 600519

# Run batch backtesting
python scripts/run_batch.py

# Convert Windows line endings to Linux (when deploying)
dos2unix filename.py

# Check file encoding
file -bi filename.py
```

## Strategy Architecture

### Platform API Differences

JoinQuant and PTrade share similar API patterns but have key differences. See [PtradeEgs/PROGRESS.md](PtradeEgs/PROGRESS.md) for the API field mapping table:

| JoinQuant | PTrade | Description |
|-----------|--------|-------------|
| `valuation.circulating_market_cap` | `float_value` | Circulating market cap |
| `valuation.market_cap` | `total_value` | Total market cap |
| `indicator.roe` | Manual calculation | Single-quarter ROE |
| `context.portfolio.available_cash` | `context.portfolio.cash` | Available cash |

Full PTrade API reference: [lessons_egs/国金证券/【附件1】PTrade所有API函数接口清单.md](lessons_egs/国金证券/【附件1】PTrade所有API函数接口清单.md)

### Multi-Strategy Pattern

`PtradeEgs/multi_strategy_controller.py` implements strategy isolation via:
- Virtual capital pools per strategy
- `safe_buy`/`safe_sell` wrappers for order safety
- Position tracking to prevent cross-strategy interference

### PTrade Progress Rules

See [PtradeEgs/PROGRESS.md](PtradeEgs/PROGRESS.md) for 9 detailed refactoring rules covering strategy isolation, capital allocation, position tagging, and platform migration notes.

## Dependencies

Core: `pandas`, `numpy`, `backtrader`, `akshare`, `jqdatasdk`
ML: `scikit-learn`, `xgboost`
Visualization: `matplotlib`, `seaborn`, `plotly`, `mpl_finance`
Other: `pyyaml`, `jupyter`, `pyarrow`, `jinja2`

## Important Files

| Purpose | Path |
|---------|------|
| Project documentation & learning roadmap | [IFLOW.md](IFLOW.md) |
| PTrade refactoring rules & API mappings | [PtradeEgs/PROGRESS.md](PtradeEgs/PROGRESS.md) |
| Multi-strategy framework agent spec | [.iflow/agents/multi-strategy-framework-architect.md](.iflow/agents/multi-strategy-framework-architect.md) |
| PTrade API documentation | [lessons_egs/国金证券/](lessons_egs/国金证券/) |
| JoinQuant API reference | [JoinQuantEgs/api_reference.md](JoinQuantEgs/api_reference.md) |
| JQData query notebooks | [docs/聚宽数据查询/](docs/聚宽数据查询/) |
