"""
策略名称：
协整配对策略
注意事项：
策略中调用的order_target、order_target_value接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""
import numpy as np


# 初始化函数，设定基准等等
def initialize(context):
    set_params()
    set_variables()
    set_backtest()


# ---代码块1. 设置参数
def set_params():
    # 股票1
    g.security1 = '601398.SS'
    # 股票2
    g.security2 = '601988.SS'
    # 基准
    g.benchmark = '601988.SS'
    # 回归系数
    g.regression_ratio = 0.9938
    # 股票1默认仓位
    g.p = 0.5
    # 股票2默认仓位
    g.q = 0.5
    # 算z-score天数
    g.test_days = 120
    # 
    g.days_count = 0
    # 
    g.benchmarkStart = 0
    #
    g.portfolioStart = 0


# ---代码块2. 设置变量
def set_variables():
    # 现在状态
    g.state = 'empty'


# ---代码块3. 设置回测
def set_backtest():
    # 设置基准
    set_benchmark(g.benchmark)


def before_trading_start(context, data):
    current_date = context.blotter.current_dt.strftime('%Y-%m-%d')
    # 2006-11-01前回测由于数据不足，不执行。
    if current_date < '2006-11-01':
        g.trade_flag = False
    else:
        g.trade_flag = True


# 每个单位时间(如果按天回测,则每天调用一次,如果按分钟,则每分钟调用一次)调用一次
def handle_data(context, data):
    if not g.trade_flag:
        return
    g.days_count += 1
    log.info('day:' + str(g.days_count))
    # z值检验流程
    # 获取两支股票历史价格
    prices1 = get_history(g.test_days, '1d', 'close', g.security1, is_dict=True)[g.security1]['close']
    prices2 = get_history(g.test_days, '1d', 'close', g.security2, is_dict=True)[g.security2]['close']

    # 根据回归比例算它们的平稳序列 a.X-Y,
    stable_series = g.regression_ratio * prices1 - prices2
    # 算均值
    series_mean = np.mean(stable_series)
    # 算标准差
    sigma = np.std(stable_series)
    # 算序列现值离均值差距多少
    diff = stable_series[-1] - series_mean
    # 返回z值
    z_score = diff / sigma
    # log.info('z_score='+str(z_score))
    new_state = get_signal(z_score)
    # log.info(new_state)
    # 调仓
    change_positions(new_state, context)


# ---代码块5.获取信号
# 返回新的状态，是一个string
def get_signal(z_score):
    if z_score > 1:
        # 状态为全仓第二支
        return 'buy2'
    # 如果小于负标准差
    if z_score < -1:
        # 状态为全仓第一支
        return 'buy1'
    # 如果在正负标准差之间
    if -1 <= z_score <= 1:
        # 如果差大于0
        if z_score >= 0:
            # 在均值上面
            return 'side1'
        # 反之
        else:
            # 在均值下面
            return 'side2'


# ---代码块6.根据信号调换仓位
# 输入是目标状态，输入为一个string
def change_positions(new_state, context):
    # 总值产价值
    total_value = context.portfolio.portfolio_value
    # 如果新状态是全仓股票1
    if new_state == 'buy1':
        # 全卖股票2
        order_target(g.security2, 0)
        # 全买股票1
        order_value(g.security1, total_value)
        # 旧状态更改
        g.state = 'buy1'
    # 如果新状态是全仓股票2
    if new_state == 'buy2':
        # 全卖股票1
        order_target(g.security1, 0)
        # 全买股票2
        order_value(g.security2, total_value)
        # 旧状态更改
        g.state = 'buy2'
    # 如果处于全仓一股票状态，但是z-score交叉0点
    if (g.state == 'buy1' and new_state == 'side1') or (g.state == 'buy2' and new_state == 'side2'):
        # 按照p,q值将股票仓位调整为默认值
        order_target_value(g.security1, g.p * total_value)
        order_target_value(g.security2, g.q * total_value)
        # 代码里重复两遍因为要先卖后买，而我们没有特地确定哪个先哪个后
        order_target_value(g.security1, g.p * total_value)
        order_target_value(g.security2, g.q * total_value)
        # 状态改为‘平’
        g.state = 'even'