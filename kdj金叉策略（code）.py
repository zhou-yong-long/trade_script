# -*- coding: gbk -*-
"""
KDJ金叉策略
基于迅投QMT量化交易平台实现的KDJ金叉交易策略
"""

import numpy as np
import pandas as pd
import datetime
import json

# 策略参数
INIT_CAPITAL = 1000000  # 初始资金
MAX_POSITION = 0.5      # 单股最大仓位占比
MAX_HOLDINGS = 5        # 最大持仓数量
STOCK_POOL_SIZE = 1000    # 股票池大小

# 全局变量
formatted_time = ""     # 格式化时间

def timetag_to_datetime(timetag, format="%Y-%m-%d %H:%M:%S"):
    """
    时间戳转换为日期时间格式
    """
    try:
        import time
        timetag = timetag / 1000
        time_local = time.localtime(timetag)
        return time.strftime(format, time_local)
    except:
        return ""

def init(ContextInfo):
    """
    初始化函数
    """
    ContextInfo.capital = INIT_CAPITAL
    ContextInfo.max_position = MAX_POSITION
    ContextInfo.max_holdings = MAX_HOLDINGS
    ContextInfo.stock_pool_size = STOCK_POOL_SIZE
    ContextInfo.accID = 'testS'

    # 初始化变量
    ContextInfo.holdings = {}  # 持仓信息
    
    # 设置回测参数，使用中证2000股票池
    # 修改股票池设置，使用中证2000
    s = ContextInfo.get_stock_list_in_sector('中证2000')
    if not s:
        # 如果无法获取中证2000股票池，则尝试获取其他小盘股指数
        s = ContextInfo.get_stock_list_in_sector('中证1000')
        if not s:
            # 如果仍然无法获取，则使用沪深A股
            s = ContextInfo.get_stock_list_in_sector('沪深A股')
    
    if not s:
        # 如果无法获取股票池，则使用默认标的
        s = [ContextInfo.stockcode + '.' + ContextInfo.market]
    else:
        # 取前STOCK_POOL_SIZE只股票
        s = s[:ContextInfo.stock_pool_size]
    
    ContextInfo.set_universe(s)
    
    print("策略初始化完成，标的股票数量: ", len(s))
    
def handlebar(ContextInfo):
    """
    主要策略逻辑函数，每个K线周期执行一次
    """
    global formatted_time
    
    # 获取当前时间
    current_time = ContextInfo.get_bar_timetag(ContextInfo.barpos)
    formatted_time = timetag_to_datetime(current_time)
    
    print("执行策略，当前时间: ", formatted_time, "原始时间标签: ", current_time, "K线位置: ", ContextInfo.barpos)
    
    # 更新持仓信息
    update_positions(ContextInfo)
    
    buy_candidates = [];

    # 如果持仓未满，需要计算kdj指标
    if len(ContextInfo.holdings) < ContextInfo.max_holdings:
        # 选股逻辑：基于周线KDJ金叉买入
        buy_candidates = select_kdj_golden_cross_stocks(ContextInfo)
    
    print("候选买入股票数量: ", len(buy_candidates))
    
    # 根据选股结果进行交易
    execute_trades(ContextInfo, buy_candidates, current_time)
    
    print("策略执行完成，当前持仓数量: ", len(ContextInfo.holdings))

def calculate_kdj(high_prices, low_prices, close_prices, N=9, M1=3, M2=3):
    """
    计算KDJ指标
    """
    if len(high_prices) < N:
        return None, None, None
    
    # 计算RSV未成熟随机值
    rsv = []
    for i in range(len(close_prices)):
        if i < N - 1:
            rsv.append(0)
        else:
            high_period = high_prices[i - N + 1:i + 1]
            low_period = low_prices[i - N + 1:i + 1]
            ct = close_prices[i]
            ln = min(low_period)
            hn = max(high_period)
            if hn == ln:
                rsv.append(0)
            else:
                rsv.append((ct - ln) / (hn - ln) * 100)
    
    # 计算K值
    k_values = [50]  # 初始K值设为50
    for i in range(1, len(rsv)):
        k = (M1 - 1) / M1 * k_values[-1] + 1 / M1 * rsv[i]
        k_values.append(k)
    
    # 计算D值
    d_values = [50]  # 初始D值设为50
    for i in range(1, len(k_values)):
        d = (M2 - 1) / M2 * d_values[-1] + 1 / M2 * k_values[i]
        d_values.append(d)
    
    # 计算J值
    j_values = []
    for i in range(len(k_values)):
        j = 3 * k_values[i] - 2 * d_values[i]
        j_values.append(j)
    
    return k_values, d_values, j_values

def select_kdj_golden_cross_stocks(ContextInfo):
    """
    选择KDJ金叉的股票（周线线级别）
    """
    candidates = []
    
    # 获取所有股票
    stocks = ContextInfo.get_universe()
    print("股票池数量: ", len(stocks))
    
    # 限制处理股票数量，避免处理时间过长
    stocks = stocks[:1000] 
    
    for stock in stocks:
        try:
            # 检查股票是否已经涨停，如果涨停则跳过
            try:
                # 获取当前价格和昨日收盘价来判断是否涨停
                current_prices = ContextInfo.get_history_data(1, '1d', 'close')
                yesterday_prices = ContextInfo.get_history_data(2, '1d', 'close')
                
                if (not current_prices) or (not yesterday_prices):
                    continue
                    
                if stock not in current_prices or stock not in yesterday_prices:
                    continue
                    
                if len(current_prices[stock]) < 1 or len(yesterday_prices[stock]) < 2:
                    continue
                
                current_price = current_prices[stock][-1]
                yesterday_close = yesterday_prices[stock][-2]
                
                # 计算涨跌幅
                if yesterday_close > 0:
                    price_change_ratio = (current_price - yesterday_close) / yesterday_close
                    
                    # 判断是否接近涨停（考虑浮点数精度问题，设置一个略微宽松的阈值）
                    # A股主板涨停幅度为10%，ST股为5%
                    # 通过股票名称判断是否为ST股
                    stock_name = ContextInfo.get_stock_name(stock)
                    is_st = 'ST' in stock_name if stock_name else False
                    limit_up_threshold = 0.049 if is_st else 0.099  # 略微宽松的涨停判定阈值
                    
                    if price_change_ratio >= limit_up_threshold:
                        print("股票 {} 已经涨停或接近涨停，跳过".format(stock))
                        continue
            except Exception as e:
                print("检查股票是否涨停时出错: ", stock, str(e))
                # 出错时继续处理，不跳过该股票
                pass
            
            # 获取周线线数据
            high_prices = ContextInfo.get_history_data(20, '1w', 'high')  # 20天的最高价
            low_prices = ContextInfo.get_history_data(20, '1w', 'low')    # 20天的最低价
            close_prices = ContextInfo.get_history_data(20, '1w', 'close') # 20天的收盘价
            
            if not all([high_prices, low_prices, close_prices]):
                print("无法获取周线数据")
                continue
                
            if stock not in high_prices or stock not in low_prices or stock not in close_prices:
                print("股票数据缺失")
                continue
                
            if len(high_prices[stock]) < 3 or len(low_prices[stock]) < 3 or len(close_prices[stock]) < 3:
                print("历史日线数据不足")
                continue
            
            # 计算KDJ指标
            k_values, d_values, j_values = calculate_kdj(
                high_prices[stock], 
                low_prices[stock], 
                close_prices[stock]
            )
            
            if k_values is None or len(k_values) < 3:
                print("KDJ计算失败")
                continue
            
            # 判断是否出现金叉（K线上穿D线）
            # 前一周K<D 且 当前K>D 且 K和D都在20以下（低位金叉）
            prev_k, curr_k = k_values[-2], k_values[-1]
            prev_d, curr_d = d_values[-2], d_values[-1]
            
            is_golden_cross = (prev_k <= prev_d) and (curr_k > curr_d) and (curr_d < 20)
            
            if is_golden_cross:
                current_price = close_prices[stock][-1]
                candidates.append({
                    'stock': stock,
                    'price': current_price,
                    'k': curr_k,
                    'd': curr_d,
                    'j': j_values[-1]
                })
                print("加入候选买入股票: ", stock, "K:", curr_k, "D:", curr_d, "J:", j_values[-1])
                
                # 当选出来的股票数量已经达到最大持仓数量时，提前结束选股
                if len(candidates) >= ContextInfo.max_holdings:
                    print("已选出足够数量的股票，提前结束选股")
                    break
        except Exception as e:
            print("处理股票时发生错误: ", stock, str(e))
            import traceback
            traceback.print_exc()
            continue  # 忽略异常股票
    
    print("最终候选买入股票: "+json.dumps(candidates))
    return candidates

def execute_trades(ContextInfo, buy_candidates, current_time):
    """
    执行交易操作
    """
    global formatted_time
    print("执行交易操作，当前时间: ", formatted_time)
    # 先处理卖出信号
    handle_sell_orders(ContextInfo, current_time)
    
    # 处理买入信号
    handle_buy_orders(ContextInfo, buy_candidates, current_time)

def handle_sell_orders(ContextInfo, current_time):
    """
    处理卖出订单 - 基于KDJ死叉或J值大于100（周线级别）
    """
    global formatted_time
    print("处理卖出订单，当前时间: ", formatted_time, "当前持仓数量: ", len(ContextInfo.holdings))
    for stock in list(ContextInfo.holdings.keys()):
        try:
            # 获取日线数据
            high_prices = ContextInfo.get_history_data(20, '1w', 'high')
            low_prices = ContextInfo.get_history_data(20, '1w', 'low')
            close_prices = ContextInfo.get_history_data(20, '1w', 'close')
            
            if not all([high_prices, low_prices, close_prices]):
                continue
                
            if stock not in high_prices or stock not in low_prices or stock not in close_prices:
                continue
                
            if len(high_prices[stock]) < 3 or len(low_prices[stock]) < 3 or len(close_prices[stock]) < 3:
                continue
            
            # 计算KDJ指标
            k_values, d_values, j_values = calculate_kdj(
                high_prices[stock], 
                low_prices[stock], 
                close_prices[stock]
            )
            
            if k_values is None or len(k_values) < 3:
                continue
            
            # 判断是否出现死叉（K线下穿D线）
            # 前一日K>D 且 当前K<D 且 K和D都在80以上（高位死叉）
            prev_k, curr_k = k_values[-2], k_values[-1]
            prev_d, curr_d = d_values[-2], d_values[-1]
            curr_j = j_values[-1]
            
            is_dead_cross = (prev_k >= prev_d) and (curr_k < curr_d) and (curr_d > 80)
            
            # J值大于100也需要卖出
            is_high_j = curr_j > 100
            
            # 如果满足卖出条件，则卖出
            if is_dead_cross or is_high_j:
                # 获取当前价格
                current_price = ContextInfo.get_close_price(
                    stock.split('.')[1],  # 市场
                    stock.split('.')[0],  # 股票代码
                    current_time,
                    86400000  # 1日周期
                )
                
                if current_price <= 0:
                    continue
                
                order_volume = ContextInfo.holdings[stock]
                if order_volume > 0:
                    # 卖出所有持仓，使用回测标准函数
                    print("时间:", formatted_time, "准备卖出股票:", stock, "数量:", order_volume, "价格:", current_price)
                    print("卖出原因: 死叉=", is_dead_cross, "J值过高=", is_high_j, "J值=", curr_j)
                    order_shares(stock, -order_volume, ContextInfo, ContextInfo.accID)
                    del ContextInfo.holdings[stock]
                    print("时间:", formatted_time, "卖出: ", stock)
        except Exception as e:
            print("卖出订单处理错误: ", stock, str(e))
            import traceback
            traceback.print_exc()
            pass

def handle_buy_orders(ContextInfo, candidates, current_time):
    """
    处理买入订单（日线级别）
    """
    global formatted_time
    print("处理买入订单，当前时间: ", formatted_time, "候选股票数量: ", len(candidates))
    # 当前持仓数量
    current_holdings = len(ContextInfo.holdings)
    
    # 如果持仓已满，不继续买入
    if current_holdings >= ContextInfo.max_holdings:
        print("持仓已满，不继续买入")
        return
    
    # 计算可买入的股票数量
    available_slots = ContextInfo.max_holdings - current_holdings
    
    # 在候选股票中选择符合买入条件的股票
    for i, candidate in enumerate(candidates):
        stock = candidate['stock']
        
        # 如果该股票已在持仓中，跳过
        if stock in ContextInfo.holdings:
            continue
        
        # 如果已达到最大持仓数量，停止买入
        if available_slots <= 0:
            break
            
        try:
            # 获取当前价格
            current_price = candidate['price']
            
            # 确保价格有效
            if current_price <= 0:
                continue
                
            # 计算买入金额（根据仓位控制）
            available_capital = ContextInfo.capital * ContextInfo.max_position
            
            # 计算买入数量（手）
            volume = int(available_capital / (current_price * 100)) * 100
            
            print("计算买入量，可用资金:", available_capital, "当前价格:", current_price, "计算量:", volume)
            
            if volume > 0:
                # 使用收盘价买入
                print("时间:", formatted_time, "准备下单买入: ", stock, "数量: ", volume, "价格: ", current_price)
                order_shares(stock, volume, ContextInfo, ContextInfo.accID)
                
                # 记录持仓
                ContextInfo.holdings[stock] = volume
                available_slots -= 1
                print("时间:", formatted_time, "成功买入: ", stock, "数量: ", volume, "价格: ", current_price)
        except Exception as e:
            print("买入订单处理错误: ", stock, str(e))
            import traceback
            traceback.print_exc()
            pass

def update_positions(ContextInfo):
    """
    更新持仓信息
    """
    pass