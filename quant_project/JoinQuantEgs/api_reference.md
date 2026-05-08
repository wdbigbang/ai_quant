# 聚宽量化交易平台API接口使用文档

> **重要说明**：
> - 本文档基于聚宽JoinQuant平台API整理，适用于量化交易策略开发
> - 目录中带有 **"♠"** 标识的API是 **"回测环境/模拟"** 专用的API，**不能在研究模块中调用**
> - **jqdata模块**在研究环境与回测环境下都可以使用
> - 所有价格单位是元
> - 所有时间都是北京时间(UTC+8)，格式为 `datetime.datetime` 对象
> - 每个交易日结束时自动撤销所有未完成订单（如A股是在17:00之后）

---

## 文档导航

- [策略程序架构](#策略程序架构)
- [策略设置函数](#策略设置函数)
- [数据获取函数](#数据获取函数)
- [技术指标函数](#技术指标函数)
- [数据处理函数](#数据处理函数)
- [交易函数](#交易函数)
- [对象说明](#对象说明)
- [其他函数](#其他函数)
- [注意事项](#注意事项)

---

## 策略程序架构

### 1. initialize(context) - 初始化函数

**功能**：在回测开始时调用一次，用于设置策略参数、交易成本、定时任务等。

**参数**：
- `context`: 策略上下文对象，包含账户信息、时间信息等

**使用示例**：
```python
def initialize(context):
    # 设置基准
    set_benchmark('000300.XSHG')
    
    # 设置要交易的股票
    g.security = '000001.XSHE'
    
    # 设置定时任务
    run_daily(market_open, time='9:30')
    
    # 设置滑点
    set_slippage(FixedSlippage(0.002))
    
    # 设置交易成本
    set_order_cost(OrderCost(
        open_tax=0, 
        close_tax=0.001,
        open_commission=0.0003, 
        close_commission=0.0003,
        close_today_commission=0, 
        min_commission=5
    ), type='stock')
    
    # 设置使用真实价格
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
```

---

### 2. run_daily(func, time, reference_security=None) - 定时运行策略

**功能**：在指定时间运行策略函数

**参数**：
- `func`: 要运行的函数名
- `time`: 运行时间，格式如 '9:30'、'14:50' 或 'every_bar'（每个时间片运行）
- `reference_security`: 参考证券，用于确定交易日历

**使用示例**：
```python
# 每天9:30运行
run_daily(market_open, time='9:30')

# 每个时间片运行（日线回测即每天调用一次）
run_daily(market_open, time='every_bar')

# 每周最后一个交易日10:31运行
run_weekly(market_open, -1, time='10:31')

# 每月第一个交易日10:31运行
run_monthly(market_open, 1, time='10:31')
```

---

### 3. handle_data(context, data) - 运行策略

**功能**：在每个时间片调用（日线回测即每天调用一次）

**参数**：
- `context`: 策略上下文对象
- `data`: 数据对象，包含当前时间片的行情数据

**使用示例**：
```python
def handle_data(context, data):
    security = g.security
    # 获取股票收盘价
    close_data = attribute_history(security, 5, '1d', ['close'])
    MA5 = close_data['close'].mean()
    current_price = close_data['close'][-1]
    
    # 交易逻辑
    if current_price > 1.01 * MA5:
        order_value(security, context.portfolio.available_cash)
```

---

### 4. before_trading_start(context) - 开盘前运行策略

**功能**：在每个交易日开盘前调用（约9:00）

**使用示例**：
```python
def before_trading_start(context):
    # 获取股票池
    g.stock_list = get_index_stocks('000300.XSHG')
    
    # 初始化当日变量
    g.today_bought_stocks = set()
```

---

### 5. after_trading_end(context) - 收盘后运行策略

**功能**：在每个交易日收盘后调用（约15:30）

**使用示例**：
```python
def after_trading_end(context):
    # 记录当日交易
    trades = get_trades()
    for trade in trades.values():
        log.info(f"交易: {trade}")
```

---

### 6. process_initialize(context) - 每次程序启动时运行

**功能**：每次程序启动时运行（包括模拟交易重启）

**使用示例**：
```python
def process_initialize(context):
    # 初始化需要在每次启动时执行的变量
    g.init_complete = True
```

---

### 7. after_code_changed(context) - 模拟交易更换代码后运行

**功能**：模拟交易更换代码后运行，用于更新全局变量

**使用示例**：
```python
def after_code_changed(context):
    # 更新全局变量
    g.security = '000002.XSHE'
```

---

### 8. unschedule_all() - 取消所有定时运行

**功能**：取消所有通过 run_daily/run_weekly/run_monthly 设置的定时任务

**使用示例**：
```python
# 取消所有定时任务
unschedule_all()
```

---

## 策略设置函数

### 1. set_benchmark(security) - 设置基准

**功能**：设置策略比较基准

**参数**：
- `security`: 基准证券代码，如 '000300.XSHG'（沪深300）

**使用示例**：
```python
set_benchmark('000300.XSHG')  # 沪深300指数
set_benchmark('000905.XSHG')  # 中证500指数
```

---

### 2. set_order_cost(OrderCost, type) - 设置佣金/印花税

**功能**：设置交易成本

**参数**：
- `OrderCost`: 交易成本对象
  - `open_tax`: 买入印花税（股票通常为0）
  - `close_tax`: 卖出印花税（股票为0.001，即0.1%）
  - `open_commission`: 买入佣金率（通常为0.0003，即0.03%）
  - `close_commission`: 卖出佣金率（通常为0.0003，即0.03%）
  - `close_today_commission`: 当日平仓佣金率（股票为0）
  - `min_commission`: 最低佣金（通常为5元）
- `type`: 证券类型，'stock'、'fund'、'futures'等

**使用示例**：
```python
# 股票交易成本设置
set_order_cost(OrderCost(
    open_tax=0, 
    close_tax=0.001,
    open_commission=0.0003, 
    close_commission=0.0003,
    close_today_commission=0, 
    min_commission=5
), type='stock')

# 基金交易成本设置
set_order_cost(OrderCost(
    open_tax=0, 
    close_tax=0,
    open_commission=0.0002, 
    close_commission=0.0002,
    min_commission=5
), type='fund')
```

---

### 3. set_slippage(Slippage, type=None) - 设置滑点

**功能**：设置滑点模式，模拟真实交易中的价格冲击

**参数**：
- `Slippage`: 滑点对象
  - `FixedSlippage(0.002)`: 固定滑点0.2%
  - `PriceRelatedSlippage(0.002)`: 按价格比例滑点
- `type`: 证券类型（可选）

**使用示例**：
```python
# 固定滑点
set_slippage(FixedSlippage(0.002))

# 按价格比例滑点
set_slippage(PriceRelatedSlippage(0.002), type='stock')
```

---

### 4. set_option(key, value) - 设置动态复权及其他选项

**功能**：设置各种策略选项

**常用选项**：
- `use_real_price`: 使用真实价格（动态复权模式），建议设置为True
- `avoid_future_data`: 避免未来数据，建议设置为True
- `order_volume_ratio`: 订单成交量比例（默认为0.25，表示不超过当日成交量的25%）

**使用示例**：
```python
# 使用真实价格
set_option('use_real_price', True)

# 避免未来数据
set_option('avoid_future_data', True)

# 设置订单成交量比例
set_option('order_volume_ratio', 0.5)
```

---

## 数据获取函数

### 1. attribute_history(security, count, unit, fields) - 获取历史数据

**功能**：获取单个标的历史数据，支持多个字段

**参数**：
- `security`: 证券代码，如 '000001.XSHE'
- `count`: 获取的天数/分钟数
- `unit`: 时间单位，'1d'（日线）、'1m'（分钟线）
- `fields`: 字段列表，如 ['open', 'close', 'high', 'low', 'volume']

**返回值**：DataFrame 或 Dict

**可用字段**：
- 'open': 开盘价
- 'close': 收盘价
- 'high': 最高价
- 'low': 最低价
- 'volume': 成交量（单位：股）

**使用示例**：
```python
# 获取过去5天的收盘价
close_data = attribute_history(security='000001.XSHE', count=5, unit='1d', fields=['close'])
MA5 = close_data['close'].mean()
current_price = close_data['close'][-1]

# 获取过去10天的OHLCV数据
data = attribute_history(security='000001.XSHE', count=10, unit='1d', 
                        fields=['open', 'close', 'high', 'low', 'volume'])

# 计算移动平均线
MA5 = data['close'].mean()
MA10 = data['close'].rolling(10).mean().iloc[-1]

# 计算收益率
daily_returns = data['close'].pct_change().dropna()
```

---

### 2. get_price(security, end_date=None, count=None, frequency='daily', fields=None, skip_paused=True, fq='pre')

**功能**：获取历史数据，可查询多个标的多字段

**参数**：
- `security`: 证券代码或代码列表
- `end_date`: 结束日期，格式如 '2023-12-31'，默认为当前日期
- `count`: 获取的天数
- `frequency`: 频率，'daily'（日线）、'minute'（分钟线）、'tick'
- `fields`: 字段列表，如 ['open', 'close', 'high', 'low', 'volume', 'money']
- `skip_paused`: 是否跳过停牌
- `fq`: 复权方式，'pre'（前复权，默认）、'none'（不复权）

**返回值**：DataFrame 或 Panel

**使用示例**：
```python
# 获取单只股票过去30天的日线数据
df = get_price('000001.XSHE', end_date='2023-12-31', count=30, 
               frequency='daily', fields=['open', 'close', 'high', 'low', 'volume'])

# 获取多只股票的数据
df = get_price(['000001.XSHE', '000002.XSHE'], end_date='2023-12-31', count=30)

# 获取分钟数据
df = get_price('000001.XSHE', end_date='2023-12-29 15:00:00', count=240, 
               frequency='minute', fields=['close'])
```

---

### 3. history(count, unit, field, security_list=None, df=True, skip_paused=True, fq='pre')

**功能**：获取历史数据，可查询多个标的单个字段

**参数**：
- `count`: 获取的天数
- `unit`: 时间单位，'1d'、'1m'
- `field`: 字段名，如 'close'
- `security_list`: 证券代码列表
- `df`: 是否返回DataFrame（True）或Dict（False）
- `skip_paused`: 是否跳过停牌
- `fq`: 复权方式

**返回值**：DataFrame 或 Dict

**使用示例**：
```python
# 获取多只股票的收盘价
close_prices = history(5, '1d', 'close', ['000001.XSHE', '000002.XSHE'])

# 返回字典格式
close_dict = history(5, '1d', 'close', ['000001.XSHE'], df=False)
```

---

### 4. get_bars(security, count, unit, fields=None, include_now=True, end_dt=None, fq_ref_date=None, df=True)

**功能**：获取历史数据（包含快照数据），支持更灵活的数据获取

**参数**：
- `security`: 证券代码或代码列表
- `count`: 获取的bar数量
- `unit`: 时间单位，'1d'、'1m'、'5m'、'15m'、'30m'、'60m'
- `fields`: 字段列表
- `include_now`: 是否包含当前时间点的数据
- `end_dt`: 结束时间
- `fq_ref_date`: 复权参考日期
- `df`: 是否返回DataFrame

**返回值**：numpy.ndarray 或 DataFrame

**使用示例**：
```python
# 获取5分钟K线数据
bars = get_bars('000001.XSHE', count=100, unit='5m', 
                fields=['open', 'close', 'high', 'low', 'volume'])

# 获取当前时间点的数据
bars = get_bars('000001.XSHE', count=1, unit='1m', include_now=True)
```

---

### 5. get_current_data() ♠ - 获取当前时间数据

**功能**：获取当前时间点的实时数据

**返回值**：字典，key为证券代码，value为 SecurityUnitData 对象

**使用示例**：
```python
# 获取当前数据
current_data = get_current_data()

# 获取单个股票的当前价格
last_price = current_data['000001.XSHE'].last_price

# 检查是否停牌
is_paused = current_data['000001.XSHE'].paused

# 检查是否ST股
is_st = current_data['000001.XSHE'].is_st

# 获取股票名称
name = current_data['000001.XSHE'].name
```

---

### 6. get_fundamentals(query, date=None, statDate=None)

**功能**：查询财务数据

**参数**：
- `query`: 查询对象，使用 query() 函数构建
- `date`: 查询日期，格式如 '2023-12-31'
- `statDate`: 统计日期，如 '2023q4'（2023年第四季度）

**返回值**：DataFrame

**使用示例**：
```python
# 查询估值数据
q = query(
    valuation.code,
    valuation.pe_ratio,
    valuation.pb_ratio,
    valuation.market_cap
).filter(
    valuation.code.in_(['000001.XSHE', '000002.XSHE']),
    valuation.pe_ratio > 0
).order_by(valuation.market_cap.desc())

df_valuation = get_fundamentals(q, date='2023-12-31')

# 查询财务指标
q = query(
    indicator.code,
    indicator.roe,
    indicator.roa,
    indicator.net_profit_margin
).filter(
    indicator.code.in_(['000001.XSHE', '000002.XSHE'])
)

df_indicator = get_fundamentals(q)
```

---

### 7. get_factor_values(securities, factors, start_date, end_date, count=None)

**功能**：获取聚宽因子库中的因子数据

**参数**：
- `securities`: 证券代码列表
- `factors`: 因子名称列表
- `start_date`: 开始日期
- `end_date`: 结束日期
- `count`: 获取天数（可选）

**返回值**：Dict，key为因子名，value为DataFrame

**常用因子**：
- 'market_cap': 市值
- 'book_to_price_ratio': 账面市值比
- 'sales_to_price_ratio': 销售市值比
- 'roe_ttm': TTM净资产收益率
- 'growth': 增长因子
- 'momentum': 动量因子

**使用示例**：
```python
# 获取多个因子
factors = ['market_cap', 'book_to_price_ratio', 'roe_ttm', 'growth']
data = get_factor_values(
    securities=['000001.XSHE', '000002.XSHE'],
    factors=factors,
    start_date='2023-01-01',
    end_date='2023-12-31'
)

# 获取单个因子
market_cap = get_factor_values(['000001.XSHE'], ['market_cap'], 
                               start_date='2023-12-01', end_date='2023-12-31')
```

---

### 8. get_index_stocks(index_code, date=None)

**功能**：获取指数成分股

**参数**：
- `index_code`: 指数代码，如 '000300.XSHG'（沪深300）、'000905.XSHG'（中证500）
- `date`: 查询日期，格式如 '2023-12-31'，默认为当前日期

**返回值**：List，证券代码列表

**使用示例**：
```python
# 获取沪深300成分股
hs300_stocks = get_index_stocks('000300.XSHG')

# 获取历史时点的成分股
hs300_stocks = get_index_stocks('000300.XSHG', date='2023-12-31')

# 获取中证500成分股
zz500_stocks = get_index_stocks('000905.XSHG')
```

---

### 9. get_industry_stocks(industry_code, date=None)

**功能**：获取行业成分股

**参数**：
- `industry_code`: 行业代码，如 'I64'（信息技术）
- `date`: 查询日期

**返回值**：List，证券代码列表

**使用示例**：
```python
# 获取信息技术行业股票
tech_stocks = get_industry_stocks('I64')

# 获取金融行业股票
finance_stocks = get_industry_stocks('I66')
```

---

### 10. get_concept_stocks(concept_code, date=None)

**功能**：获取概念成分股

**参数**：
- `concept_code`: 概念代码
- `date`: 查询日期

**返回值**：List，证券代码列表

**使用示例**：
```python
# 获取人工智能概念股票
ai_stocks = get_concept_stocks('GN041')

# 获取新能源汽车概念股票
ev_stocks = get_concept_stocks('GN038')
```

---

### 11. get_all_securities(types=['stock'], date=None)

**功能**：获取所有标的信息

**参数**：
- `types`: 证券类型列表，'stock'、'fund'、'index'、'futures'等
- `date`: 查询日期

**返回值**：DataFrame

**使用示例**：
```python
# 获取所有股票
all_stocks = get_all_securities(types=['stock'])

# 获取所有基金
all_funds = get_all_securities(types=['fund'])

# 获取所有股票和指数
securities = get_all_securities(types=['stock', 'index'])
```

---

### 12. get_security_info(security)

**功能**：获取单个标的信息

**参数**：
- `security`: 证券代码

**返回值**：SecurityInfo 对象

**使用示例**：
```python
info = get_security_info('000001.XSHE')
print(info.name)      # 股票名称
print(info.start_date) # 上市日期
print(info.type)      # 证券类型
print(info.concepts)  # 所属概念
```

---

### 13. get_trade_days(end_date=None, count=None)

**功能**：获取交易日

**参数**：
- `end_date`: 结束日期
- `count`: 获取天数

**返回值**：List，日期列表

**使用示例**：
```python
# 获取最近5个交易日
trade_days = get_trade_days(count=5)

# 获取指定日期之前的交易日
trade_days = get_trade_days(end_date='2023-12-31', count=10)

# 获取所有交易日
all_trade_days = get_all_trade_days()
```

---

### 14. get_trade_day(security, dt)

**功能**：根据标的获取指定时刻对应的交易日

**参数**：
- `security`: 证券代码
- `dt`: 日期时间

**返回值**：Datetime

**使用示例**：
```python
# 获取指定日期对应的交易日
trade_day = get_trade_day('000001.XSHE', datetime(2023, 12, 31))
```

---

## 技术指标函数

### 1. jqlib.technical_analysis - 技术分析指标

**导入方式**：
```python
from jqlib.technical_analysis import *
```

**常用指标**：

#### MACD - 指数平滑异同移动平均线
```python
from jqlib.technical_analysis import MACD

# 计算MACD
macd_data = MACD(security, check_date, timeperiod=short, timeperiod_long=long, timeperiod_mid=mid)
# 返回: {'DIF': dif, 'DEA': dea, 'MACD': macd}
```

#### KDJ - 随机指标
```python
from jqlib.technical_analysis import KDJ

# 计算KDJ
kdj_data = KDJ(security, check_date, N, M1, M2)
# 返回: {'K': k, 'D': d, 'J': j}
```

#### RSI - 相对强弱指标
```python
from jqlib.technical_analysis import RSI

# 计算RSI
rsi_data = RSI(security, check_date, N1, N2)
# 返回: {'RSI': rsi}
```

#### BOLL - 布林带
```python
from jqlib.technical_analysis import BOLL

# 计算布林带
boll_data = BOLL(security, check_date, N, M)
# 返回: {'upper': upper, 'middle': middle, 'lower': lower}
```

#### ATR - 平均真实波幅
```python
from jqlib.technical_analysis import ATR

# 计算ATR
atr_data = ATR(security, check_date, timeperiod)
# 返回: {'ATR': atr}
```

**使用示例**：
```python
from jqlib.technical_analysis import MACD, KDJ, RSI, BOLL

def initialize(context):
    g.security = '000001.XSHE'
    run_daily(trade, time='9:30')

def trade(context):
    # 获取MACD
    macd = MACD(g.security, context.current_dt, 12, 26, 9)
    dif, dea, macd_hist = macd['DIF'], macd['DEA'], macd['MACD']
    
    # 获取KDJ
    kdj = KDJ(g.security, context.current_dt, 9, 3, 3)
    k, d, j = kdj['K'], kdj['D'], kdj['J']
    
    # 获取RSI
    rsi = RSI(g.security, context.current_dt, 6, 12)
    
    # 获取布林带
    boll = BOLL(g.security, context.current_dt, 20, 2)
    upper, middle, lower = boll['upper'], boll['middle'], boll['lower']
```

---

### 2. jqlib.alpha101 - Alpha101因子

**导入方式**：
```python
from jqlib.alpha101 import *
```

**使用示例**：
```python
from jqlib.alpha101 import alpha_001, alpha_002

# 计算Alpha001因子
alpha001 = alpha_001(security, end_date)

# 计算Alpha002因子
alpha002 = alpha_002(security, end_date)
```

---

### 3. jqlib.alpha191 - Alpha191因子

**导入方式**：
```python
from jqlib.alpha191 import *
```

**使用示例**：
```python
from jqlib.alpha191 import alpha_001, alpha_002

# 计算Alpha191因子
alpha191_001 = alpha_001(security, end_date)
```

---

## 数据处理函数

### 1. neutralize(factor, industry_list=None, date=None)

**功能**：中性化处理，消除行业和市值影响

**参数**：
- `factor`: 因子数据（Series或DataFrame）
- `industry_list`: 行业列表（可选）
- `date`: 日期（可选）

**返回值**：处理后的因子数据

**使用示例**：
```python
from jqlib.factor_analysis import neutralize

# 对因子进行中性化处理
neutralized_factor = neutralize(factor, industry_list=['000001.XSHE'], date='2023-12-31')
```

---

### 2. winsorize(factor, n=3, method='mad')

**功能**：去极值处理

**参数**：
- `factor`: 因子数据
- `n`: 阈值倍数（默认为3）
- `method`: 方法，'mad'（中位数绝对偏差）或 'std'（标准差）

**返回值**：处理后的因子数据

**使用示例**：
```python
from jqlib.factor_analysis import winsorize

# 使用MAD方法去极值
winsorized_factor = winsorize(factor, n=3, method='mad')

# 使用标准差方法去极值
winsorized_factor = winsorize(factor, n=3, method='std')
```

---

### 3. standardlize(factor)

**功能**：标准化处理（z-score）

**参数**：
- `factor`: 因子数据

**返回值**：标准化后的因子数据

**使用示例**：
```python
from jqlib.factor_analysis import standardlize

# 标准化因子
standardized_factor = standardlize(factor)
```

---

## 交易函数

### 1. order(security, amount, style=None, side='long', pindex=0)

**功能**：按股数下单

**参数**：
- `security`: 证券代码
- `amount`: 股数（正数买入，负数卖出）
- `style`: 下单方式，MarketOrder()、LimitOrder()
- `side`: 方向，'long'（做多，默认）、'short'（做空）
- `pindex`: 子账户索引（默认为0）

**返回值**：Order 对象或 None

**使用示例**：
```python
# 买入1000股
order('000001.XSHE', 1000)

# 卖出800股
order('000001.XSHE', -800)

# 使用限价单买入
order('000001.XSHE', 1000, style=LimitOrder(price=10.5))

# 期货做多1手
order('RB2401.XSGE', 1, side='long')
```

---

### 2. order_target(security, amount, style=None, side='long', pindex=0)

**功能**：目标股数下单（调整持仓到目标数量）

**参数**：
- `security`: 证券代码
- `amount`: 目标股数
- `style`: 下单方式
- `side`: 方向
- `pindex`: 子账户索引

**返回值**：Order 对象或 None

**使用示例**：
```python
# 调整持仓到1000股
order_target('000001.XSHE', 1000)

# 清仓
order_target('000001.XSHE', 0)
```

---

### 3. order_value(security, value, style=None, side='long', pindex=0)

**功能**：按金额下单

**参数**：
- `security`: 证券代码
- `value`: 金额（元）
- `style`: 下单方式
- `side`: 方向
- `pindex`: 子账户索引

**返回值**：Order 对象或 None

**使用示例**：
```python
# 全仓买入
order_value('000001.XSHE', context.portfolio.available_cash)

# 按金额买入10000元
order_value('000001.XSHE', 10000)
```

---

### 4. order_target_value(security, value, style=None, side='long', pindex=0)

**功能**：目标价值下单（调整持仓市值到目标金额）

**参数**：
- `security`: 证券代码
- `value`: 目标市值（元）
- `style`: 下单方式
- `side`: 方向
- `pindex`: 子账户索引

**返回值**：Order 对象或 None

**使用示例**：
```python
# 调整持仓市值为10000元
order_target_value('000001.XSHE', 10000)

# 清仓
order_target_value('000001.XSHE', 0)
```

---

### 5. cancel_order(order)

**功能**：撤单

**参数**：
- `order`: Order 对象或订单ID

**使用示例**：
```python
# 获取未完成订单
open_orders = get_open_orders()

# 撤销所有未完成订单
for order in open_orders:
    cancel_order(order)
```

---

### 6. get_open_orders()

**功能**：获取未完成订单

**返回值**：List，Order 对象列表

**使用示例**：
```python
# 获取未完成订单
orders = get_open_orders()

for order in orders:
    log.info(f"未完成订单: {order.security}, 数量: {order.amount}")
```

---

### 7. get_orders()

**功能**：获取订单信息

**返回值**：Dict，key为订单ID，value为Order对象

**使用示例**：
```python
# 获取所有订单
orders = get_orders()

for order_id, order in orders.items():
    log.info(f"订单ID: {order_id}, 证券: {order.security}, 状态: {order.status}")
```

---

### 8. get_trades()

**功能**：获取成交信息

**返回值**：Dict，key为订单ID，value为Trade对象

**使用示例**：
```python
# 获取当日成交记录
trades = get_trades()

for trade in trades.values():
    log.info(f"成交: {trade.security}, 价格: {trade.price}, 数量: {trade.amount}")
```

---

### 9. inout_cash(money, pindex=0)

**功能**：账户出入金

**参数**：
- `money`: 金额（正数入金，负数出金）
- `pindex`: 子账户索引

**使用示例**：
```python
# 入金10000元
inout_cash(10000)

# 出金5000元
inout_cash(-5000)
```

---

### 10. batch_submit_orders(orders)

**功能**：篮子下单

**参数**：
- `orders`: 订单列表

**使用示例**：
```python
# 批量下单
orders = [
    {'security': '000001.XSHE', 'amount': 1000},
    {'security': '000002.XSHE', 'amount': 1000},
]
batch_submit_orders(orders)
```

---

### 11. batch_cancel_orders(orders)

**功能**：篮子撤单

**参数**：
- `orders`: 订单列表

**使用示例**：
```python
# 批量撤单
orders = get_open_orders()
batch_cancel_orders(orders)
```

---

## 对象说明

### 1. g - 全局变量对象

**功能**：用于存储策略运行过程中的全局变量

**使用示例**：
```python
def initialize(context):
    # 定义全局变量
    g.security = '000001.XSHE'
    g.stock_list = []
    g.ma_short = 5
    g.ma_long = 20
    
def handle_data(context, data):
    # 访问全局变量
    security = g.security
    ma_short = g.ma_short
```

**注意事项**：
- g对象在模拟交易重启时会保存（使用pickle序列化）
- g中以'__'开头的变量不会被保存
- g中不能序列化的变量不会被保存
- 序列化后状态大小不能超过30M

---

### 2. Context - 策略信息总览

**主要属性**：

#### context.portfolio - 账户信息
```python
# 总资产
total_value = context.portfolio.total_value

# 可用资金
available_cash = context.portfolio.available_cash

# 总资金
total_cash = context.portfolio.total_cash

# 持仓字典
positions = context.portfolio.positions
```

#### context.current_dt - 当前时间
```python
# 当前时间
current_time = context.current_dt

# 当前日期
current_date = context.current_dt.date()

# 当前小时
current_hour = context.current_dt.hour

# 当前分钟
current_minute = context.current_dt.minute
```

#### context.previous_date - 前一个交易日
```python
# 前一个交易日
prev_date = context.previous_date
```

---

### 3. Portfolio - 总账户信息

**主要属性**：
```python
# 总资产
total_value = context.portfolio.total_value

# 可用资金
available_cash = context.portfolio.available_cash

# 总资金
total_cash = context.portfolio.total_cash

# 持仓市值
positions_value = context.portfolio.positions_value

# 起始资金
starting_cash = context.portfolio.starting_cash

# 持仓字典
positions = context.portfolio.positions
```

---

### 4. Position - 持仓标的信息

**主要属性**：
```python
# 遍历持仓
for security, position in context.portfolio.positions.items():
    # 持仓数量
    total_amount = position.total_amount
    
    # 可卖出数量（考虑T+1）
    closeable_amount = position.closeable_amount
    
    # 持仓市值
    value = position.value
    
    # 持仓成本
    avg_cost = position.avg_cost
    
    # 盈亏
    profit = position.profit
```

**使用示例**：
```python
# 检查是否持有某只股票
if security in context.portfolio.positions:
    position = context.portfolio.positions[security]
    # 获取可卖出数量
    closeable_amount = position.closeable_amount
```

---

### 5. Order - 订单对象

**主要属性**：
```python
order = order('000001.XSHE', 1000)

if order is not None:
    # 订单ID
    order_id = order.order_id
    
    # 证券代码
    security = order.security
    
    # 订单数量
    amount = order.amount
    
    # 已成交数量
    filled = order.filled
    
    # 成交价格
    price = order.price
    
    # 交易费用
    commission = order.commission
    
    # 是否买单
    is_buy = order.is_buy
    
    # 订单状态：0=已提交，1=已成交，2=部分成交，3=已撤销
    status = order.status
```

---

### 6. Trade - 交易对象

**主要属性**：
```python
trades = get_trades()
for trade in trades.values():
    # 订单ID
    order_id = trade.order_id
    
    # 证券代码
    security = trade.security
    
    # 成交价格
    price = trade.price
    
    # 成交数量
    amount = trade.amount
    
    # 交易费用
    commission = trade.commission
    
    # 成交时间
    time = trade.time
```

---

## 其他函数

### 1. record(**kwargs) ♠ - 画图函数

**功能**：记录自定义指标，在回测结果图表中显示

**参数**：关键字参数，指标名=值

**使用示例**：
```python
# 记录价格和均线
record(stock_price=current_price, MA5=MA5, MA10=MA10)

# 记录收益率
record(daily_return=context.portfolio.returns)

# 记录持仓数量
record(position_count=len(context.portfolio.positions))
```

---

### 2. log.info/debug/warn/error(message) - 日志函数

**功能**：输出日志信息

**使用示例**：
```python
# 信息日志
log.info("买入股票: 000001.XSHE")

# 调试日志
log.debug(f"当前价格: {current_price}")

# 警告日志
log.warn("资金不足")

# 错误日志
log.error("下单失败")
```

**设置日志级别**：
```python
# 设置订单日志只报错
log.set_level('order', 'error')

# 设置系统日志只报错
log.set_level('system', 'error')

# 设置策略日志显示debug信息
log.set_level('strategy', 'debug')
```

---

### 3. write_file(filename, content)

**功能**：将回测或模拟交易数据写入到投资研究文件中

**参数**：
- `filename`: 文件名
- `content`: 文件内容

**使用示例**：
```python
# 写入文件
write_file('test.txt', 'Hello World')

# 写入JSON数据
import json
write_file('data.json', json.dumps(data))
```

---

### 4. read_file(filename)

**功能**：在回测或模拟交易中读取研究中的文件

**参数**：
- `filename`: 文件名

**返回值**：文件内容

**使用示例**：
```python
# 读取文件
content = read_file('test.txt')

# 读取JSON数据
import json
data = json.loads(read_file('data.json'))
```

---

### 5. normalize_code(code)

**功能**：股票代码格式转换

**参数**：
- `code`: 股票代码

**返回值**：标准格式的股票代码

**使用示例**：
```python
# 转换股票代码
code = normalize_code('000001')  # 返回 '000001.XSHE'
code = normalize_code('600000')  # 返回 '600000.XSHG'
```

---

## 注意事项

### 1. 带有"♠"标识的API

以下API是回测环境/模拟专用的，**不能在研究模块中调用**：

- `get_current_tick()` - 获取最新的tick数据
- `get_current_data()` - 获取当前时间数据
- `record()` - 画图函数
- `send_message()` - 发送自定义消息
- `enable_profile()` - 性能分析
- 策略程序架构中的函数（如 initialize, handle_data 等）

### 2. jqdata模块

整个 `jqdata` 模块在研究环境与回测环境下都可以使用。

### 3. 交易成本

- **券商手续费**：双边收费，默认万分之三（0.03%），最低5元
- **印花税**：卖方单边征收，默认千分之一（0.1%）

### 4. 滑点

- 默认使用固定滑点0.2%
- 可通过 `set_slippage()` 自定义

### 5. 未来数据

- 回测中应避免使用未来数据
- 建议开启 `set_option('avoid_future_data', True)`

### 6. 订单限制

- 回测和模拟中，每日下单的最大数量为10000笔
- 所有未完成订单在每个交易日结束时自动撤销

### 7. 时间格式

- 所有时间都是北京时间(UTC+8)
- 格式为 `datetime.datetime` 对象
- 日期字符串格式为 'YYYY-MM-DD'

### 8. 股票代码格式

- 深交所：`000001.XSHE`
- 上交所：`600000.XSHG`

### 9. 数据更新频率

- 当日回测数据会在收盘后通过多数据源进行校验
- 在T+1（第二天）的00:01更新

### 10. K线数据说明

- 所有行情K线数据为后对齐
- 标识K线的时间为数据的结束时间
- 在一分钟K线上，没有09:30，从09:31开始，有15:00的K线，共计240根

---

## 附录：常用股票代码

### 主要指数
- `000300.XSHG` - 沪深300指数
- `000905.XSHG` - 中证500指数
- `000016.XSHG` - 上证50指数
- `399006.XSHE` - 创业板指
- `000001.XSHG` - 上证指数

### 行业指数
- `399101.XSHE` - 中小板综指
- `399001.XSHE` - 深证成指

### 常用ETF
- `510300.XSHG` - 沪深300ETF
- `510500.XSHG` - 中证500ETF
- `159915.XSHE` - 创业板ETF
- `510050.XSHG` - 上证50ETF
- `511880.XSHG` - 银华日利（货币基金）

---

## 常见问题

### Q1: 如何获取多个股票的数据？

A: 使用 `get_price()` 或 `history()` 函数，传入股票代码列表：
```python
# 获取多只股票的数据
df = get_price(['000001.XSHE', '000002.XSHE'], count=30)
```

### Q2: 如何计算移动平均线？

A: 使用 Pandas 的 rolling() 方法：
```python
close_data = attribute_history(security, 20, '1d', ['close'])
MA5 = close_data['close'].rolling(5).mean().iloc[-1]
MA10 = close_data['close'].rolling(10).mean().iloc[-1]
MA20 = close_data['close'].rolling(20).mean().iloc[-1]
```

### Q3: 如何过滤ST股和停牌股？

A: 使用 `get_current_data()` 检查：
```python
current_data = get_current_data()
valid_stocks = []
for stock in stock_list:
    if not current_data[stock].is_st and not current_data[stock].paused:
        valid_stocks.append(stock)
```

### Q4: 如何获取涨停板和跌停板价格？

A: 使用以下方法：
```python
def get_limit_price(code, date):
    yesterday_price = get_price(code, end_date=date, count=1, frequency='daily', fields=['close']).iloc[0, 0]
    
    # 判断涨跌停板限制
    if code.startswith('68'):  # 科创板
        rate = 0.20
    elif code.startswith('3'):  # 创业板
        rate = 0.20
    else:
        rate = 0.10
    
    high_limit = yesterday_price * (1 + rate)
    low_limit = yesterday_price * (1 - rate)
    
    return high_limit, low_limit
```

### Q5: 如何计算收益率？

A:
```python
# 日收益率
close_data = attribute_history(security, 5, '1d', ['close'])
daily_returns = close_data['close'].pct_change().dropna()

# 累计收益率
cumulative_returns = (1 + daily_returns).cumprod() - 1

# 对数收益率
log_returns = np.log(close_data['close'] / close_data['close'].shift(1)).dropna()
```

---

## 参考资料

- 聚宽官方文档: https://www.joinquant.com/help/api
- 聚宽社区: https://www.joinquant.com/community
- JQData本地数据: https://www.joinquant.com/help/api/help#name:Stock

---

## 版本说明

- 文档版本: v1.0
- 最后更新: 2026-01-31
- 适用平台: 聚宽JoinQuant量化平台
- 适用Python版本: Python 3.6+

---

**声明**：本文档基于聚宽JoinQuant平台官方API文档整理，仅供学习参考使用。实际使用中请以聚宽官方最新文档为准。