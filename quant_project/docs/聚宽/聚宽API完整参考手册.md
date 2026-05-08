# -*- coding: utf-8 -*-
# 聚宽JoinQuant API完整参考手册

> 本文档基于聚宽平台实际代码使用情况整理，包含所有常用API函数的详细说明、参数、返回值和示例代码。
>
> 文档更新时间：2026-01-28
> 数据来源：JoinQuantEgs文件夹中的实际策略代码

---

## 目录

- [1. 策略初始化与配置](#1-策略初始化与配置)
  - [1.1 initialize() - 策略初始化函数](#11-initialize---策略初始化函数)
  - [1.2 set_benchmark() - 设置基准指数](#12-set_benchmark---设置基准指数)
  - [1.3 set_option() - 设置策略选项](#13-set_option---设置策略选项)
  - [1.4 set_order_cost() - 设置交易成本](#14-set_order_cost---设置交易成本)
  - [1.5 OrderCost - 交易成本类](#15-ordercost---交易成本类)
  - [1.6 set_slippage() - 设置滑点](#16-set_slippage---设置滑点)
  - [1.7 FixedSlippage - 固定滑点类](#17-fixedslippage---固定滑点类)
- [2. 数据获取API](#2-数据获取api)
- [3. 交易执行API](#3-交易执行api)
- [4. 查询对象API](#4-查询对象api)
- [5. 工具函数API](#5-工具函数api)
- [6. 技术分析API](#6-技术分析api)
- [7. 市场数据API](#7-市场数据api)
- [8. 财务数据API](#8-财务数据api)
- [9. 因子数据API](#9-因子数据api)
- [10. 高级功能API](#10-高级功能api)
- [附录A：快速索引](#附录a快速索引)
- [附录B：常见问题](#附录b常见问题)

---

## 1. 策略初始化与配置

### 1.1 initialize() - 策略初始化函数

**函数签名**：
```python
def initialize(context):
    pass
```

**说明**：
- 策略回测开始时调用一次
- 用于设置策略参数、定时任务、交易成本等

**参数**：
- `context`: 策略上下文对象，包含账户信息、时间信息等

**示例**：
```python
def initialize(context):
    # 设置基准指数
    set_benchmark('000300.XSHG')
    
    # 设置交易成本
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.0003,
        close_commission=0.0003,
        min_commission=5
    ), type='stock')
    
    # 设置定时任务
    run_daily(market_open, time='every_bar')
```

---

### 1.2 set_benchmark() - 设置基准指数

**函数签名**：
```python
set_benchmark(security)
```

**说明**：
- 设置策略回测的基准指数
- 用于衡量策略表现

**参数**：
- `security` (str): 基准指数代码，如 '000300.XSHG'（沪深300）

**示例**：
```python
set_benchmark('000300.XSHG')  # 沪深300指数
set_benchmark('000001.XSHE')  # 深证成指
```

---

### 1.3 set_option() - 设置策略选项

**函数签名**：
```python
set_option(key, value)
```

**说明**：
- 设置策略的全局选项

**常用选项**：
- `'use_real_price'`: 使用真实价格（True/False）
- `'avoid_future_data'`: 避免未来数据（True/False）

**示例**：
```python
set_option('use_real_price', True)
set_option('avoid_future_data', True)
```

---

### 1.4 set_order_cost() - 设置交易成本

**函数签名**：
```python
set_order_cost(order_cost, type='stock')
```

**说明**：
- 设置交易手续费和滑点

**参数**：
- `order_cost` (OrderCost): 交易成本对象
- `type` (str): 证券类型，'stock'（股票）、'fund'（基金）、'futures'（期货）

**OrderCost 参数**：
- `open_tax`: 买入时的印花税（股票买入无印花税，设为0）
- `close_tax`: 卖出时的印花税（股票卖出0.1%，即0.001）
- `open_commission`: 买入时的佣金率（0.03%，即0.0003）
- `close_commission`: 卖出时的佣金率（0.03%，即0.0003）
- `close_today_commission`: 当日平仓的佣金率（股票无此费用，设为0）
- `min_commission`: 最低佣金（5元）

**示例**：
```python
# 股票交易成本设置
set_order_cost(OrderCost(
    open_tax=0,              # 买入无印花税
    close_tax=0.001,         # 卖出印花税0.1%
    open_commission=0.0003,  # 买入佣金0.03%
    close_commission=0.0003, # 卖出佣金0.03%
    close_today_commission=0,
    min_commission=5         # 最低佣金5元
), type='stock')
```

---

### 1.5 OrderCost - 交易成本类

**类定义**：
```python
OrderCost(open_tax=0, close_tax=0, open_commission=0, close_commission=0, 
          close_today_commission=0, min_commission=0)
```

**示例**：
```python
from jqdata import *

# 创建交易成本对象
cost = OrderCost(
    open_tax=0,
    close_tax=0.001,
    open_commission=0.0003,
    close_commission=0.0003,
    min_commission=5
)
set_order_cost(cost, type='stock')
```

---

### 1.6 set_slippage() - 设置滑点

**函数签名**：
```python
set_slippage(slippage)
```

**说明**：
- 设置交易滑点
- 滑点是指实际成交价格与期望价格之间的差异
- 用于模拟真实交易中的价格波动

**参数**：
- `slippage` (Slippage): 滑点对象

**常用滑点类型**：
- `FixedSlippage`: 固定滑点
- `PriceRelatedSlippage`: 价格相关滑点
- `UpDownPercentSlippage`: 上下浮动百分比滑点

**示例**：
```python
# 固定滑点（0.1%）
set_slippage(FixedSlippage(0.001))

# 价格相关滑点
set_slippage(PriceRelatedSlippage(0.002))
```

**实际应用示例**（来自安全摸狗策略.py）：
```python
# 设置滑点
set_slippage(FixedSlippage(0.001))
```

---

### 1.7 FixedSlippage - 固定滑点类

**类定义**：
```python
FixedSlippage(value)
```

**说明**：
- 固定滑点，按固定比例调整成交价格
- 买入时：成交价 = 期望价 * (1 + value)
- 卖出时：成交价 = 期望价 * (1 - value)

**参数**：
- `value` (float): 滑点值（如 0.001 表示0.1%）

**示例**：
```python
# 固定滑点0.1%
set_slippage(FixedSlippage(0.001))

# 固定滑点0.2%
set_slippage(FixedSlippage(0.002))
```

**其他滑点类型**：

**PriceRelatedSlippage** - 价格相关滑点：
```python
PriceRelatedSlippage(value)
# value: 滑点值，如 0.002
```

**UpDownPercentSlippage** - 上下浮动百分比滑点：
```python
UpDownPercentSlippage(up_percent, down_percent)
# up_percent: 上涨时滑点
# down_percent: 下跌时滑点
```

---

## 2. 数据获取API

### 2.1 attribute_history() - 获取历史属性数据

**函数签名**：
```python
attribute_history(security, count, unit, fields, df=True, skip_paused=True, fq='pre')
```

**说明**：
- 获取指定证券的历史数据
- 返回DataFrame或字典格式

**参数**：
- `security` (str/list): 证券代码或证券代码列表
- `count` (int): 获取的数据条数
- `unit` (str): 时间单位，'1d'（日线）、'1m'（分钟线）、'1w'（周线）、'1M'（月线）
- `fields` (list): 要获取的字段列表，如 ['open', 'close', 'high', 'low', 'volume']
- `df` (bool): 是否返回DataFrame格式（True）或字典格式（False）
- `skip_paused` (bool): 是否跳过停牌日
- `fq` (str): 复权类型，'pre'（前复权）、'post'（后复权）、'none'（不复权）

**返回值**：
- `df=True`: 返回DataFrame，索引为日期，列为字段
- `df=False`: 返回字典，键为字段名，值为数组

**可用字段**：
- `open`: 开盘价
- `close`: 收盘价
- `high`: 最高价
- `low`: 最低价
- `volume`: 成交量（股）
- `money`: 成交额（元）
- `factor`: 复权因子

**示例**：
```python
# 获取单个股票的收盘价数据
close_data = attribute_history('000001.XSHE', 20, '1d', ['close'])
print(close_data['close'][-1])  # 最新收盘价

# 获取多个股票的开高低收数据
ohlc_data = attribute_history(['000001.XSHE', '600000.XSHG'], 10, '1d', 
                               ['open', 'high', 'low', 'close'])

# 获取成交量数据
volume_data = attribute_history('000001.XSHE', 30, '1d', ['volume'])

# 获取分钟线数据
minute_data = attribute_history('000001.XSHE', 60, '1m', ['close', 'volume'])
```

**实际应用示例**（来自debug.py）：
```python
# 获取过去5天的收盘价数据
close_data = attribute_history(security=g.security, count=5, unit='1d', fields=['close'])

# 计算5日移动平均线
MA5 = close_data['close'].mean()

# 获取当前价格
current_price = close_data['close'][-1]
```

---

### 2.2 get_price() - 获取价格数据

**函数签名**：
```python
get_price(security, count=None, unit='1d', fields=None, reference_date=None, 
          fq_ref_date=None, skip_paused=True, fq='pre')
```

**说明**：
- 获取证券的价格数据
- 支持多证券、多字段、多频率

**参数**：
- `security` (str/list): 证券代码或代码列表
- `count` (int): 获取的数据条数（默认为None，获取所有）
- `unit` (str): 时间单位，'1d'、'1m'、'1w'、'1M'
- `fields` (list): 字段列表，如 ['open', 'close', 'high', 'low', 'volume']
- `reference_date` (str/datetime): 参考日期（获取该日期之前的数据）
- `fq_ref_date` (str/datetime): 复权参考日期
- `skip_paused` (bool): 是否跳过停牌日
- `fq` (str): 复权类型，'pre'、'post'、'none'

**返回值**：
- DataFrame，索引为日期，列为证券代码和字段的组合

**示例**：
```python
# 获取单只股票的收盘价
price_data = get_price('000001.XSHE', count=20, unit='1d', fields=['close'])

# 获取多只股票的开高低收
price_data = get_price(['000001.XSHE', '600000.XSHG'], count=10, 
                       unit='1d', fields=['open', 'high', 'low', 'close'])

# 获取指定日期之前的数据
price_data = get_price('000001.XSHE', count=30, unit='1d', 
                       fields=['close'], reference_date='2024-01-01')
```

---

### 2.3 get_current_data() - 获取当前数据

**函数签名**：
```python
get_current_data()
```

**说明**：
- 获取当前时刻的快照数据
- 包含当前价格、涨停价、跌停价等

**返回值**：
- 字典，键为证券代码，值为当前数据对象

**可用属性**：
- `price`: 当前价格
- `high_limit`: 涨停价
- `low_limit`: 跌停价
- `last_price`: 最后一笔成交价
- `time`: 时间戳

**示例**：
```python
# 获取当前数据
current_data = get_current_data()
stock_data = current_data['000001.XSHE']

print(f"当前价格: {stock_data.price}")
print(f"涨停价: {stock_data.high_limit}")
print(f"跌停价: {stock_data.low_limit}")
```

---

### 2.4 get_trade_days() - 获取交易日

**函数签名**：
```python
get_trade_days(start_date=None, end_date=None, count=None)
```

**说明**：
- 获取指定日期范围内的交易日列表

**参数**：
- `start_date` (str/datetime): 开始日期
- `end_date` (str/datetime): 结束日期
- `count` (int): 获取的交易日的数量

**返回值**：
- DatetimeIndex，包含所有交易日

**示例**：
```python
# 获取最近5个交易日
trade_days = get_trade_days(count=5)

# 获取指定日期范围内的交易日
trade_days = get_trade_days(start_date='2024-01-01', end_date='2024-01-31')

# 获取指定日期之前的交易日
trade_days = get_trade_days(end_date='2024-01-15', count=10)
```

**实际应用示例**（来自ai_debug.py）：
```python
# 获取北向资金数据
end_date = context.previous_date
trade_days = get_trade_days(end_date=end_date, count=5)

# 获取北向资金流入
northbound_flow = 0
for i in range(min(3, len(trade_days))):
    date_str = trade_days[-i-1].strftime('%Y-%m-%d')
    money_flow = get_money_flow(['000001.XSHG', '399001.XSHE'], 
                              start_date=date_str, end_date=date_str)
```

---

### 2.5 get_all_securities() - 获取所有证券信息

**函数签名**：
```python
get_all_securities(types=[], date=None)
```

**说明**：
- 获取所有证券的基础信息

**参数**：
- `types` (list): 证券类型列表，如 ['stock', 'fund', 'index', 'futures']
- `date` (str/datetime): 指定日期（获取该日期的证券列表）

**返回值**：
- DataFrame，索引为证券代码，包含证券信息

**可用类型**：
- `'stock'`: 股票
- `'fund'`: 基金
- `'index'`: 指数
- `'futures'`: 期货
- `'bond'`: 债券
- `'option'`: 期权

**示例**：
```python
# 获取所有股票
all_stocks = get_all_securities(types=['stock'])
stock_list = all_stocks.index.tolist()

# 获取指定日期的股票
stocks_2024 = get_all_securities(types=['stock'], date='2024-01-01')

# 获取所有基金
all_funds = get_all_securities(types=['fund'])

# 获取所有证券
all_securities = get_all_securities()
```

**实际应用示例**（来自五合一打板综合强化.py）：
```python
# 获取所有股票
date = context.previous_date.strftime('%Y-%m-%d')
all_stocks = get_all_securities('stock', date).index.tolist()

# 过滤A股股票（60、00、30开头）
all_stocks = [s for s in all_stocks if s[:2] in (('60', '00', '30'))]
```

---

### 2.6 get_security_info() - 获取证券详细信息

**函数签名**：
```python
get_security_info(security)
```

**说明**：
- 获取单个证券的详细信息

**参数**：
- `security` (str): 证券代码

**返回值**：
- SecurityInfo对象，包含证券的详细信息

**可用属性**：
- `code`: 证券代码
- `display_name`: 显示名称
- `name`: 名称
- `start_date`: 上市日期
- `end_date`: 退市日期
- `type`: 证券类型
- `parent`: 母公司
- `concepts`: 所属概念列表

**示例**：
```python
# 获取股票信息
stock_info = get_security_info('000001.XSHE')
print(f"股票名称: {stock_info.display_name}")
print(f"上市日期: {stock_info.start_date}")
print(f"所属概念: {stock_info.concepts}")
```

**实际应用示例**（来自五合一打板综合强化.py）：
```python
# 获取股票所属概念
stock_info = get_security_info(stock)
if not stock_info or not stock_info.concepts:
    log.info(f"股票 {stock} 无所属概念")
    return 0

# 从概念字典中提取'name'字段
stock_concepts = [concept['name'] for concept in stock_info.concepts]
```

---

### 2.7 get_index_stocks() - 获取指数成分股

**函数签名**：
```python
get_index_stocks(index_code, date=None)
```

**说明**：
- 获取指定指数的成分股列表

**参数**：
- `index_code` (str): 指数代码，如 '000300.XSHG'（沪深300）
- `date` (str/datetime): 指定日期（获取该日期的成分股）

**返回值**：
- list，包含成分股代码

**常用指数**：
- `'000001.XSHG'`: 上证综指
- `'000300.XSHG'`: 沪深300
- `'399001.XSHE'`: 深证成指
- `'399006.XSHE'`: 创业板指
- `'000016.XSHG'`: 上证50
- `'000905.XSHG'`: 中证500

**示例**：
```python
# 获取沪深300成分股
hs300_stocks = get_index_stocks('000300.XSHG')

# 获取指定日期的成分股
hs300_stocks_2024 = get_index_stocks('000300.XSHG', date='2024-01-01')

# 获取创业板指成分股
cyb_stocks = get_index_stocks('399006.XSHE')
```

---

### 2.8 get_industry_stocks() - 获取行业成分股

**函数签名**：
```python
get_industry_stocks(industry_code, date=None)
```

**说明**：
- 获取指定行业的成分股列表

**参数**：
- `industry_code` (str): 行业代码
- `date` (str/datetime): 指定日期

**返回值**：
- list，包含成分股代码

**示例**：
```python
# 获取银行行业成分股
bank_stocks = get_industry_stocks('sw1_bank')

# 获取指定日期的行业成分股
bank_stocks_2024 = get_industry_stocks('sw1_bank', date='2024-01-01')
```

---

### 2.9 get_concept_stocks() - 获取概念成分股

**函数签名**：
```python
get_concept_stocks(concept_code, date=None)
```

**说明**：
- 获取指定概念的成分股列表

**参数**：
- `concept_code` (str): 概念代码
- `date` (str/datetime): 指定日期

**返回值**：
- list，包含成分股代码

**示例**：
```python
# 获取人工智能概念成分股
ai_stocks = get_concept_stocks('GN021')

# 获取指定日期的概念成分股
ai_stocks_2024 = get_concept_stocks('GN021', date='2024-01-01')
```

---

### 2.10 get_billboard_list() - 获取龙虎榜数据

**函数签名**：
```python
get_billboard_list(stock_list=None, end_date=None, count=1)
```

**说明**：
- 获取龙虎榜数据

**参数**：
- `stock_list` (list): 股票代码列表（None表示所有股票）
- `end_date` (str/datetime): 结束日期
- `count` (int): 获取的天数

**返回值**：
- DataFrame，包含龙虎榜数据

**示例**：
```python
# 获取指定股票的龙虎榜数据
billboard = get_billboard_list(stock_list=['000001.XSHE'], end_date='2024-01-15', count=5)

# 获取所有股票的龙虎榜数据
all_billboard = get_billboard_list(end_date='2024-01-15', count=1)
```

---

### 2.11 get_money_flow() - 获取资金流向数据

**函数签名**：
```python
get_money_flow(security_list, start_date=None, end_date=None, fields=None)
```

**说明**：
- 获取资金流向数据

**参数**：
- `security_list` (list): 证券代码列表
- `start_date` (str/datetime): 开始日期
- `end_date` (str/datetime): 结束日期
- `fields` (list): 字段列表

**返回值**：
- DataFrame，包含资金流向数据

**示例**：
```python
# 获取资金流向数据
money_flow = get_money_flow(['000001.XSHG', '399001.XSHE'], 
                           start_date='2024-01-01', 
                           end_date='2024-01-15')
```

**实际应用示例**（来自ai_debug.py）：
```python
# 获取北向资金数据
money_flow = get_money_flow(['000001.XSHG', '399001.XSHE'], 
                           start_date=date_str, end_date=date_str)
if not money_flow.empty:
    northbound_flow += money_flow['net_amount_main'].sum()
```

---

### 2.12 get_mtss() - 获取融资融券数据

**函数签名**：
```python
get_mtss(security_list=None, start_date=None, end_date=None, stat_date=None)
```

**说明**：
- 获取融资融券数据

**参数**：
- `security_list` (list): 证券代码列表
- `start_date` (str/datetime): 开始日期
- `end_date` (str/datetime): 结束日期
- `stat_date` (str/datetime): 统计日期

**返回值**：
- DataFrame，包含融资融券数据

**示例**：
```python
# 获取融资融券数据
margin_data = get_mtss(security_list=['000001.XSHE'], 
                      start_date='2024-01-01', 
                      end_date='2024-01-15')
```

**实际应用示例**（来自ai_debug.py）：
```python
# 获取融资融券数据（盘后才能获取）
date_str = end_date.strftime('%Y-%m-%d')
margin_data = get_mtss(date_str, date_str)

if not margin_data.empty:
    margin_buy = margin_data['fin_buy'].sum()  # 融资买入额
    margin_sell = margin_data['fin_ref'].sum()  # 融券卖出额
    margin_ratio = margin_buy / max(margin_sell, 1)
```

---

## 3. 交易执行API

### 3.1 order() - 按数量下单

**函数签名**：
```python
order(security, amount, style=None, side='long', pindex=None)
```

**说明**：
- 按指定数量买入或卖出股票

**参数**：
- `security` (str): 证券代码
- `amount` (int): 交易数量（正数买入，负数卖出）
- `style` (OrderStyle): 订单类型，如 MarketOrder、LimitOrder
- `side` (str): 交易方向，'long'（做多）、'short'（做空）
- `pindex` (int): 价格类型索引

**返回值**：
- Order对象，包含订单信息

**示例**：
```python
# 买入100股
order('000001.XSHE', 100)

# 卖出100股
order('000001.XSHE', -100)

# 使用限价单买入
from jqlib.technical_analysis import *
order('000001.XSHE', 100, style=LimitOrder(10.5))
```

---

### 3.2 order_value() - 按金额下单

**函数签名**：
```python
order_value(security, value, style=None, side='long', pindex=None)
```

**说明**：
- 按指定金额买入或卖出股票

**参数**：
- `security` (str): 证券代码
- `value` (float): 交易金额（正数买入，负数卖出）
- `style` (OrderStyle): 订单类型
- `side` (str): 交易方向
- `pindex` (int): 价格类型索引

**返回值**：
- Order对象

**示例**：
```python
# 使用10000元买入
order_value('000001.XSHE', 10000)

# 使用所有可用资金买入
order_value('000001.XSHE', context.portfolio.available_cash)
```

**实际应用示例**（来自debug.py）：
```python
# 使用全部可用资金买入股票
order_value(security, cash)
```

---

### 3.3 order_target() - 目标数量下单

**函数签名**：
```python
order_target(security, amount, style=None, side='long', pindex=None)
```

**说明**：
- 调整持仓到目标数量

**参数**：
- `security` (str): 证券代码
- `amount` (int): 目标持仓数量
- `style` (OrderStyle): 订单类型
- `side` (str): 交易方向
- `pindex` (int): 价格类型索引

**返回值**：
- Order对象

**示例**：
```python
# 调整持仓到100股
order_target('000001.XSHE', 100)

# 清仓
order_target('000001.XSHE', 0)
```

---

### 3.4 order_target_value() - 目标金额下单

**函数签名**：
```python
order_target_value(security, value, style=None, side='long', pindex=None)
```

**说明**：
- 调整持仓到目标金额

**参数**：
- `security` (str): 证券代码
- `value` (float): 目标持仓金额
- `style` (OrderStyle): 订单类型
- `side` (str): 交易方向
- `pindex` (int): 价格类型索引

**返回值**：
- Order对象

**示例**：
```python
# 调整持仓到10000元
order_target_value('000001.XSHE', 10000)

# 清仓
order_target_value('000001.XSHE', 0)
```

**实际应用示例**（来自debug.py）：
```python
# 将持仓价值设置为0（即全部卖出）
order_target_value(security, 0)
```

---

### 3.5 order_target_percent() - 目标比例下单

**函数签名**：
```python
order_target_percent(security, percent, style=None, side='long', pindex=None)
```

**说明**：
- 调整持仓到目标比例

**参数**：
- `security` (str): 证券代码
- `percent` (float): 目标持仓比例（0-1之间）
- `style` (OrderStyle): 订单类型
- `side` (str): 交易方向
- `pindex` (int): 价格类型索引

**返回值**：
- Order对象

**示例**：
```python
# 调整持仓到总资产的10%
order_target_percent('000001.XSHE', 0.1)

# 清仓
order_target_percent('000001.XSHE', 0)
```

---

## 4. 查询对象API

### 4.1 query() - 创建查询对象

**函数签名**：
```python
query(*tables)
```

**说明**：
- 创建查询对象，用于查询基本面数据

**参数**：
- `*tables`: 表对象或字段

**返回值**：
- Query对象

**示例**：
```python
# 查询估值数据
q = query(valuation.code, valuation.market_cap, valuation.pe_ratio)

# 查询指标数据
q = query(indicator.code, indicator.roe, indicator.eps)

# 查询收入数据
q = query(income.code, income.total_revenue, income.net_profit)
```

---

### 4.2 valuation - 估值数据表

**说明**：
- 股票估值指标数据

**常用字段**：
- `code`: 股票代码
- `day`: 日期
- `market_cap`: 市值
- `circulating_market_cap`: 流通市值
- `pe_ratio`: 市盈率
- `pb_ratio`: 市净率
- `ps_ratio`: 市销率
- `pcf_ratio`: 市现率
- `turnover_ratio`: 换手率

**示例**：
```python
# 查询估值数据
q = query(
    valuation.code,
    valuation.market_cap,
    valuation.pe_ratio,
    valuation.pb_ratio
).filter(
    valuation.code.in_(stock_list),
    valuation.pe_ratio > 5,
    valuation.pe_ratio < 200
).order_by(valuation.market_cap.desc())

df_valuation = get_fundamentals(q, date='2024-01-01')
```

**实际应用示例**（来自多因子策略聚宽因子库.py）：
```python
# 查询估值数据
q = query(
    valuation.code,
    valuation.day,
    valuation.pe_ratio,
    valuation.pb_ratio,
    valuation.market_cap
).filter(
    valuation.code.in_(stock_list),
    valuation.pe_ratio > 5,
    valuation.pe_ratio < 200
).order_by(valuation.market_cap.desc())

df_valuation = get_fundamentals(q, date=s_previous_date).set_index('code')
```

---

### 4.3 indicator - 财务指标表

**说明**：
- 财务指标数据

**常用字段**：
- `code`: 股票代码
- `pubDate`: 发布日期
- `statDate`: 统计日期
- `eps`: 每股收益
- `roe`: 净资产收益率
- `roa`: 总资产收益率
- `net_profit_margin`: 净利率
- `gross_profit_margin`: 毛利率
- `ocf_to_revenue`: 经营现金流/营业收入
- `inc_operation_profit_year_on_year`: 营业利润同比增长率

**示例**：
```python
# 查询财务指标
q = query(
    indicator.code,
    indicator.eps,
    indicator.roe,
    indicator.roa,
    indicator.net_profit_margin,
    indicator.gross_profit_margin,
    indicator.ocf_to_revenue,
    indicator.inc_operation_profit_year_on_year
).filter(
    indicator.code.in_(stock_list),
    indicator.ocf_to_revenue > 0
)

df_finance = get_fundamentals(q)
```

**实际应用示例**（来自多因子策略聚宽因子库.py）：
```python
# 获取财务数据
q = query(
    indicator.code,
    indicator.pubDate,
    indicator.statDate,
    indicator.eps,
    indicator.roe,
    indicator.roa,
    indicator.net_profit_margin,
    indicator.gross_profit_margin,
    indicator.ocf_to_revenue,
    indicator.inc_operation_profit_year_on_year
).filter(
    indicator.code.in_(stock_list),
    indicator.ocf_to_revenue > 0
)

df_finance = get_fundamentals(q).set_index('code')
```

---

### 4.4 income - 利润表

**说明**：
- 利润表数据

**常用字段**：
- `code`: 股票代码
- `pubDate`: 发布日期
- `statDate`: 统计日期
- `total_revenue`: 营业总收入
- `operating_revenue`: 营业收入
- `operating_profit`: 营业利润
- `total_profit`: 利润总额
- `net_profit`: 净利润

**示例**：
```python
# 查询利润表数据
q = query(
    income.code,
    income.total_revenue,
    income.operating_revenue,
    income.net_profit
).filter(
    income.code.in_(stock_list)
)

df_income = get_fundamentals(q)
```

---

### 4.5 balance - 资产负债表

**说明**：
- 资产负债表数据

**常用字段**：
- `code`: 股票代码
- `pubDate`: 发布日期
- `statDate`: 统计日期
- `total_assets`: 总资产
- `total_liab`: 总负债
- `equities_parent_company_owner`: 归属母公司所有者权益

**示例**：
```python
# 查询资产负债表数据
q = query(
    balance.code,
    balance.total_assets,
    balance.total_liab,
    balance.equities_parent_company_owner
).filter(
    balance.code.in_(stock_list)
)

df_balance = get_fundamentals(q)
```

---

### 4.6 cash_flow - 现金流量表

**说明**：
- 现金流量表数据

**常用字段**：
- `code`: 股票代码
- `pubDate`: 发布日期
- `statDate`: 统计日期
- `net_cash_flows_oper_act`: 经营活动现金流量净额
- `net_cash_flows_inv_act`: 投资活动现金流量净额
- `net_cash_flows_fin_act`: 筹资活动现金流量净额

**示例**：
```python
# 查询现金流量表数据
q = query(
    cash_flow.code,
    cash_flow.net_cash_flows_oper_act,
    cash_flow.net_cash_flows_inv_act,
    cash_flow.net_cash_flows_fin_act
).filter(
    cash_flow.code.in_(stock_list)
)

df_cash_flow = get_fundamentals(q)
```

---

### 4.7 finance.STK_LIST - 股票列表表

**说明**：
- 股票上市信息

**常用字段**：
- `code`: 股票代码
- `start_date`: 上市日期
- `end_date`: 退市日期
- `state`: 状态（正常上市、暂停上市、终止上市）

**示例**：
```python
# 查询上市时间超过一年的股票
q = query(
    finance.STK_LIST.code,
    finance.STK_LIST.start_date,
    finance.STK_LIST.state
).filter(
    finance.STK_LIST.code.in_(stock_list),
    finance.STK_LIST.start_date < '2023-01-01',
    finance.STK_LIST.state == '正常上市'
).order_by(finance.STK_LIST.start_date.asc())

df_LIST = finance.run_query(q).set_index('code')
```

**实际应用示例**（来自多因子策略聚宽因子库.py）：
```python
# 选出上市时间超过一年的股票
q = query(
    finance.STK_LIST.code,
    finance.STK_LIST.start_date,
    finance.STK_LIST.state
).filter(
    finance.STK_LIST.code.in_(stock_list),
    finance.STK_LIST.start_date < s_omb,
    finance.STK_LIST.state == '正常上市'
).order_by(finance.STK_LIST.start_date.asc())

df_LIST = finance.run_query(q).set_index('code')
```

---

## 5. 工具函数API

### 5.1 run_daily() - 设置每日定时任务

**函数签名**：
```python
run_daily(func, time=None, reference_security=None)
```

**说明**：
- 设置每日定时任务

**参数**：
- `func` (function): 要执行的函数
- `time` (str): 执行时间，如 '09:30'、'every_bar'（每个时间片）
- `reference_security` (str): 参考证券代码

**示例**：
```python
# 每个时间片执行
run_daily(market_open, time='every_bar')

# 每天上午9:30执行
run_daily(before_trading, time='09:30')

# 每天下午14:50执行
run_daily(after_trading, time='14:50')
```

**实际应用示例**（来自ai_debug.py）：
```python
# 盘前任务
run_daily(record_morning_stats, '09:25')  # 盘前统计
run_daily(analyze_market_environment, '09:26')  # 市场环境分析
run_daily(update_strategy_parameters, '09:27')  # 更新策略参数
run_daily(get_stock_list, '09:28:00')  # 获取股票列表

# 买入任务
run_daily(buy, '09:28:10')  # 早盘买入
run_daily(buy, '09:31:00')  # 开盘后买入
run_daily(buy, '10:00:00')  # 10点买入
run_daily(buy, '14:50:00')  # 周五下午建仓

# 卖出任务
run_daily(sell_limit_down, time='09:28', reference_security='000300.XSHG')
run_daily(sell2, '10:31')
```

---

### 5.2 run_monthly() - 设置每月定时任务

**函数签名**：
```python
run_monthly(func, monthday=None, time=None)
```

**说明**：
- 设置每月定时任务

**参数**：
- `func` (function): 要执行的函数
- `monthday` (int): 每月的第几天（1-31）
- `time` (str): 执行时间

**示例**：
```python
# 每月1号执行
run_monthly(rebalance, monthday=1)

# 每月15号上午10点执行
run_monthly(rebalance, monthday=15, time='10:00')
```

**实际应用示例**（来自多因子策略聚宽因子库.py）：
```python
# 每月调仓
run_monthly(handle_monthly, 1)
```

---

### 5.3 log.info() - 记录信息日志

**函数签名**：
```python
log.info(message)
```

**说明**：
- 记录信息级别的日志

**参数**：
- `message` (str): 日志消息

**示例**：
```python
log.info("策略开始运行")
log.info(f"当前持仓: {len(context.portfolio.positions)} 只")
```

**实际应用示例**（来自ai_debug.py）：
```python
log.info("=" * 80)
log.info("开始深度市场环境分析（增强版）")
log.info("=" * 80)
log.info(f"均线系统：")
log.info(f"  MA5: {ma5:.2f} (斜率: {ma5_slope:.4f})")
```

---

### 5.4 log.warn() - 记录警告日志

**函数签名**：
```python
log.warn(message)
```

**说明**：
- 记录警告级别的日志

**参数**：
- `message` (str): 日志消息

**示例**：
```python
log.warn("数据不足，无法计算指标")
```

---

### 5.5 log.error() - 记录错误日志

**函数签名**：
```python
log.error(message)
```

**说明**：
- 记录错误级别的日志

**参数**：
- `message` (str): 日志消息

**示例**：
```python
log.error(f"函数执行失败: {str(e)}")
```

---

### 5.6 log.set_level() - 设置日志级别

**函数签名**：
```python
log.set_level(level, logger_name='')
```

**说明**：
- 设置日志级别

**参数**：
- `level` (str): 日志级别，'order'、'system'、'debug'
- `logger_name` (str): 日志器名称

**示例**：
```python
log.set_level('order', 'order')  # 设置订单日志级别
log.set_level('system', 'error')  # 设置系统日志级别为error
```

**实际应用示例**（来自ai_debug.py）：
```python
log.set_level('system', 'error')
```

---

### 5.7 record() - 记录自定义指标

**函数签名**：
```python
record(**kwargs)
```

**说明**：
- 记录自定义指标到回测结果

**参数**：
- `**kwargs`: 键值对，键为指标名，值为指标值

**示例**：
```python
# 记录价格和均线
record(stock_price=current_price, MA5=MA5)

# 记录多个指标
record(price=current_price, ma5=MA5, ma20=MA20, volume=volume)
```

**实际应用示例**（来自debug.py）：
```python
# 记录数据到回测结果中
record(stock_price=current_price, MA5=MA5)
```

---

## 6. 技术分析API

### 6.1 MA - 移动平均线

**函数签名**：
```python
MA(series, timeperiod, matype=0)
```

**说明**：
- 计算移动平均线

**参数**：
- `series`: 价格序列
- `timeperiod`: 周期
- `matype`: 均线类型（0=SMA, 1=EMA, 2=WMA, 3=DEMA, 4=TEMA, 5=TRIMA, 6=KAMA, 7=MAMA, 8=T3）

**返回值**：
- 移动平均线序列

**示例**：
```python
from jqlib.technical_analysis import *

# 计算简单移动平均线
ma5 = MA(close_prices, 5)
ma20 = MA(close_prices, 20)

# 计算指数移动平均线
ema12 = MA(close_prices, 12, matype=1)
ema26 = MA(close_prices, 26, matype=1)
```

---

### 6.2 MACD - MACD指标

**函数签名**：
```python
MACD(series, fastperiod=12, slowperiod=26, signalperiod=9)
```

**说明**：
- 计算MACD指标

**参数**：
- `series`: 价格序列
- `fastperiod`: 快线周期（默认12）
- `slowperiod`: 慢线周期（默认26）
- `signalperiod`: 信号线周期（默认9）

**返回值**：
- (MACD, Signal, Hist) 元组

**示例**：
```python
from jqlib.technical_analysis import *

# 计算MACD
macd, signal, hist = MACD(close_prices)

# 金叉信号
if macd[-1] > signal[-1] and macd[-2] <= signal[-2]:
    print("MACD金叉")
```

---

### 6.3 KDJ - KDJ指标

**函数签名**：
```python
KDJ(high, low, close, fastk_period=9, slowk_period=3, slowd_period=3)
```

**说明**：
- 计算KDJ指标

**参数**：
- `high`: 最高价序列
- `low`: 最低价序列
- `close`: 收盘价序列
- `fastk_period`: 快速K线周期（默认9）
- `slowk_period`: 慢速K线周期（默认3）
- `slowd_period`: 慢速D线周期（默认3）

**返回值**：
- (K, D, J) 元组

**示例**：
```python
from jqlib.technical_analysis import *

# 计算KDJ
k, d, j = KDJ(high_prices, low_prices, close_prices)

# 超买信号
if k[-1] > 80:
    print("超买")
```

---

### 6.4 RSI - RSI指标

**函数签名**：
```python
RSI(series, timeperiod=14)
```

**说明**：
- 计算RSI指标

**参数**：
- `series`: 价格序列
- `timeperiod`: 周期（默认14）

**返回值**：
- RSI序列

**示例**：
```python
from jqlib.technical_analysis import *

# 计算RSI
rsi = RSI(close_prices, 14)

# 超买超卖信号
if rsi[-1] > 70:
    print("超买")
elif rsi[-1] < 30:
    print("超卖")
```

---

### 6.5 BOLL - 布林带

**函数签名**：
```python
BOLL(series, timeperiod=20, nbdevup=2, nbdevdn=2)
```

**说明**：
- 计算布林带

**参数**：
- `series`: 价格序列
- `timeperiod`: 周期（默认20）
- `nbdevup`: 上轨标准差倍数（默认2）
- `nbdevdn`: 下轨标准差倍数（默认2）

**返回值**：
- (Upper, Middle, Lower) 元组

**示例**：
```python
from jqlib.technical_analysis import *

# 计算布林带
upper, middle, lower = BOLL(close_prices, 20)

# 突破上轨
if close_prices[-1] > upper[-1]:
    print("突破上轨")
```

---

## 7. 市场数据API

### 7.1 get_locked_shares() - 获取限售解禁数据

**函数签名**：
```python
get_locked_shares(stock_list, start_date, forward_count)
```

**说明**：
- 获取限售解禁数据

**参数**：
- `stock_list` (list): 股票代码列表
- `start_date` (str/datetime): 开始日期
- `forward_count` (int): 向前查找的天数

**返回值**：
- DataFrame，包含限售解禁数据

**示例**：
```python
# 获取限售解禁数据
locked_shares = get_locked_shares(['000001.XSHE'], '2024-01-01', 30)
```

---

## 8. 财务数据API

### 8.1 get_fundamentals() - 获取基本面数据

**函数签名**：
```python
get_fundamentals(query_object, date=None, statDate=None)
```

**说明**：
- 获取基本面数据

**参数**：
- `query_object` (Query): 查询对象
- `date` (str/datetime): 查询日期
- `statDate` (str/datetime): 统计日期

**返回值**：
- DataFrame，包含查询结果

**示例**：
```python
# 查询估值数据
q = query(valuation.code, valuation.market_cap, valuation.pe_ratio)
df = get_fundamentals(q, date='2024-01-01')

# 查询财务指标
q = query(indicator.code, indicator.roe, indicator.eps)
df = get_fundamentals(q)
```

**实际应用示例**（来自多因子策略聚宽因子库.py）：
```python
# 获取财务数据
q = query(
    indicator.code,
    indicator.pubDate,
    indicator.statDate,
    indicator.eps,
    indicator.roe,
    indicator.roa,
    indicator.net_profit_margin,
    indicator.gross_profit_margin,
    indicator.ocf_to_revenue,
    indicator.inc_operation_profit_year_on_year
).filter(
    indicator.code.in_(stock_list),
    indicator.ocf_to_revenue > 0
)

df_finance = get_fundamentals(q).set_index('code')
```

---

### 8.2 finance.run_query() - 执行财务查询

**函数签名**：
```python
finance.run_query(query_object)
```

**说明**：
- 执行财务数据查询

**参数**：
- `query_object` (Query): 查询对象

**返回值**：
- DataFrame，包含查询结果

**示例**：
```python
# 查询股票列表
q = query(finance.STK_LIST.code, finance.STK_LIST.start_date)
df = finance.run_query(q)
```

**实际应用示例**（来自多因子策略聚宽因子库.py）：
```python
# 查询上市时间超过一年的股票
q = query(
    finance.STK_LIST.code,
    finance.STK_LIST.start_date,
    finance.STK_LIST.state
).filter(
    finance.STK_LIST.code.in_(stock_list),
    finance.STK_LIST.start_date < s_omb,
    finance.STK_LIST.state == '正常上市'
).order_by(finance.STK_LIST.start_date.asc())

df_LIST = finance.run_query(q).set_index('code')
```

---

## 9. 因子数据API

### 9.1 get_factor_values() - 获取因子数据

**函数签名**：
```python
get_factor_values(security_list, factors, start_date=None, end_date=None, count=None, df=True)
```

**说明**：
- 获取聚宽因子数据

**参数**：
- `security_list` (list): 证券代码列表
- `factors` (list): 因子列表
- `start_date` (str/datetime): 开始日期
- `end_date` (str/datetime): 结束日期
- `count` (int): 获取的天数
- `df` (bool): 是否返回DataFrame格式

**返回值**：
- DataFrame或字典，包含因子数据

**常用因子**：
- `book_to_price_ratio`: 账面市值比
- `sales_to_price_ratio`: 销售市值比
- `roe_ttm`: 滚动净资产收益率
- `total_asset_turnover_rate`: 总资产周转率
- `growth`: 成长因子
- `Price3M`: 3个月价格
- `market_cap`: 市值
- `ROC20`: 20日价格变动率
- `CR20`: 20日累计收益率

**示例**：
```python
# 获取因子数据
factors = ['book_to_price_ratio', 'sales_to_price_ratio', 'roe_ttm']
data = get_factor_values(stock_list, factors, start_date='2024-01-01', end_date='2024-01-01')
```

**实际应用示例**（来自多因子策略聚宽因子库.py）：
```python
# 根据新的证券列表取聚宽因子
jqf = ['book_to_price_ratio',
       'sales_to_price_ratio',
       'roe_ttm', 
       'total_asset_turnover_rate',
       'growth',
       'Price3M',       
       'market_cap']
data = get_factor_values(stock_list, factors=jqf, start_date=s_previous_date, end_date=s_previous_date)

# 替换列名
i = 0
df = data[jqf[i]].T
df.rename(columns={df.columns[0]: jqf[i]}, inplace=True)
df_valuation = df.iloc[:, 0:1].copy()
df_valuation.sort_index(ascending=True, inplace=True)

for i in range(1, len(jqf)):
    df = data[jqf[i]].T
    df.rename(columns={df.columns[0]: jqf[i]}, inplace=True)
    df.sort_index(ascending=True, inplace=True)
    df_valuation[jqf[i]] = df.iloc[:, 0:1].copy()
```

---

## 10. 高级功能API

### 10.1 OrderStyle - 订单类型

**说明**：
- 订单类型基类

**子类**：
- `MarketOrder`: 市价单
- `LimitOrder`: 限价单
- `StopOrder`: 止损单

**示例**：
```python
from jqlib.technical_analysis import *

# 市价单
order('000001.XSHE', 100, style=MarketOrder())

# 限价单
order('000001.XSHE', 100, style=LimitOrder(10.5))

# 止损单
order('000001.XSHE', 100, style=StopOrder(10.0))
```

---

### 10.2 Context - 上下文对象

**说明**：
- 策略上下文对象，包含账户信息、时间信息等

**常用属性**：
- `current_dt`: 当前时间
- `previous_date`: 前一个交易日
- `portfolio`: 账户组合信息

**Portfolio属性**：
- `total_value`: 总资产
- `available_cash`: 可用资金
- `positions`: 持仓信息

**示例**：
```python
# 获取当前时间
current_time = context.current_dt

# 获取前一个交易日
prev_date = context.previous_date

# 获取总资产
total_value = context.portfolio.total_value

# 获取可用资金
cash = context.portfolio.available_cash

# 获取持仓
positions = context.portfolio.positions
```

**实际应用示例**（来自debug.py）：
```python
# 获取可用资金
cash = context.portfolio.available_cash

# 获取持仓可卖出数量
closeable_amount = context.portfolio.positions[security].closeable_amount
```

---

## 附录A：快速索引

### 按功能分类

#### 策略初始化与配置
- [initialize](#11-initialize---策略初始化函数)
- [set_benchmark](#12-set_benchmark---设置基准指数)
- [set_option](#13-set_option---设置策略选项)
- [set_order_cost](#14-set_order_cost---设置交易成本)
- [OrderCost](#15-ordercost---交易成本类)
- [set_slippage](#16-set_slippage---设置滑点)
- [FixedSlippage](#17-fixedslippage---固定滑点类)

#### 数据获取
- [attribute_history](#21-attribute_history---获取历史属性数据)
- [get_price](#22-get_price---获取价格数据)
- [get_current_data](#23-get_current_data---获取当前数据)
- [get_trade_days](#24-get_trade_days---获取交易日)
- [get_all_securities](#25-get_all_securities---获取所有证券信息)
- [get_security_info](#26-get_security_info---获取证券详细信息)
- [get_index_stocks](#27-get_index_stocks---获取指数成分股)
- [get_industry_stocks](#28-get_industry_stocks---获取行业成分股)
- [get_concept_stocks](#29-get_concept_stocks---获取概念成分股)
- [get_billboard_list](#210-get_billboard_list---获取龙虎榜数据)
- [get_money_flow](#211-get_money_flow---获取资金流向数据)
- [get_mtss](#212-get_mtss---获取融资融券数据)

#### 交易执行
- [order](#31-order---按数量下单)
- [order_value](#32-order_value---按金额下单)
- [order_target](#33-order_target---目标数量下单)
- [order_target_value](#34-order_target_value---目标金额下单)
- [order_target_percent](#35-order_target_percent---目标比例下单)

#### 查询对象
- [query](#41-query---创建查询对象)
- [valuation](#42-valuation---估值数据表)
- [indicator](#43-indicator---财务指标表)
- [income](#44-income---利润表)
- [balance](#45-balance---资产负债表)
- [cash_flow](#46-cash_flow---现金流量表)
- [finance.STK_LIST](#47-financestk_list---股票列表表)

#### 工具函数
- [run_daily](#51-run_daily---设置每日定时任务)
- [run_monthly](#52-run_monthly---设置每月定时任务)
- [log.info](#53-loginfo---记录信息日志)
- [log.warn](#54-logwarn---记录警告日志)
- [log.error](#55-logerror---记录错误日志)
- [log.set_level](#56-logset_level---设置日志级别)
- [record](#57-record---记录自定义指标)

#### 技术分析
- [MA](#61-ma---移动平均线)
- [MACD](#62-macd---macd指标)
- [KDJ](#63-kdj---kdj指标)
- [RSI](#64-rsi---rsi指标)
- [BOLL](#65-boll---布林带)

#### 财务数据
- [get_fundamentals](#81-get_fundamentals---获取基本面数据)
- [finance.run_query](#82-fincerun_query---执行财务查询)

#### 因子数据
- [get_factor_values](#91-get_factor_values---获取因子数据)

---

### 按字母顺序

- [attribute_history](#21-attribute_history---获取历史属性数据)
- [BOLL](#65-boll---布林带)
- [balance](#45-balance---资产负债表)
- [cash_flow](#46-cash_flow---现金流量表)
- [Context](#102-context---上下文对象)
- [finance.run_query](#82-fincerun_query---执行财务查询)
- [finance.STK_LIST](#47-financestk_list---股票列表表)
- [FixedSlippage](#17-fixedslippage---固定滑点类)
- [get_all_securities](#25-get_all_securities---获取所有证券信息)
- [get_billboard_list](#210-get_billboard_list---获取龙虎榜数据)
- [get_concept_stocks](#29-get_concept_stocks---获取概念成分股)
- [get_current_data](#23-get_current_data---获取当前数据)
- [get_factor_values](#91-get_factor_values---获取因子数据)
- [get_fundamentals](#81-get_fundamentals---获取基本面数据)
- [get_index_stocks](#27-get_index_stocks---获取指数成分股)
- [get_industry_stocks](#28-get_industry_stocks---获取行业成分股)
- [get_money_flow](#211-get_money_flow---获取资金流向数据)
- [get_mtss](#212-get_mtss---获取融资融券数据)
- [get_price](#22-get_price---获取价格数据)
- [get_security_info](#26-get_security_info---获取证券详细信息)
- [get_trade_days](#24-get_trade_days---获取交易日)
- [indicator](#43-indicator---财务指标表)
- [income](#44-income---利润表)
- [initialize](#11-initialize---策略初始化函数)
- [KDJ](#63-kdj---kdj指标)
- [log.error](#55-logerror---记录错误日志)
- [log.info](#53-loginfo---记录信息日志)
- [log.set_level](#56-logset_level---设置日志级别)
- [log.warn](#54-logwarn---记录警告日志)
- [MACD](#62-macd---macd指标)
- [MA](#61-ma---移动平均线)
- [order](#31-order---按数量下单)
- [OrderCost](#15-ordercost---交易成本类)
- [OrderStyle](#101-orderstyle---订单类型)
- [order_target](#33-order_target---目标数量下单)
- [order_target_percent](#35-order_target_percent---目标比例下单)
- [order_target_value](#34-order_target_value---目标金额下单)
- [order_value](#32-order_value---按金额下单)
- [query](#41-query---创建查询对象)
- [record](#57-record---记录自定义指标)
- [RSI](#64-rsi---rsi指标)
- [run_daily](#51-run_daily---设置每日定时任务)
- [run_monthly](#52-run_monthly---设置每月定时任务)
- [set_benchmark](#12-set_benchmark---设置基准指数)
- [set_option](#13-set_option---设置策略选项)
- [set_order_cost](#14-set_order_cost---设置交易成本)
- [set_slippage](#16-set_slippage---设置滑点)
- [valuation](#42-valuation---估值数据表)

---

## 附录B：常见问题

### Q1: 如何获取股票的历史数据？

**A**: 使用 `attribute_history()` 或 `get_price()` 函数。

```python
# 方法1：使用attribute_history
close_data = attribute_history('000001.XSHE', 20, '1d', ['close'])

# 方法2：使用get_price
price_data = get_price('000001.XSHE', count=20, unit='1d', fields=['close'])
```

---

### Q2: 如何查询基本面数据？

**A**: 使用 `query()` 和 `get_fundamentals()` 函数。

```python
# 查询估值数据
q = query(valuation.code, valuation.market_cap, valuation.pe_ratio)
df = get_fundamentals(q, date='2024-01-01')

# 查询财务指标
q = query(indicator.code, indicator.roe, indicator.eps)
df = get_fundamentals(q)
```

---

### Q3: 如何设置交易成本？

**A**: 使用 `set_order_cost()` 函数。

```python
set_order_cost(OrderCost(
    open_tax=0,
    close_tax=0.001,
    open_commission=0.0003,
    close_commission=0.0003,
    min_commission=5
), type='stock')
```

---

### Q4: 如何执行交易？

**A**: 使用 `order()`, `order_value()`, `order_target()` 等函数。

```python
# 按数量买入
order('000001.XSHE', 100)

# 按金额买入
order_value('000001.XSHE', 10000)

# 调整持仓到目标数量
order_target('000001.XSHE', 100)

# 清仓
order_target_value('000001.XSHE', 0)
```

---

### Q5: 如何设置定时任务？

**A**: 使用 `run_daily()` 或 `run_monthly()` 函数。

```python
# 每个时间片执行
run_daily(market_open, time='every_bar')

# 每天上午9:30执行
run_daily(before_trading, time='09:30')

# 每月1号执行
run_monthly(rebalance, monthday=1)
```

---

### Q6: 如何计算技术指标？

**A**: 使用 `jqlib.technical_analysis` 模块。

```python
from jqlib.technical_analysis import *

# 计算移动平均线
ma5 = MA(close_prices, 5)

# 计算MACD
macd, signal, hist = MACD(close_prices)

# 计算KDJ
k, d, j = KDJ(high_prices, low_prices, close_prices)

# 计算RSI
rsi = RSI(close_prices, 14)

# 计算布林带
upper, middle, lower = BOLL(close_prices, 20)
```

---

### Q7: 如何获取指数成分股？

**A**: 使用 `get_index_stocks()` 函数。

```python
# 获取沪深300成分股
hs300_stocks = get_index_stocks('000300.XSHG')

# 获取指定日期的成分股
hs300_stocks_2024 = get_index_stocks('000300.XSHG', date='2024-01-01')
```

---

### Q8: 如何记录日志？

**A**: 使用 `log` 模块。

```python
log.info("信息日志")
log.warn("警告日志")
log.error("错误日志")
```

---

### Q9: 如何记录自定义指标？

**A**: 使用 `record()` 函数。

```python
record(stock_price=current_price, MA5=MA5)
```

---

### Q10: 如何获取聚宽因子数据？

**A**: 使用 `get_factor_values()` 函数。

```python
factors = ['book_to_price_ratio', 'roe_ttm', 'market_cap']
data = get_factor_values(stock_list, factors, start_date='2024-01-01', end_date='2024-01-01')
```

---

## 文档说明

本文档基于聚宽JoinQuant平台实际代码使用情况整理，包含了策略开发中最常用的API函数。每个API函数都包含了：

- 函数签名
- 详细说明
- 参数列表
- 返回值说明
- 实际示例代码

**文档特点**：
1. **实用性强**：基于实际策略代码整理，确保所有API都经过实际验证
2. **示例丰富**：每个API都包含实际使用示例
3. **分类清晰**：按功能分类，便于查找
4. **快速索引**：提供按功能和按字母顺序的快速索引

**更新记录**：
- 2026-01-28: 初始版本，基于JoinQuantEgs文件夹中的代码整理
- 2026-01-28: 添加set_slippage()和FixedSlippage API说明

**参考资料**：
- 聚宽JoinQuant官方文档: https://www.joinquant.com/help/api/help
- JoinQuantEgs文件夹中的策略代码

---

## 最佳实践

### 1. 策略初始化最佳实践

```python
def initialize(context):
    # 1. 设置基准指数
    set_benchmark('000300.XSHG')
    
    # 2. 设置交易成本（股票）
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.0003,
        close_commission=0.0003,
        min_commission=5
    ), type='stock')
    
    # 3. 设置滑点
    set_slippage(FixedSlippage(0.001))
    
    # 4. 设置策略选项
    set_option('use_real_price', True)
    set_option('avoid_future_data', True)
    
    # 5. 设置日志级别
    log.set_level('system', 'error')
    
    # 6. 设置定时任务
    run_daily(before_trading, time='09:25')
    run_daily(market_open, time='every_bar')
    run_daily(after_trading, time='15:05')
```

### 2. 数据获取最佳实践

```python
# 使用attribute_history获取历史数据（推荐）
close_data = attribute_history('000001.XSHE', 20, '1d', ['close'])

# 使用get_price获取价格数据
price_data = get_price('000001.XSHE', count=20, unit='1d', fields=['close'])

# 使用get_current_data获取当前数据
current_data = get_current_data()
current_price = current_data['000001.XSHE'].price
```

### 3. 交易执行最佳实践

```python
# 买入时使用order_value，避免数量计算错误
order_value('000001.XSHE', 10000)

# 卖出时使用order_target_value，便于清仓
order_target_value('000001.XSHE', 0)

# 检查订单是否成功
order_obj = order('000001.XSHE', 100)
if order_obj:
    log.info(f"订单成功: {order_obj}")
```

### 4. 风险控制最佳实践

```python
# 设置止损
if profit_pct < -0.05:  # 亏损超过5%
    order_target_value(stock, 0)
    log.info(f"止损卖出: {stock}, 亏损: {profit_pct:.2%}")

# 设置止盈
if profit_pct > 0.10:  # 盈利超过10%
    order_target_value(stock, 0)
    log.info(f"止盈卖出: {stock}, 盈利: {profit_pct:.2%}")

# 控制单只股票仓位
max_position_ratio = 0.1  # 单只股票不超过总资产的10%
if position_value / total_value > max_position_ratio:
    log.warning(f"仓位过重: {stock}, 当前仓位: {position_value / total_value:.2%}")
```

### 5. 日志记录最佳实践

```python
# 使用info记录重要信息
log.info(f"买入: {stock}, 价格: {price:.2f}, 数量: {amount}")

# 使用warn记录警告
log.warn(f"数据不足: {stock}, 可用数据量: {len(data)}")

# 使用error记录错误
log.error(f"交易失败: {stock}, 错误: {str(e)}")

# 使用record记录自定义指标
record(price=current_price, ma5=MA5, ma20=MA20)
```

---

## 注意事项

### 1. 避免未来函数

```python
# ❌ 错误：使用未来数据
df = get_price('000001.XSHE', end_date='2024-01-15', count=10)
# 如果在2024-01-15之前使用这个数据，就是未来函数

# ✅ 正确：使用历史数据
df = attribute_history('000001.XSHE', 10, '1d', ['close'])
# attribute_history自动处理未来数据问题
```

### 2. 股票代码格式

```python
# 股票代码格式：6位数字.交易所代码
# 上交所：.XSHG
# 深交所：.XSHE

# ✅ 正确格式
'000001.XSHE'  # 平安银行（深交所）
'600000.XSHG'  # 浦发银行（上交所）

# ❌ 错误格式
'000001'       # 缺少交易所代码
'000001.SZ'    # 错误的交易所代码
```

### 3. 日期格式

```python
# 日期格式：YYYY-MM-DD

# ✅ 正确格式
'2024-01-15'
'2024-12-31'

# ❌ 错误格式
'2024/01/15'  # 使用了斜杠
'2024-1-15'   # 月份和日期没有补零
```

### 4. 交易日处理

```python
# 获取交易日
trade_days = get_trade_days(end_date='2024-01-15', count=5)

# 注意：trade_days是DatetimeIndex，不是字符串
# 需要转换为字符串格式
date_str = trade_days[-1].strftime('%Y-%m-%d')

# 使用context.previous_date获取前一个交易日
prev_date = context.previous_date.strftime('%Y-%m-%d')
```

### 5. 持仓管理

```python
# 获取持仓
positions = context.portfolio.positions

# 遍历持仓
for stock, position in positions.items():
    total_amount = position.total_amount        # 总持仓数量
    closeable_amount = position.closeable_amount  # 可卖出数量
    avg_cost = position.avg_cost                 # 平均成本

# 注意：closeable_amount可能小于total_amount
# 因为部分股票可能被锁定（如新股中签）
```

### 6. 数据类型处理

```python
# attribute_history返回值类型
data = attribute_history('000001.XSHE', 10, '1d', ['close'])
# data是字典，键是字段名，值是numpy数组
close_values = data['close']  # numpy数组

# get_price返回值类型
data = get_price('000001.XSHE', count=10, unit='1d', fields=['close'])
# data是DataFrame，索引是日期，列是字段
close_values = data['close']  # Series

# 获取最新值
latest_close = close_values[-1]  # 最后一个值
```

### 7. 异常处理

```python
# 使用try-except处理异常
try:
    data = attribute_history('000001.XSHE', 10, '1d', ['close'])
    if len(data['close']) < 10:
        log.warn(f"数据不足: {stock}")
        return
except Exception as e:
    log.error(f"获取数据失败: {stock}, 错误: {str(e)}")
    return
```

### 8. 性能优化

```python
# 批量获取数据
stock_list = ['000001.XSHE', '600000.XSHG', '000002.XSHE']
data = attribute_history(stock_list, 10, '1d', ['close'])  # 一次性获取多只股票

# 避免重复获取相同数据
# 使用缓存
if not hasattr(g, 'price_cache'):
    g.price_cache = {}

if stock not in g.price_cache:
    g.price_cache[stock] = attribute_history(stock, 10, '1d', ['close'])

data = g.price_cache[stock]
```

---

**如有疑问或需要补充，请联系文档维护者。**