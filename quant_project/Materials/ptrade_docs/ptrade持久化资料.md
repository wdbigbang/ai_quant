下面给你一份**可直接复制到PTrade运行**的「手动文件持久化」完整示例，包含：路径获取、目录创建、JSON/CSV/Pickle 三种常用格式的读写、策略重启自动加载、日志打印说明。

---

## 一、核心前提（必须遵守）
1. **只能写到 `get_research_path()` 下面**（平台给你的专属云盘，回测/实盘/研究通用）
2. 禁止写绝对路径（如 `/home/xxx`、`C:\`），新版会报错
3. 用平台提供的 `create_dir()` 创建子目录，不要用 `os.makedirs`
4. 策略重启后：**g 自动持久化会恢复；手动文件需要你自己 load**

---

## 二、完整可运行代码（复制即用）
```python
# -*- coding: utf-8 -*-
import json
import pickle
import pandas as pd
from ptrade.api import get_research_path, create_dir, log

# -------------------------- 1. 路径与目录配置 --------------------------
def get_my_data_dir():
    """返回你专属的数据目录路径：/home/fly/notebook/my_strategy_data/"""
    base_path = get_research_path()  # 平台根目录
    data_dir = base_path + "my_strategy_data/"
    create_dir("my_strategy_data")   # 不存在则创建，必须用这个API
    return data_dir

# -------------------------- 2. JSON 读写（推荐：配置/小状态） --------------------------
def save_json(data, filename="state.json"):
    """保存字典/列表到JSON"""
    path = get_my_data_dir() + filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"[JSON保存成功] {path}")

def load_json(filename="state.json"):
    """从JSON加载，不存在返回空字典"""
    path = get_my_data_dir() + filename
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        log.info(f"[JSON加载成功] {path}")
        return data
    except Exception as e:
        log.info(f"[JSON不存在/加载失败] {e}，返回空字典")
        return {}

# -------------------------- 3. CSV 读写（推荐：交易记录/日志） --------------------------
def save_csv(df, filename="trades.csv", mode="a"):
    """
    DataFrame 保存为CSV
    :param mode: a=追加（日志），w=覆盖
    """
    path = get_my_data_dir() + filename
    if mode == "a":
        # 追加：不写header
        df.to_csv(path, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        # 覆盖：写header
        df.to_csv(path, mode="w", header=True, index=False, encoding="utf-8-sig")
    log.info(f"[CSV保存成功] {path}")

def load_csv(filename="trades.csv"):
    """加载CSV为DataFrame"""
    path = get_my_data_dir() + filename
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
        log.info(f"[CSV加载成功] 共{len(df)}行")
        return df
    except Exception as e:
        log.info(f"[CSV不存在/加载失败] {e}，返回空DataFrame")
        return pd.DataFrame()

# -------------------------- 4. Pickle 读写（推荐：复杂对象/模型） --------------------------
def save_pickle(obj, filename="model.pkl"):
    """保存任意可序列化对象（如训练好的模型、复杂字典）"""
    path = get_my_data_dir() + filename
    with open(path, "wb") as f:
        pickle.dump(obj, f)
    log.info(f"[Pickle保存成功] {path}")

def load_pickle(filename="model.pkl"):
    """加载Pickle对象，不存在返回None"""
    path = get_my_data_dir() + filename
    try:
        with open(path, "rb") as f:
            obj = pickle.load(f)
        log.info(f"[Pickle加载成功] {path}")
        return obj
    except Exception as e:
        log.info(f"[Pickle不存在/加载失败] {e}，返回None")
        return None

# -------------------------- 5. 策略初始化：重启自动加载 --------------------------
def initialize(context):
    g.security = "000001.SS"
    set_universe(g.security)

    # 重启后：手动加载之前保存的状态
    g.my_state = load_json("state.json")       # 加载配置/状态
    g.trade_log = load_csv("trades.csv")        # 加载历史交易
    g.my_model = load_pickle("model.pkl")       # 加载复杂对象

    # 初始化默认值（首次运行时）
    if not g.my_state:
        g.my_state = {
            "total_profit": 0.0,
            "trade_count": 0,
            "last_buy_price": None
        }
        save_json(g.my_state, "state.json")

    log.info("=== 初始化完成，手动持久化已加载 ===")

# -------------------------- 6. 主逻辑：每次交易后保存 --------------------------
def handle_data(context, data):
    # 示例：模拟一次交易，更新状态并保存
    if context.portfolio.available_cash > 10000:
        # 下单逻辑...
        order(g.security, 100)

        # 1. 更新状态并保存JSON
        g.my_state["trade_count"] += 1
        g.my_state["last_buy_price"] = data[g.security].close
        save_json(g.my_state, "state.json")

        # 2. 记录交易日志（追加CSV）
        new_trade = pd.DataFrame({
            "time": [context.now.strftime("%Y-%m-%d %H:%M:%S")],
            "code": [g.security],
            "price": [data[g.security].close],
            "volume": [100]
        })
        save_csv(new_trade, "trades.csv", mode="a")

        # 3. 保存一个复杂对象示例（Pickle）
        complex_obj = {"name": "my_strategy", "params": [0.5, 1.2, 3.0]}
        save_pickle(complex_obj, "model.pkl")

# -------------------------- 7. 盘后：最终保存一次 --------------------------
def after_trading_end(context, data):
    # 收盘再落盘一次，防止当天意外中断
    save_json(g.my_state, "state.json")
    log.info("=== 盘后持久化完成 ===")
```

---

## 三、三种格式怎么选（场景建议）
- **JSON**：配置参数、简单状态（计数器、开关、最后价格）  
  ✅ 人类可读、跨语言、适合小数据
- **CSV**：交易日志、K线记录、对账数据  
  ✅ 表格格式、Excel可直接打开、适合日志流水
- **Pickle**：复杂字典、训练模型、自定义类实例  
  ✅ 支持任意Python对象、读写快、适合模型/中间结果

---

## 四、怎么验证是否生效
1. 运行策略 → 看日志：
   ```
   [JSON保存成功] /home/fly/notebook/my_strategy_data/state.json
   [CSV保存成功] /home/fly/notebook/my_strategy_data/trades.csv
   ```
2. 左侧「研究」→ 进入 `my_strategy_data` 目录，能看到三个文件
3. **重启策略**：日志会打印「加载成功」，且 `g.my_state` 是上次保存的值

---

## 五、常见坑（避坑）
1. ❌ 不要写死 `/home/fly/notebook/` → 用 `get_research_path()`
2. ❌ 不要用 `os.makedirs` → 用 `create_dir("文件夹名")`
3. ❌ 不要保存「无法序列化对象」（数据库连接、文件句柄、socket）→ 会报错
4. ⚠️ 回测→实盘：文件是**隔离的**，回测数据不会自动到实盘，需手动上传文件到实盘研究目录

---


结论先说：**默认是“共享同一个研究目录”，文件会互相看见、互相覆盖；但你只要给每个项目建一个独立子目录，就能做到完全隔离、绝不混淆。**

下面分两层讲清楚：

---

## 一、PTrade 的文件空间是“账户级共享”，不是“项目隔离”
- 所有策略/项目，`get_research_path()` 拿到的**根路径完全一样**：
  ```
  /home/fly/notebook/
  ```
 
- 你在策略A写：
  ```python
  save_json(..., "state.json")
  ```
  策略B也能直接读到这个 `state.json`，**默认是互通、互相影响的**。
- 平台只对：
  - **g 对象自动持久化**：每个策略独立，互不干扰
  - **实盘 vs 回测**：文件目录隔离

但**不同策略之间，文件系统是打通的**。

---

## 二、怎么让两个项目的手动文件完全独立（推荐做法）
给每个项目分配**专属子目录**，路径隔离，自然不会混。

### 示例：项目 A、项目 B
```python
# 项目 A 专用路径
def get_project_a_dir():
    base=get_research_path()
    dir_a=base + "project_a/"
    create_dir("project_a")
    return dir_a

# 项目 B 专用路径
def get_project_b_dir():
    base=get_research_path()
    dir_b=base + "project_b/"
    create_dir("project_b")
    return dir_b
```

- 项目 A 保存：
  ```python
  path=get_project_a_dir() + "state.json"
  ```
- 项目 B 保存：
  ```python
  path=get_project_b_dir() + "state.json"
  ```
物理上是两个不同文件：
```
/home/fly/notebook/project_a/state.json
/home/fly/notebook/project_b/state.json
```
**彻底隔离，永不混淆。**

---

## 三、你现在的风险（如果不建子目录）
- 两个策略都用：
  ```
  state.json
  trades.csv
  ```
  会**互相覆盖、互相读对方的数据**，造成：
  - 计数错乱
  - 交易日志混在一起
  - 重启后状态异常

---

## 四、一句话总结
- **默认：同账户下所有策略共享一个文件目录，会互相干扰。**
- **正确：每个项目建独立子目录，文件完全隔离、安全。**
