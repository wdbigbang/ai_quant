# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python-based quantitative trading system for A-share (Chinese stock) market. Supports strategy development, backtesting, and live trading across multiple platforms:

- **JoinQuant (聚宽)**: Learning and strategy backtesting (golden standard for strategy logic)
- **PTrade (国金证券)**: Live trading platform (must converge on JoinQuant behavior)
- **QMT/迅投 (华泰证券)**: Live trading (additional resources in docs/QMT量化交易资料/)
- **Backtrader**: Local backtesting engine (not currently active)

**Current Status**: PTrade v3.0 strategies are being aligned with JoinQuant behavior. See [PtradeEgs/PROGRESS.md](PtradeEgs/PROGRESS.md) for detailed progress tracking and known issues.

## Directory Structure

```
quant_project/
├── JoinQuantEgs/          # JoinQuant platform strategies (golden standard)
│   ├── small_cap_strategy.py       # Small-cap swing strategy v1.0
│   ├── sector_sentinel_strategy.py # Sector sentiment detection
│   ├── etf_rotation_strategy.py    # ETF rotation with EPO optimization
│   ├── ai_debug.py                 # AI-assisted strategy development (v0.0-v0.1)
│   ├── tests/debug.py              # NumPy/Pandas learning exercises
│   ├── api_reference.md            # JoinQuant API documentation
│   └── Backtest_details/           # Backtest logs
├── PtradeEgs/             # PTrade platform strategies (must match JoinQuant)
│   ├── multi_strategy_controller.py   # Multi-strategy controller v2.1 (capital isolation)
│   ├── small_cap_strategy.py          # Small-cap swing v3.0 (active development)
│   ├── etf_rotation_strategy.py       # ETF rotation v3.0
│   ├── sector_sentinel_strategy.py    # Sector sentinel v0.1
│   ├── PROGRESS.md                    # Version tracking & API mappings
│   └── PTrade_API_学习笔记.md         # PTrade API learning notes
├── Materials/
│   └── ptrade_docs/
│       ├── API-doc-1.md              # PTrade API reference
│       ├── 官方demo/                 # Official PTrade demo strategies (11 files)
│       │   ├── 小市值.py             # Small-cap official demo
│       │   ├── 二八轮动.py           # 2-8 rotation demo
│       │   ├── 双均线.py             # Dual moving average demo
│       │   └── ...                   # Other indicator demos
│       └── ptrade隔离仓位的示例代码.py # Capital isolation example
├── docs/
│   ├── 聚宽/                         # JoinQuant resources
│   │   ├── 聚宽数据查询/             # 28 Jupyter notebooks for JQData queries
│   │   ├── joinquant_api_reference.md
│   │   └── 聚宽API完整参考手册.md
│   ├── DC42-2022年度精选策略/        # JoinQuant 2022 selected strategies
│   ├── QMT量化交易资料/              # QMT platform resources
│   └── 国金证券_大模型赋能投研报告/  # AI-powered research reports
├── CLAUDE.md              # This file
└── dialog.txt             # Development conversation logs
```

**Note**: No requirements.txt exists. Dependencies are managed by each platform (JoinQuant/PTrade provide their own environments).

## Core Principles

### Strategy Development Rules

1. **JoinQuant is the golden standard**: Strategy logic in PTrade must match JoinQuant behavior exactly. **Never modify JoinQuant code to accommodate PTrade limitations** - always fix PTrade to converge on JoinQuant. (See [PtradeEgs/PROGRESS.md](PtradeEgs/PROGRESS.md))

2. **Platform isolation**: Each platform has its own `.py` files with platform-specific API calls. Do not mix platform code. No cross-platform imports.

3. **Strategy lifecycle pattern**: All strategies follow `initialize()` -> `before_trading_start()` -> `handle_data()` -> `after_trading_end()`. This is the JoinQuant/PTrade standard framework.

4. **Global state convention**: Strategies use `g.*` global namespace (JoinQuant/PTrade convention) rather than OOP classes. Example: `g.stock_list = []`, `g.position_last_map = []`.

5. **Version tracking**: Each strategy file has a version number in the header comments. Track changes in PROGRESS.md when updating PTrade strategies to align with JoinQuant.

6. **Chinese comments**: Chinese comments and variable names are intentional and should be preserved. This is a Chinese-market-focused project.

7. **Strategy UUID + position ownership** (v5.5+): All strategies must implement position isolation via UUID tagging:
   - `g.strategy_uuid`: Unique identifier generated on first `initialize()`, persisted via state file
   - `g.owned_positions`: Dict `{code: amount}` tracking ONLY positions bought by this strategy
   - Helper functions: `_is_owned(code)`, `_get_owned_amount(code, context)`, `_get_owned_enable_amount(code, context)`, `_sync_owned_positions(context)`
   - **NEVER** use `context.portfolio.positions` directly for strategy decisions — always use `g.owned_positions` + helper functions
   - When buying: add to `g.owned_positions` with estimated shares
   - When selling: remove from `g.owned_positions`
   - Other strategies' positions, manual trades (convertible bonds, reverse repos, etc.) are invisible
   - First startup: `g.owned_positions = {}` (empty), log warning if account has unowned positions
   - This enables multiple strategies to run independently without interference

### 持久化与标签标记规范（PTrade平台）

**标准文件**: [PtradeEgs/shared_position_validator.py](PtradeEgs/shared_position_validator.py) 是持久化和持仓校验逻辑的**单一真理源（Single Source of Truth）**。

**PTrade安全限制**: PTrade禁止以下模块/函数，无法动态加载共享模块：
- `sys` 模块（禁止）
- `os` 模块（禁止）
- `exec()` 函数（禁止，检测为代码注入）

**内联策略**: 由于无法动态导入，必须将 `shared_position_validator.py` 中的核心函数**内联**到每个策略文件中。

**变更流程**:
1. 修改持久化/标签逻辑时，**先修改** `shared_position_validator.py`
2. 然后将核心函数**同步复制**到各策略文件中
3. 核心函数包括：
   - `validate_strategy_positions` - 主校验函数
   - `validate_pool_membership` - 股票池校验
   - `_validate_static_pool` - 静态池校验器
   - `is_owned`, `get_owned_amount`, `get_owned_enable_amount`, `sync_owned_positions` - 持仓辅助函数

**持久化文件路径**: `get_research_path() + "{strategy_name}/state.json"`
- 研究路径: `/home/fly/notebook/`（PTrade实盘）
- 子目录示例: `etf_core_asset_rotation/`, `etf_rotation/`

### 多策略并行验证进度（2026-05-29）

**验证目标**: ETF摸狗 + ETF轮动 双策略并行，验证持仓隔离和持久化机制。

**已完成工作**:
1. **发现PTrade安全限制**（2026-05-29）
   - PTrade禁止 `sys`、`os`、`exec()`，无法动态导入共享模块
   - 通过诊断日志确认：文件存在但Python无法导入
   
2. **制定持久化规范**
   - 以 `shared_position_validator.py` 为单一真理源
   - 变更流程：先改共享文件，再同步到各策略
   
3. **校验函数内联**
   - ETF摸狗（ETF_Core_Asset_Rotation_Strategy.py）：已内联约150行校验代码
   - ETF轮动（etf_rotation_strategy.py）：已内联约150行校验代码
   
4. **清理诊断代码**
   - 移除 `_diagnose_import_paths()` 函数及调用
   - 代码更简洁
   
5. **双策略配置**
   - ETF摸狗：`g.capital_ratio = 0.2`（20%资金）
   - ETF轮动：`g.capital_ratio = 0.2`（20%资金）

**当前状态**（2026-05-29）:
- 双策略已部署到PTrade模拟盘
- 第一天运行初步观察：两个策略调仓看起来互相没影响
- 护网期间测试环境不稳定，需持续观察

**待验证项**:
- [ ] 持仓隔离：各策略的 `g.owned_positions` 是否独立追踪
- [ ] 持久化：各策略的 `state.json` 是否独立保存/恢复
- [ ] 资金分配：各策略是否只用20%资金
- [ ] 跨策略干扰：一个策略的持仓是否影响另一个策略

**已知问题**:
- 深圳ETF数据加载可能延迟（159915.SZ 出现过数据不足警告）
- 建议后续观察是否持续

## Code Conventions

- UTF-8 encoding (no BOM), LF line endings (Linux standard, no CRLF)
- `# -*- coding: utf-8 -*-` header in Python files
- PEP 8 style, 4-space indent, 88-char line limit
- Chinese comments are intentional and should be preserved
- File naming: lowercase with underscores (`my_strategy.py`)

## Development Workflow

### Running Strategies

```bash
# JoinQuant: Upload .py file to web interface
# https://www.joinquant.com/ -> Strategy -> Create -> Upload

# PTrade: Deploy .py file to terminal
# PTrade terminal -> Strategy -> Import -> Run

# Local learning exercises (NumPy/Pandas/Matplotlib)
cd JoinQuantEgs/tests
python debug.py  # Requires demo.csv data file
```

### Jupyter Notebooks for Data Queries

```bash
# JoinQuant provides 28 Jupyter notebooks for JQData queries
# Located in docs/聚宽/聚宽数据查询/
# Topics: Alpha factors, macro data, bonds, funds, options, technical indicators

# Start Jupyter to explore data queries
jupyter notebook docs/聚宽/聚宽数据查询/
```

### Code Quality

```bash
# Convert Windows line endings to Linux (critical for deployment)
dos2unix filename.py

# Check file encoding (must be UTF-8)
file -bi filename.py

# Verify LF line endings
grep -c $'\r' filename.py  # Should return 0
```

## Strategy Architecture

### Active Strategies

| Strategy | JoinQuant Version | PTrade Version | Description |
|----------|-------------------|----------------|-------------|
| Small-Cap Swing | v1.0 | v3.0 (aligning) | Deep100 index, ROE+market cap filters, 8% stop-profit |
| ETF Rotation | v3.0 | v3.0 | 5 ETF pool, EPO optimization, monthly rebalance |
| Sector Sentinel | v0.1 | v0.1 | Sector sentiment detection, industry rotation |

### Multi-Strategy Controller (v2.1)

[PtradeEgs/multi_strategy_controller.py](PtradeEgs/multi_strategy_controller.py) implements strategy isolation:

- **Capital allocation**: `g.capital_ratio_small_cap = 1.0`, `g.capital_ratio_etf = 0.0` (percentage split)
- **Virtual positions tracking**: Prevents cross-strategy overselling via `g.strategies['small_cap']['positions']`
- **Safe order wrappers**: `safe_buy()` checks capital ratio, `safe_sell()` checks virtual positions
- **Scheduled execution**: Different time slots for each strategy (14:49 sell, 10:30/13:30/14:30 cooldown check)
- **Money market fund**: 银华日利 (511880.XSHG) for empty position periods

### Platform API Differences

**Stock code formats:**
- JoinQuant: `600000.XSHG` (上交所), `000001.XSHE` (深交所)
- PTrade: `600000.SS` (上交所), `000001.SZ` (深交所), `000300.XBHS` (指数)

**Key API mappings** (see [PtradeEgs/PROGRESS.md](PtradeEgs/PROGRESS.md) for complete table):

| JoinQuant | PTrade | Description |
|-----------|--------|-------------|
| `valuation.circulating_market_cap` | `float_value` | Circulating market cap |
| `valuation.market_cap` | `total_value` | Total market cap |
| `indicator.roe` | Manual calculation from `np_parent_company_owners` / `total_shareholder_equity` | Single-quarter ROE |
| `context.portfolio.available_cash` | `context.portfolio.cash` | Available cash |
| `get_price()` | `get_history()` | Historical price data |
| `log.info()` | `log.info()` | Same logging API |

### ROE Calculation in PTrade

PTrade doesn't provide single-quarter ROE directly. Must calculate manually:

```python
# Get quarterly reports (not cumulative!)
# Q1 = 一季报 (March report)
# Q2 = 半年报 - Q1 (June - March)
# Q3 = 三季报 - Q2 (Sept - June)
# Q4 = 年报 - Q3 (Dec - Sept)

roe_q = net_profit / total_equity
```

This is a **known source of discrepancy** between platforms. See [PtradeEgs/ROE改善筛选差异分析.md](PtradeEgs/ROE改善筛选差异分析.md) for debugging details.

## Documentation & Resources

### Key Files

| Purpose | Path |
|---------|------|
| **PTrade version tracking** | [PtradeEgs/PROGRESS.md](PtradeEgs/PROGRESS.md) - Current status, API mappings, known issues |
| **ROE discrepancy analysis** | [PtradeEgs/ROE改善筛选差异分析.md](PtradeEgs/ROE改善筛选差异分析.md) |
| **PTrade API learning notes** | [PtradeEgs/PTrade_API_学习笔记.md](PtradeEgs/PTrade_API_学习笔记.md) |
| **JoinQuant API reference** | [JoinQuantEgs/api_reference.md](JoinQuantEgs/api_reference.md) |
| **PTrade API reference** | [Materials/ptrade_docs/API-doc-1.md](Materials/ptrade_docs/API-doc-1.md) |
| **Official PTrade demos** | [Materials/ptrade_docs/官方demo/](Materials/ptrade_docs/官方demo/) - 11 example strategies |
| **Capital isolation example** | [Materials/ptrade_docs/ptrade隔离仓位的示例代码.py](Materials/ptrade_docs/ptrade隔离仓位的示例代码.py) |
| **JQData query notebooks** | [docs/聚宽/聚宽数据查询/](docs/聚宽/聚宽数据查询/) - 28 Jupyter notebooks |
| **JoinQuant full API manual** | [docs/聚宽/聚宽API完整参考手册.md](docs/聚宽/聚宽API完整参考手册.md) |

### Example Strategies

**Official PTrade demos** (11 files in Materials/ptrade_docs/官方demo/):
- 小市值.py - Small-cap official demo
- 二八轮动.py - 2-8 rotation
- 双均线.py - Dual moving average
- 三因子.py - Three-factor model
- 单因子.py - Single-factor model
- 指数增强.py - Index enhancement
- AROON指标.py - AROON indicator
- 阳线买入.py - Bullish candle buy
- 猛犸.py - Mammoth strategy
- 协整配对交易策略.py - Cointegration pairs trading
- 日内交易策略.py - Intraday trading

**JoinQuant 2022精选** (docs/DC42-2022年度精选策略/聚宽2025年精选/):
- 20小盘股动态调仓，100只10年17倍.py
- 66手把手教你构建ETF策略候选池.py
- 100使用K-means聚类对基金分类.py
