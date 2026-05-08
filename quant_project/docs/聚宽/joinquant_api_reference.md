# -*- coding: utf-8 -*-
# 聚宽JoinQuant API参考文档

## 数据获取API概览

### 股票数据
- 股票列表数据
- 交易统计数据
- 融资融券数据
- 行业概念及成分股数据
- 沪股通、深股通和港股通(市场通数据)
- 集合竞价结果数据
- 多频率分时数据

### 基金数据
- 基金交易标的列表
- 基金主体信息
- 基金投资组合
- 基金财务指标
- 基金分红信息
- 净值及业绩表现

### 财务数据
- 单季度/年度财务数据
- 报告期财务数据
- 上市公司概况（上市信息，员工信息）
- 上市公司股东股本

### 指数数据
- 指数交易标的列表
- 多频率分时数据
- 指数成分股及权重

### 期货数据
- 获取所有期货信息
- 指定日期的期货列表数据
- 期货主力合约
- 期货连续指数
- 外盘期货日行情数据
- 期货龙虎榜数据
- 期货仓单数据
- 期货结算价
- 期货持仓量
- 期货合约的信息
- 多频率分时数据

### 期权数据
- 获取所有期权信息
- 股票期权交易和持仓排名统计
- 期权风险指标
- 期权行权交收信息
- 期权合约调整记录
- 期权合约资料
- 期权每日盘前静态文件

### 历史数据
- 日、周、月等周期历史金融数据

## 常用API函数

### 数据获取函数
```python
# 获取历史数据
history(count, unit, field, security_list, df=True, skip_paused=True, fq='pre')

# 获取基本面数据
get_fundamentals(query_object, date=None, statDate=None)

# 获取当前数据
get_current_data()

# 获取指数成分股
get_index_stocks(index_code, date=None)

# 获取行业成分股
get_industry_stocks(industry_code, date=None)

# 获取概念成分股
get_concept_stocks(concept_code, date=None)

# 获取限售解禁数据
get_locked_shares(stock_list, start_date, forward_count)

# 获取所有证券信息
get_all_securities(types=[], date=None)

# 获取证券信息
get_security_info(security)

# 获取价格数据
get_price(security, count=None, unit='1d', fields=None, reference_date=None, fq_ref_date=None, skip_paused=True, fq='pre')

# 获取龙虎榜数据
get_billboard_list(stock_list=None, end_date=None, count=1)
```

### 查询对象
```python
# 估值数据查询
query(valuation.code, valuation.market_cap, valuation.pe_ratio)

# 指标数据查询
query(indicator.code, indicator.roe, indicator.eps)

# 收入数据查询
query(income.code, income.total_revenue, income.net_profit)

# 资产负债数据查询
query(balance.code, balance.total_assets, balance.total_liab)

# 现金流数据查询
query(cash_flow.code, cash_flow.net_cash_flows_oper_act)
```

## 平台适配器实现

### 聚宽数据适配器
```python
# -*- coding: utf-8 -*-
import pandas as pd
from typing import List, Dict, Any, Optional

class JoinQuantAdapter:
    """聚宽平台数据适配器"""
    
    def __init__(self):
        self.platform = 'joinquant'
    
    def get_price(self, security: str, count: int, end_date: str = None, **kwargs) -> pd.DataFrame:
        """获取价格数据"""
        return get_price(security, count=count, end_date=end_date, **kwargs)
    
    def get_fundamentals(self, query_obj, date: str = None, **kwargs) -> pd.DataFrame:
        """获取基本面数据"""
        return get_fundamentals(query_obj, date=date, **kwargs)
    
    def get_current_data(self) -> Dict:
        """获取当前数据"""
        return get_current_data()
    
    def get_index_stocks(self, index_code: str, date: str = None) -> List[str]:
        """获取指数成分股"""
        return get_index_stocks(index_code, date=date)
    
    def order(self, security: str, amount: int, **kwargs) -> Any:
        """下单"""
        return order(security, amount, **kwargs)
    
    def order_value(self, security: str, value: float, **kwargs) -> Any:
        """按金额下单"""
        return order_value(security, value, **kwargs)
    
    def order_target(self, security: str, target_amount: int, **kwargs) -> Any:
        """目标仓位下单"""
        return order_target(security, target_amount, **kwargs)
```

### 数据格式转换
```python
# -*- coding: utf-8 -*-
class DataConverter:
    """数据格式转换器"""
    
    @staticmethod
    def joinquant_to_universal(data: pd.DataFrame) -> pd.DataFrame:
        """聚宽数据格式转通用格式"""
        # 股票代码格式转换: 000001.XSHE -> 000001.SZ
        if 'code' in data.columns:
            data['code'] = data['code'].apply(
                lambda x: x.replace('.XSHE', '.SZ').replace('.XSHG', '.SH')
            )
        return data
    
    @staticmethod
    def universal_to_joinquant(security: str) -> str:
        """通用股票代码转聚宽格式"""
        if security.endswith('.SZ'):
            return security.replace('.SZ', '.XSHE')
        elif security.endswith('.SH'):
            return security.replace('.SH', '.XSHG')
        return security
```

## 策略迁移示例

### 聚宽策略模板
```python
# -*- coding: utf-8 -*-
def initialize(context):
    """聚宽策略初始化"""
    # 设置基准
    set_benchmark('000300.XSHG')
    
    # 设置股票池
    g.stock_pool = ['000001.XSHE', '600000.XSHG']
    
    # 设置手续费
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, 
                           open_commission=0.0003, close_commission=0.0003,
                           min_commission=5), type='stock')

def handle_data(context, data):
    """聚宽策略数据处理"""
    for stock in g.stock_pool:
        # 获取历史数据
        hist_data = attribute_history(stock, 20, '1d', ['close'])
        
        # 计算均线
        ma5 = hist_data['close'][-5:].mean()
        ma20 = hist_data['close'].[-20:].mean()
        
        # 交易逻辑
        current_price = data[stock].price
        if ma5 > ma20 and stock not in context.portfolio.positions:
            order_value(stock, context.portfolio.available_cash / len(g.stock_pool))
        elif ma5 < ma20 and stock in context.portfolio.positions:
            order_target_percent(stock, 0)
```

### 通用策略模板
```python
# -*- coding: utf-8 -*-
class UniversalStrategy:
    """通用策略类"""
    
    def __init__(self, platform='joinquant'):
        self.platform = platform
        self.adapter = self._get_adapter(platform)
        self.stock_pool = ['000001.SZ', '600000.SH']
    
    def initialize(self, context):
        """统一初始化接口"""
        if self.platform == 'joinquant':
            self._initialize_joinquant(context)
        elif self.platform == 'qmt':
            self._initialize_qmt(context)
        else:
            self._initialize_backtest(context)
    
    def handle_data(self, context, data):
        """统一数据处理接口"""
        for stock in self.stock_pool:
            # 转换股票代码格式
            platform_stock = self._convert_stock_code(stock)
            
            # 获取历史数据
            hist_data = self.adapter.get_history_data(platform_stock, 20, ['close'])
            
            # 计算均线
            ma5 = hist_data['close'][-5:].mean()
            ma20 = hist_data['close'][-20:].mean()
            
            # 交易逻辑
            current_price = self.adapter.get_current_price(platform_stock)
            if ma5 > ma20 and not self.adapter.has_position(platform_stock):
                self.adapter.order_value(platform_stock, self.get_available_cash() / len(self.stock_pool))
            elif ma5 < ma20 and self.adapter.has_position(platform_stock):
                self.adapter.order_target_percent(platform_stock, 0)
```

## 注意事项

1. **数据权限**: 聚宽平台的数据获取需要相应的权限和积分
2. **频率限制**: 注意API调用频率限制，避免触发限制
3. **数据质量**: 聚宽数据经过清洗，但实盘前仍需验证
4. **代码兼容**: 聚宽平台不支持某些Python库，需要使用平台提供的函数
5. **回测差异**: 聚宽回测环境与实盘环境存在差异，需要注意

## 参考链接

- 聚宽API文档: https://www.joinquant.com/help/api/doc?name=logon&id=9830
- 聚宽数据文档: https://www.joinquant.com/help/api/help?name=JQData
- 聚宽策略文档: https://www.joinquant.com/help/api/help?name=algorithm