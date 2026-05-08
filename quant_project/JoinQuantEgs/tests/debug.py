#python3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# 配置matplotlib中文字体显示（Linux系统）
# 尝试多个常见的中文字体，确保至少有一个可用

def test_numpy_base():
    file_name="./demo.csv"
    # 读取指令列的数据，第3列是收盘价格，第7列是成交量
    end_prince, volume = np.loadtxt(fname= file_name,
                                    delimiter =',',
                                    usecols=(2,6),
                                    unpack=True
    )
    print(f"end_prince:{end_prince}, volume:{volume}")
    # 根据按天的最高/最低价格，计算整体的最高/最低价格
    max_daily_price, min_daily_price = np.loadtxt(fname= file_name,
                                    delimiter =',', 
                                    usecols=(4,5),
                                    unpack=True
    )
    max_price = np.max(max_daily_price)
    min_price = np.min(min_daily_price)
    print(f"max_price:{max_price}, min_price:{min_price}")
    # 根据按天的 最高/最低价格，计算极差
    ptp_max = np.ptp(max_daily_price)
    ptp_min = np.ptp(min_daily_price)
    print(f"price_range_max:{ptp_max}, price_range_min:{ptp_min}")

    #计算平均收盘价 & 成交量加权平均价格 VWAP
    avg_close_price = np.mean(end_prince)
    vwap = np.average(end_prince, weights=volume)
    print(f"vwap:{vwap}, avg_close_price:{avg_close_price}")
    # 计算收盘价的中位数
    median_close_price = np.median(end_prince)
    print(f"median_close_price:{median_close_price}")
    # 计算收盘价的标准差 & 方差
    std_close_price = np.std(end_prince)
    var_close_price = np.var(end_prince)
    print(f"std_close_price:{std_close_price}, var_close_price:{var_close_price}")
    # 计算该股票的 收益率
    log_returns= np.diff(np.log(end_prince))
    print(f"log_returns:{log_returns}")
    # 计算年波动率
    annual_volatility = log_returns.std() / log_returns.mean() * np.sqrt(250)
    print(f"annual_volatility:{annual_volatility}")
    # 计算月波动率
    monthly_volatility = log_returns.std() / log_returns.mean() * np.sqrt(12)
    print(f"monthly_volatility:{monthly_volatility}")

def test_numpy_advanced():
    file_name="./demo.csv"
    # 读取指令列的数据，第3列是收盘价格，第7列是成交量
    end_prince = np.loadtxt(fname= file_name,
                                    delimiter =',',
                                    usecols=(2),
                                    unpack=True
    )
    # 计算收盘价的 5日 平均线
    N = 5
    t = np.arange(N-1, len(end_prince))
    ma5 = np.convolve(end_prince, np.ones(N)/N)[N-1:-N+1]
    print(f"ma5:{ma5}")
    plt.plot(t, end_prince[N-1:], linewidth=1, label=f"end_prince")
    plt.plot(t, ma5, linewidth=2, label=f"ma{N}")
    # numpy 计算 5日 指数移动平均线
    weights = np.exp(np.linspace(-1., 0., N))
    weights /= weights.sum()
    ema5 = np.convolve(end_prince, weights)[N-1:-N+1]
    print(f"ema5:{ema5}")
    plt.plot(t, ema5, linewidth=5, label=f"ema{N}")
    plt.savefig('./chart.png')  # 保存为PNG文件
    plt.close() 

def test_panda_base():
    """Pandas 基础操作：读取CSV、数据清洗、统计分析、涨跌幅计算"""
    file_name = "./demo.csv"

    # 读取CSV并查看基本信息和统计信息
    df = pd.read_csv(file_name)
    print(df.info())
    print("-------------------")
    print(df.describe())

    # 重命名列名并转换日期格式（统一使用标准OHLCV格式）
    df.columns = ['stock_id', 'date', 'close', 'open', 'high', 'low', 'volume']
    df['date'] = pd.to_datetime(df['date'])
    df["year"] = df['date'].dt.year
    df["month"] = df['date'].dt.month
    print(df)

    # 查找收盘价最小值及其对应记录
    print(f"df['close'].min():{df['close'].min()}")
    print(f"df['close'].idxmin():{df['close'].idxmin()}")
    print(f"loc:{df.loc[df['close'].idxmin()]}")

    # 计算平均收盘价和月度平均价
    print(f"df['close'].mean():{df['close'].mean()}")
    monthly_avg_close_price = df.groupby(['year', 'month'])['close'].mean()
    monthly_avg_open_price = df.groupby(['year', 'month'])['open'].mean()
    print(f"monthly_avg_close_price:{monthly_avg_close_price} ")
    print(f"monthly_avg_open_price:{monthly_avg_open_price} ")

    # 计算价格变动和涨跌幅（相对于下一行）
    df['price_change'] = df['close'].diff()
    df['price_change_ratio'] = df['price_change'] / df['close'].shift(-1) * 100
    print(df)

import mplfinance as mpf
from mpl_finance import candlestick2_ohlc

def test_pandas_kline():
    """使用 matplotlib 绘制基础 K 线图（蜡烛图）"""
    file_name = "./demo.csv"

    # 读取数据并重命名列（统一使用标准OHLCV格式）
    df = pd.read_csv(file_name)
    df.columns = ['stock_id', 'date', 'close', 'open', 'high', 'low', 'volume']

    # 创建图形和坐标轴
    fig = plt.figure()
    axes = fig.add_subplot(111)

    # 绘制 K 线图（红色涨、绿色跌）
    candlestick2_ohlc(ax=axes,
                      opens=df['open'].values,
                      highs=df['high'].values,
                      lows=df['low'].values,
                      closes=df['close'].values,
                      width=0.75,
                      colorup='red',
                      colordown='green',
                      alpha=0.8)

    # 设置图表样式
    plt.xticks(range(len(df.index.values)), df.index.values, rotation=30)
    axes.grid(True)
    plt.title('Stock K-line Chart')
    plt.savefig('./kline_chart.png')
    plt.close()

def test_pandas_kline_volume():
    """使用 mplfinance 绘制带成交量的 K 线图"""
    file_name = "./demo.csv"

    # 读取数据并设置列名（统一使用标准OHLCV格式，mplfinance要求首字母大写）
    df = pd.read_csv(file_name)
    df.columns = ['stock_id', 'date', 'Close', 'Open', 'High', 'Low', 'Volume']
    df = df[['date', 'Close', 'Open', 'High', 'Low', 'Volume']]
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')

    # 配置颜色和样式（红涨绿跌）
    my_color = mpf.make_marketcolors(up='r', down='g', wick='i', edge='i',
                                     volume={'up':'r', 'down':'g'}, ohlc='i')
    my_style = mpf.make_mpf_style(marketcolors=my_color, gridaxis='both', gridstyle='-.')

    # 绘制带成交量的K线图
    mpf.plot(df, type='candle', style=my_style, title='Stock K-line with Volume',
             ylabel='Price', show_nontrading=False, volume=True, ylabel_lower='Volume',
             datetime_format='%Y-%m-%d', xrotation=30, linecolor='#00ff00',
             tight_layout=False, savefig='./kline_volume_chart.png')
    
def test_pandas_kline_EMA():
    """绘制带移动平均线的 K 线图（MA5 和 MA10）"""
    file_name = "./demo.csv"

    # 读取并准备数据（统一使用标准OHLCV格式，mplfinance要求首字母大写）
    df = pd.read_csv(file_name)
    df.columns = ['stock_id', 'date', 'Close', 'Open', 'High', 'Low', 'Volume']
    df = df[['date', 'Close', 'Open', 'High', 'Low', 'Volume']]
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')

    # 配置样式
    my_color = mpf.make_marketcolors(up='r', down='g', wick='i', edge='i',
                                     volume={'up':'r', 'down':'g'}, ohlc='i')
    my_style = mpf.make_mpf_style(marketcolors=my_color, gridaxis='both', gridstyle='-.')

    # 绘制带MA5和MA10的K线图
    mpf.plot(df, type='candle', mav=[5, 10], style=my_style,
             title='Stock K-line with Volume', ylabel='Price', show_nontrading=False,
             volume=True, ylabel_lower='Volume', datetime_format='%Y-%m-%d',
             xrotation=45, linecolor='#00ff00', tight_layout=False,
             savefig='./kline_volume_chart.png')
    
def test_matplt_macd():
    """
    计算 MACD 指标并绘制图表

    MACD 组成：
    1. DIF（快线）：12日 EMA - 26日 EMA
    2. DEA（慢线）：DIF 的 9日 EMA
    3. MACD 柱状图：2 × (DIF - DEA)

    交易信号：
    - 金叉：DIF 上穿 DEA（买入）
    - 死叉：DIF 下穿 DEA（卖出）
    """
    file_name = "./demo.csv"

    # 读取并准备数据（统一使用标准OHLCV格式）
    df = pd.read_csv(file_name)
    df.columns = ['stock_id', 'date', 'close', 'open', 'high', 'low', 'volume']
    df['date'] = pd.to_datetime(df['date'])

    # 计算 MACD 指标
    fastperiod, slowperiod, signalperiod = 12, 26, 9
    ema12 = df['close'].ewm(span=fastperiod, adjust=False).mean()
    ema26 = df['close'].ewm(span=slowperiod, adjust=False).mean()
    df['dif'] = ema12 - ema26
    df['dea'] = df['dif'].ewm(span=signalperiod, adjust=False).mean()
    df['bar'] = 2 * (df['dif'] - df['dea'])
    print(df)

    # 绘制 MACD 指标
    plt.figure()
    df['dea'].plot(label='DEA', color='red')
    df['dif'].plot(label='DIF', color='green')
    plt.legend(loc='best')

    # 绘制柱状图（正值红色，负值绿色）
    pos_bar, pos_index, neg_bar, neg_index = [], [], [], []
    for index, row in df.iterrows():
        if row['bar'] >= 0:
            pos_bar.append(row['bar'])
            pos_index.append(index)
        else:
            neg_bar.append(row['bar'])
            neg_index.append(index)
    plt.bar(pos_index, pos_bar, width=0.5, color='red')
    plt.bar(neg_index, neg_bar, width=0.5, color='green')

    # 设置图表样式
    major_index = df.index[df.index]
    major_xtics = df['date'][df.index]
    plt.xticks(major_index, major_xtics, rotation=30)
    plt.setp(plt.gca().get_xticklabels(), fontsize=8)
    plt.grid(linestyle='-.')
    plt.title('000001 ping an Bank MACD Indicator')
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
    plt.savefig('./macd_chart.png')

def test_matplt_kdj():
    df = pd.read_csv("./demo.csv")
    df.columns = ['stock_id', 'date', 'close', 'open', 'high', 'low', 'volume']
    df['date'] = pd.to_datetime(df['date'])
    low_list = df['low'].rolling(9, min_periods=9).min()
    low_list.fillna(value=df['low'].expanding().min(), inplace=True)
    high_list = df['high'].rolling(9, min_periods=9).max()
    high_list.fillna(value=df['high'].expanding().max(), inplace=True)
    rsv = (df['close'] - low_list) / (high_list - low_list) * 100
    df['k'] = rsv.ewm(com=2).mean()
    df['d'] = df['k'].ewm(com=2).mean()
    df['j'] = 3 * df['k'] - 2 * df['d']
    print(df)
    plt.figure()
    df['k'].plot(label='K', color='red')
    df['d'].plot(label='D', color='yellow')
    df['j'].plot(label='J', color='blue')
    plt.legend(loc='best')

    majoer_index = df.index[df.index]
    major_xtics = df['date'][df.index]
    plt.xticks(majoer_index, major_xtics, rotation=30)
    plt.setp(plt.gca().get_xticklabels(), fontsize=8)

    plt.grid(linestyle='-.')
    plt.title('000001 ping an Bank KDJ Indicator')
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
    plt.savefig('./kdj_chart.png')

if __name__ == "__main__":
    #test_numpy_base()
    #test_numpy_advanced()
    #test_panda_base()
    #test_pandas_kline()
    #test_pandas_kline_volume()
    #test_pandas_kline_EMA()
    #test_matplt_macd()
    test_matplt_kdj()