# PTrade API 学习笔记

## 1. 股票代码格式

| 平台 | 上交所 | 深交所 | 示例 |
|------|--------|--------|------|
| **聚宽** | .XSHG | .XSHE | 600000.XSHG, 000001.XSHE |
| **PTrade** | .SS | .SZ | 600000.SS, 000001.SZ |
| **PTrade指数** | .XBHS | .XBHS | 000300.XBHS, 399101.XBHS |

## 2. 策略框架

```python
# 初始化
def initialize(context):
    g.security = ['600570.SS', '000001.SZ']
    set_universe(g.security)
    set_benchmark('000300.XSHG')

# 盘前处理（9:10）
def before_trading_start(context, data):
    pass

# 盘中处理（日线14:50，分钟09:30每分钟）
def handle_data(context, data):
    pass

# 盘后处理（15:30）
def after_trading_end(context, data):
    pass
```

## 3. 核心API对照表

### 设置函数

| 功能 | 聚宽 | PTrade |
|------|------|--------|
| 设置股票池 | set_universe() | set_universe() |
| 设置基准 | set_benchmark() | set_benchmark() |
| 设置佣金 | set_order_cost() | set_commission(commission_ratio, min_commission) |
| 设置滑点 | set_slippage() | set_slippage(slippage) 或 set_fixed_slippage(fixedslippage) |
| 设置成交限制 | - | set_limit_mode('UNLIMITED') |

### 获取行情函数

| 功能 | 聚宽 | PTrade |
|------|------|--------|
| 获取历史数据 | get_price() | get_history(count, frequency, field, security_list, fq, include, is_dict) |
| 获取当前数据 | get_current_data() | data[security] |
| 获取实时快照 | - | get_snapshot(security) |

**PTrade get_history 参数**：
```python
his = get_history(
    count=5,              # K线数量
    frequency='1d',       # 周期：'1m', '5m', '15m', '30m', '60m', '1d', '1w'
    field='close',        # 字段：'open', 'high', 'low', 'close', 'volume', 'money'
    security_list=g.security,  # 股票列表
    fq=None,              # 复权：'pre', 'post', 'dypre', None
    include=False,        # 是否包含当前周期
    is_dict=True          # 返回字典格式
)
# 返回格式：{stock: {'close': array([...]), 'open': array([...]), ...}}
```

### 交易函数

| 功能 | 聚宽 | PTrade |
|------|------|--------|
| 按数量下单 | order(stock, amount) | order(stock, amount) |
| 目标数量下单 | order_target(stock, amount) | order_target(stock, amount) |
| 按金额下单 | order_value(stock, value) | order_value(stock, value) |
| 目标金额下单 | order_target_value(stock, value) | order_target_value(stock, value) |

**注意事项**：
- `order_target_value` 在交易场景下需谨慎使用（可能重复下单）
- 建议用 `order` 或 `order_target` 配合持仓判断

### 持仓查询函数

| 功能 | 聚宽 | PTrade |
|------|------|--------|
| 获取持仓 | context.portfolio.positions | get_positions() 或 context.portfolio.positions |
| 获取单个持仓 | - | get_position(security) |
| 获取可用资金 | context.portfolio.cash | context.portfolio.cash |
| 获取总资产 | context.portfolio.total_value | context.portfolio.total_value |

**PTrade Position对象属性**：
- `position.sid`：股票代码
- `position.amount`：持仓数量
- `position.enable_amount`：可用数量
- `position.cost_basis`：成本价

### 选股函数

| 功能 | 聚宽 | PTrade |
|------|------|--------|
| 获取指数成分股 | get_index_stocks(index) | get_index_stocks(index_code, date) |
| 获取行业成分股 | - | get_industry_stocks(industry_code) |
| 获取A股列表 | get_all_securities() | get_Ashares(date) |
| 获取财务数据 | get_fundamentals(query) | get_fundamentals(security, table, fields, date) |

### 状态过滤函数

```python
# PTrade 过滤ST、停牌、退市
stock_list = filter_stock_by_status(
    stock_list,
    filter_type=["ST", "HALT", "DELISTING"],
    query_date=None
)

# 检查涨跌停
limit_status = check_limit(stock)  # 返回 {stock: 1涨停, 0正常, -1跌停}
```

### 其他常用函数

```python
# 获取交易日
trading_day = get_trading_day(0)  # 0今天，1明天，-1昨天

# 获取股票状态
st_status = get_stock_status(stock, 'ST')
halt_status = get_stock_status(stock, 'HALT')

# 获取股票名称
name = get_stock_name(stock)

# 日志
log.info("输出字符串 %s" % (变量名))
```

## 4. 事件时间

| 事件 | 时间 | 聚宽 | PTrade |
|------|------|------|--------|
| 盘前 | 9:10 | before_trading_start | before_trading_start |
| 开盘 | 9:30 | handle_data | handle_data |
| 收盘 | 15:00 | - | - |
| 盘后 | 15:30 | after_trading_end | after_trading_end |

## 5. 禁止使用

| 函数 | 聚宽 | PTrade |
|------|------|--------|
| run_daily() | ✅ 支持 | ❌ 禁止 |
| run_weekly() | ✅ 支持 | ❌ 禁止 |
| run_monthly() | ✅ 支持 | ❌ 禁止 |
| run_interval() | ✅ 支持 | ❌ 禁止 |

**替代方案**：用时间判断代替定时任务

## 6. 数据结构差异

### context对象

```python
# 聚宽
context.current_dt           # 当前时间
context.previous_date        # 上一交易日
context.portfolio.positions  # 持仓字典
context.portfolio.cash       # 可用资金
context.portfolio.total_value # 总资产

# PTrade
context.blotter.current_dt   # 当前时间
context.previous_date        # 上一交易日
context.portfolio.positions  # 持仓字典
context.portfolio.cash       # 可用资金
context.portfolio.total_value # 总资产
context.current_dt           # 当前时间（也有）
```

### data对象

```python
# 获取当前价格
price = data[stock].price    # 最新价
close = data[stock].close    # 收盘价
open = data[stock].open      # 开盘价
high = data[stock].high      # 最高价
low = data[stock].low        # 最低价
```

## 7. 注意事项

1. **order_target_value 交易场景慎用**：可能导致重复下单
2. **股票代码格式**：PTrade用 .SS/.SZ，聚宽用 .XSHG/.XSHE
3. **指数代码格式**：PTrade用 .XBHS
4. **定时任务**：PTrade禁止使用 run_daily/run_weekly/run_monthly
5. **日志格式**：`log.info("字符串 %s" % (变量))`
6. **回测设置**：用 `set_limit_mode('UNLIMITED')` 设置无限制成交