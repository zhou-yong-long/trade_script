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
MAX_POSITION = 0.2      # 单股最大仓位占比
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

def log_message(*args):
    """
    带时间戳的日志打印函数
    """
    global formatted_time
    timestamp = formatted_time if formatted_time else datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = " ".join(str(arg) for arg in args)
    print("[{}] {}".format(timestamp, message))

def init(ContextInfo):
    """
    初始化函数
    """
    ContextInfo.max_position = MAX_POSITION
    ContextInfo.max_holdings = MAX_HOLDINGS
    ContextInfo.stock_pool_size = STOCK_POOL_SIZE
    ContextInfo.accID = 'testS'

    # 初始化变量
    init_position_manager(ContextInfo)  # 持仓信息
    
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
    
    log_message("策略初始化完成，标的股票数量: ", len(s))
    
def handlebar(ContextInfo):
    """
    主要策略逻辑函数，每个K线周期执行一次
    """
    global formatted_time
    
    # 获取当前时间
    current_time = ContextInfo.get_bar_timetag(ContextInfo.barpos)
    formatted_time = timetag_to_datetime(current_time)
    
    log_message("执行策略，原始时间标签: ", current_time, "K线位置: ", ContextInfo.barpos)
    
    update_positions(ContextInfo, ContextInfo.accID)

    buy_candidates = [];

    # 如果持仓未满，需要计算kdj指标
    if len(ContextInfo.holdings) < ContextInfo.max_holdings and ContextInfo.enable_flag:
        # 选股逻辑：基于周线KDJ金叉买入
        buy_candidates = select_kdj_golden_cross_stocks(ContextInfo)
        log_message("候选买入股票数量: ", len(buy_candidates))
    
    # 根据选股结果进行交易
    execute_trades(ContextInfo, buy_candidates, current_time)
    
    log_message("策略执行完成\n")

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
                        continue
            except Exception as e:
                log_message("检查股票是否涨停时出错: ", stock, str(e))
                # 出错时继续处理，不跳过该股票
                pass
            
            # 获取周线线数据
            high_prices = ContextInfo.get_history_data(20, '1w', 'high')  # 20天的最高价
            low_prices = ContextInfo.get_history_data(20, '1w', 'low')    # 20天的最低价
            close_prices = ContextInfo.get_history_data(20, '1w', 'close') # 20天的收盘价
            
            if not all([high_prices, low_prices, close_prices]):
                log_message("无法获取周线数据")
                continue
                
            if stock not in high_prices or stock not in low_prices or stock not in close_prices:
                log_message("股票数据缺失")
                continue
                
            if len(high_prices[stock]) < 3 or len(low_prices[stock]) < 3 or len(close_prices[stock]) < 3:
                log_message("历史日线数据不足")
                continue
            
            # 计算KDJ指标
            k_values, d_values, j_values = calculate_kdj(
                high_prices[stock], 
                low_prices[stock], 
                close_prices[stock]
            )
            
            if k_values is None or len(k_values) < 3:
                log_message("KDJ计算失败")
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
                log_message("加入候选买入股票: ", stock, "K:", curr_k, "D:", curr_d, "J:", j_values[-1])
                
                # 当选出来的股票数量已经达到最大持仓数量时，提前结束选股
                if len(candidates) >= ContextInfo.max_holdings:
                    log_message("已选出足够数量的股票，提前结束选股")
                    break
        except Exception as e:
            log_message("处理股票时发生错误: ", stock, str(e))
            import traceback
            traceback.print_exc()
            continue  # 忽略异常股票
    
    log_message("最终候选买入股票: "+json.dumps(candidates))
    return candidates

def execute_trades(ContextInfo, buy_candidates, current_time):
    """
    执行交易操作
    """
    global formatted_time
    log_message("执行交易操作")
    # 先处理卖出信号
    handle_sell_orders(ContextInfo, current_time)
    
    # 处理买入信号
    handle_buy_orders(ContextInfo, buy_candidates, current_time)

def handle_sell_orders(ContextInfo, current_time):
    """
    处理卖出订单 - 基于KDJ死叉或J值大于100（周线级别）
    """
    global formatted_time
    log_message("处理卖出订单，当前持仓数量: ", len(ContextInfo.holdings))
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
            log_message("判断死叉: ", stock, "K:", curr_k, "D:", curr_d, "J:", j_values[-1])
            is_dead_cross = (prev_k >= prev_d) and (curr_k < curr_d) and (curr_d > 80)
            
            # J值大于100也需要卖出
            is_high_j = curr_j > 100
            
            # 如果满足卖出条件，则卖出
            if is_dead_cross or is_high_j:
                order_volume = ContextInfo.holdings[stock].available_volume
                if order_volume > 0:
                    # 卖出所有持仓，使用回测标准函数
                    log_message("卖出原因: 死叉=", is_dead_cross, "J值过高=", is_high_j, "J值=", curr_j)
                    order_shares(stock, -order_volume, ContextInfo, ContextInfo.accID)
                    del ContextInfo.holdings[stock]
                    log_message("卖出: ", stock)
        except Exception as e:
            log_message("卖出订单处理错误: ", stock, str(e))
            import traceback
            traceback.print_exc()
            pass

def handle_buy_orders(ContextInfo, candidates, current_time):
    """
    处理买入订单（日线级别）
    """
    global formatted_time
    log_message("处理买入订单，候选股票数量: ", len(candidates))
    # 当前持仓数量
    current_holdings = len(ContextInfo.holdings)
    
    # 如果持仓已满，不继续买入
    if current_holdings >= ContextInfo.max_holdings:
        log_message("持仓已满，不继续买入")
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
            available_capital = ContextInfo.available_amount * ContextInfo.max_position
            
            # 计算买入数量（手）
            volume = int(available_capital / (current_price * 100)) * 100
            
            log_message("计算买入量，可用资金:", available_capital, "当前价格:", current_price, "计算量:", volume)
            
            if volume > 0:
                # 使用收盘价买入
                log_message("准备下单买入: ", stock, "数量: ", volume, "价格: ", current_price)
                order_shares(stock, volume, ContextInfo, ContextInfo.accID)
                
                available_slots -= 1
                log_message("成功买入: ", stock, "数量: ", volume, "价格: ", current_price)
        except Exception as e:
            log_message("买入订单处理错误: ", stock, str(e))
            import traceback
            traceback.print_exc()
            pass

def init_position_manager(ContextInfo):
    """
    初始化持仓与资金管理器
    """
    # 持仓信息：记录每只股票的持仓信息
    # 格式: {股票代码: {'volume': 持仓股数, 'price': 成本价, 'total_amount': 持仓金额}}
    ContextInfo.holdings = {}
    
    # 资金信息
    ContextInfo.total_amount = 0       # 总金额
    ContextInfo.available_amount = 0   # 可用金额
    ContextInfo.stock_amount = 0       # 持仓总金额
    
    # 买入标志：判断当日是否可以买入
    ContextInfo.enable_flag = True     # 默认可以买入

def update_positions(ContextInfo, account_id):
    """
    更新持仓数据
    从交易系统获取最新的持仓和资金信息
    
    参数:
    ContextInfo: 上下文信息对象
    account_id: 账户ID
    """
    try:
        # 获取持仓数据
        positions = get_trade_detail_data(account_id, 'stock', 'position')
        # 更新持仓信息
        ContextInfo.holdings = {}
        
        for position in positions:
            stock_code = position.m_strInstrumentID + '.' + position.m_strExchangeID
            volume = position.m_nVolume
            price = position.m_dOpenPrice
            total_amount = position.m_dInstrumentValue
            available_volume = position.m_nCanUseVolume
            
            ContextInfo.holdings[stock_code] = {
                'volume': volume,
                'price': price,
                'available_volume': available_volume,
                'total_amount': total_amount
            }
            
        # 获取账户资金数据
        accounts = get_trade_detail_data(account_id, 'stock', 'account')
        if accounts:
            account = accounts[0]  # 取第一个账户
            ContextInfo.total_amount = account.m_dBalance          # 总资产
            ContextInfo.available_amount = account.m_dAvailable    # 可用资金
            ContextInfo.stock_amount = account.m_dInstrumentValue  # 持仓总金额
            
        # 更新买入标志
        update_buy_flag(ContextInfo)
        
        print_position_info(ContextInfo)
    except Exception as e:
        log_message(f"更新持仓数据时出错: {e}")

def update_buy_flag(ContextInfo):
    """
    更新是否可以买入的标志
    判断逻辑：持仓金额低于总金额的80%
    """
    try:
        if ContextInfo.total_amount <= 0:
            ContextInfo.enable_flag = False
        else:
            # 计算持仓金额占总金额的比例
            ratio = ContextInfo.stock_amount / ContextInfo.total_amount
            # 如果比例低于80%，则可以继续买入
            ContextInfo.enable_flag = (ratio < 0.8)
    except Exception as e:
        log_message("更新买入标志时出错: ", str(e))
        ContextInfo.enable_flag = False

def print_position_info(ContextInfo):
    """
    打印持仓和资金信息
    """
    global formatted_time
    
    # 拼接完整的消息字符串
    message_lines = ["=" * 50]
    message_lines.append("持仓信息:")
    for stock_code, info in ContextInfo.holdings.items():
        # 修正：将 info 中的字段作为独立参数传入 format
        message_lines.append("股票代码: {}, 持仓股数: {}, 成本价: {:.2f}, 持仓金额: {:.2f}".format(
            stock_code, 
            info['volume'], 
            info['price'], 
            info['total_amount']
        ))
    
    message_lines.append("\n资金信息:")
    message_lines.append("总资产: {:.2f}".format(ContextInfo.total_amount))
    message_lines.append("可用资金: {:.2f}".format(ContextInfo.available_amount))
    message_lines.append("持仓总金额: {:.2f}".format(ContextInfo.stock_amount))
    message_lines.append("是否可以买入: {}".format(ContextInfo.enable_flag))
    message_lines.append("=" * 50)
    
    # 使用统一的打印方法打印完整消息
    log_message("\n".join(message_lines))
