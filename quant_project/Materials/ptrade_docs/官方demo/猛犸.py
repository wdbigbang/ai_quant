"""
策略名称：
猛犸策略
注意事项：
策略中调用的order_target接口的使用有场景限制，回测可以正常使用，交易谨慎使用。
回测场景下撮合是引擎计算的，因此成交之后持仓信息的更新是瞬时的，但交易场景下信息的更新依赖于柜台数据
的返回，无法做到瞬时同步，可能造成重复下单。详细原因请看帮助文档。
"""
import random


def initialize(context):
    # 交易标的列表（该股票池中的代码仅作为demo演示，非投资建议）
    context.universe = [
        '002131.SZ',
        '002736.SZ',
        '600804.SS',
        '000001.SZ',
        '600376.SS',
        '600104.SS',
        '000630.SZ',
        '002065.SZ',
        '601166.SS',
        '600875.SS',
        '000555.SZ',
        '601939.SS',
        '600999.SS',
    ]
    g.daycount = 0
    g.holdstocks = []


def handle_data(context, data):
    # 最大持仓股票支数
    maxhold = 5
    totalsize = len(context.universe)
    # 取得当前的现金
    cash = context.portfolio.cash
    g.daycount = g.daycount + 1

    if len(g.holdstocks) == 0:  # 初始状态
        count = maxhold
        singlemoney = cash / maxhold

        while count > 0:
            buystock = context.universe[random.randint(0, totalsize - 1)]
            if buystock not in g.holdstocks:
                g.holdstocks.append(buystock)
                # 用所有 singlemoney 买入股票
                log.info('buystock=' + buystock)
                log.info('singlemoney=' + str(singlemoney))
                order_value(buystock, singlemoney)
                # 记录这次买入
                # log.info("Buying %s" % (buystock))
                log.info("Buying %s" % buystock)
                count = count - 1
                log.info('count=' + str(count))

    elif g.daycount % 5 == 1:  # 5 days change

        log.info('g.daycount=' + str(g.daycount))
        # 选择过去7天表现最差的股票卖出
        weakstock = ''
        weak_returns = 10000
        his_data_info = get_history(7, '1d', field=['price', 'volume'], security_list=context.universe,
                                    fq='pre', include=False, is_dict=True)
        halt_status = get_stock_status(context.universe, 'HALT')
        for stock in g.holdstocks:
            his_data = his_data_info[stock]
            # 当日停牌跳过
            if halt_status[stock]:
                continue
            if his_data.size == 0:
                continue
            startprice = his_data['price'][0]
            endprice = his_data['price'][-1]

            cur_returns = endprice / startprice - 1
            # 遍历记录涨幅最小的股票
            if cur_returns < weak_returns:
                weak_returns = cur_returns
                weakstock = stock
        if weakstock == '':
            weakstock = g.holdstocks[0]
        sellstock = weakstock
        log.info('weakstock=' + weakstock)
        g.holdstocks.remove(weakstock)
        # 卖出所有股票,使这只股票的最终持有量为0
        order_target(sellstock, 0)
        # 记录这次卖出
        log.info("selling %s" % sellstock)

        while True:
            buystock = context.universe[random.randint(0, totalsize - 1)]
            if buystock not in g.holdstocks and buystock != sellstock:
                g.holdstocks.append(buystock)
                # 用所有 cash 买入股票
                log.info('buystock=' + buystock)
                log.info('cash=' + str(cash))
                order_value(buystock, cash)
                # 记录这次买入
                log.info("Buying %s" % buystock)
                break