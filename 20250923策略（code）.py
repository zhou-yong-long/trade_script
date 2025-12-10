# -*- coding: gbk -*-
# 20250923策略 - 基于迅投QMT平台的量化交易策略
# 实现选股、买入决策、自动做T、止盈止损、板块轮动和避险机制等完整功能

import numpy as np
import pandas as pd
import time
import datetime
import json
import os

# 定义主要板块映射 - 全局变量
sectors = {
    # 大金融
    '银行': 'SW1银行',  # 申万一级行业
    '非银金融': 'SW1非银金融',  # 申万一级行业（包含证券、保险、多元金融）
    
    # 大消费
    '消费': '上证消费',  # 或更具体的"白酒"、"饮料乳品"等，食品饮料是申万一级
    '旅游': 'SW1社会服务',  # 申万一级行业（包含旅游及景区、酒店餐饮）
    '汽车': 'SW1汽车',  # 申万一级行业
    '地产': 'SW1房地产',  # 申万一级行业
    
    # 科技成长
    '半导体': 'SW2半导体',  # 申万二级行业（属于电子）
    '芯片': '芯片概念',  # 通常与半导体同义
    '消费电子': '消费电子',  # 申万三级行业（属于电子）
    '互联网': '互联网',  # 或更广泛的"传媒"，互联网电商是申万三级（属于传媒）
    '游戏': 'SW2游戏',  # 申万三级行业（属于传媒）
    'ai': '人工智能',  # 常见概念板块，非标准行业
    '计算机': 'SW1计算机',  # 申万一级行业
    '软件': 'SW2软件开发',  # 申万二级行业（属于计算机）
    '通信': 'SW1通信',  # 申万一级行业
    
    # 高端制造
    '制造': 'SW1机械设备',  # 或"机械设备"，电力设备是申万一级，高端制造常聚焦于此
    '电池': 'SW2电池',  # 申万二级行业（属于电力设备）
    '机器人': '机器人概念',  # 申万二级行业（属于机械设备）
    '军工': 'SW1国防军工',  # 申万一级行业
    
    # 周期资源
    '有色金属': 'SW1有色金属',  # 申万一级行业
    '钢铁': 'SW1钢铁',  # 申万一级行业
    '石油': 'SW1石油石化',  # 申万一级行业
    '煤炭': 'SW1煤炭',  # 申万一级行业
    '化工': 'SW1基础化工',  # 申万一级行业
    '电力': 'SW1电力设备',
    '农业': 'SW1农林牧渔',
    
    # 医药
    '医药': 'SW1医药生物',  # 申万一级行业
    
    # 其他公共事业、综合等
    '公用事业': 'SW1公用事业',  # 申万一级行业
    '交通': 'SW1交通运输',  # 申万一级行业
    
    # 概念类 (这些是主题/概念，而非严格行业)
    '社保': '社保重仓',  
    '基金': '基金重仓',
    '增持回购': '增持回购',
    '红利': '红利指数',  # 概念板块，高股息率股票
}

# 全局变量存储当前日期
current_date = ""

# 全局变量存储沪深300指数20日均线状态
hs300_ma20_condition = False


def calculate_start_date(end_date_str, count, period='1d'):
    """
    根据结束日期和count计算开始日期
    :param end_date_str: 结束日期字符串，格式为'YYYY-MM-DD'
    :param count: 需要的数据条数
    :param period: 周期类型
    :return: 开始日期字符串，格式为'YYYYMMDD'
    """
    try:
        if not end_date_str:
            return ""
            
        # 解析结束日期
        end_date = datetime.datetime.strptime(end_date_str.split(' ')[0], '%Y-%m-%d')
        
        # 根据周期类型计算开始日期
        if period == '1d':
            # 日线数据，需要count个交易日
            start_date = end_date - datetime.timedelta(days=count * 1.5)  # 多预留一些天数考虑周末和节假日
        elif period == '120m':
            # 120分钟线，大约每天4根K线，需要count根K线
            days_needed = count // 4 + 1
            start_date = end_date - datetime.timedelta(days=days_needed)
        elif period == '15m':
            # 15分钟线，大约每天20根K线，需要count根K线
            days_needed = count // 20 + 1
            start_date = end_date - datetime.timedelta(days=days_needed)
        elif period == '5m':
            # 5分钟线，大约每天48根K线，需要count根K线
            days_needed = count // 48 + 1
            start_date = end_date - datetime.timedelta(days=days_needed)
        else:
            # 默认按照日线处理
            start_date = end_date - datetime.timedelta(days=count * 1.5)
            
        return start_date.strftime('%Y%m%d')
    except Exception as e:
        print("[{}] 计算开始日期异常: {}".format(current_date, str(e)))
        return ""


def init(ContextInfo):
    """
    策略初始化函数
    """
    # 设置策略参数
    ContextInfo.portfolio_size = 5  # 持仓股票数量
    ContextInfo.max_position_ratio = 0.1  # 单只股票最大仓位
    ContextInfo.stop_loss = 0.03  # 单票最大亏损3%
    ContextInfo.take_profit = 0.05  # 浮动止盈点5%
    ContextInfo.drawdown_threshold = 0.02  # 回撤2%止盈
    ContextInfo.max_hold_days = 5  # 最大持仓天数
    ContextInfo.t_threshold = 0.008  # 做T幅度阈值0.8%
    ContextInfo.t_stop_loss = 0.015  # 做T止损点1.5%
    
    # 初始化变量
    ContextInfo.selected_stocks = []  # 选股池
    ContextInfo.position_info = {}  # 持仓信息
    ContextInfo.t_holdings = {}  # 做T持仓信息
    ContextInfo.sector_heat = {}  # 板块热度
    ContextInfo.last_trade_time = {}  # 最后交易时间
    ContextInfo.market_risk_level = 0  # 市场风险等级
    
    # 设置基准
    ContextInfo.benchmark = "000300.SH"  # 沪深300指数
    
    # 日志记录
    print("策略初始化完成")

def handlebar(ContextInfo):
    """
    主要处理函数，每个K线周期执行一次
    """
    try:
        # 1. 获取实时行情数据
        current_index = ContextInfo.barpos
        current_time = ContextInfo.get_bar_timetag(current_index)
        global current_date
        current_date = timetag_to_datetime(current_time, '%Y-%m-%d %H:%M:%S')
        
        # 记录日志
        print("[{}] 开始执行策略，时间: {}, 当前索引: {}".format(current_date, current_date, current_index))
        
        # 每天检查一次沪深300指数20日均线状态
        global hs300_ma20_condition
        hs300_ma20_condition = check_hs300_ma20_condition(ContextInfo)
        print("[{}] 沪深300指数20日均线状态: {}".format(current_date, hs300_ma20_condition))
        
        # 2. 风险评估
        risk_check(ContextInfo)
        
        # 3. 板块轮动分析
        sector_analysis(ContextInfo)
        
        # 4. 选股逻辑执行 - 进一步优化执行条件
        # 为了确保策略能正常进入选股逻辑，我们增加多种触发条件：
        # 1) 第一次运行时执行选股
        # 2) 每隔10个周期执行一次选股
        # 3) 如果当前未持有任何股票，也执行选股
        should_select_stocks = False
        
        # 条件1: 第一次运行
        if current_index == 0:
            should_select_stocks = True
            print("[{}] 首次运行，执行选股逻辑".format(current_date))
        
        # 条件2: 每隔10个周期
        elif current_index % 10 == 0:
            should_select_stocks = True
            print("[{}] 按周期执行选股逻辑，当前索引: {}".format(current_date, current_index))
        
        # 条件3: 检查当前持仓，如果未持有股票也执行选股
        else:
            current_positions = get_holdings(ContextInfo, "STOCK")
            if not current_positions:  # 没有持仓
                should_select_stocks = True
                print("[{}] 当前无持仓，执行选股逻辑".format(current_date))
        
        if should_select_stocks:
            select_stocks(ContextInfo)
        else:
            print("[{}] 跳过选股逻辑，当前索引: {}".format(current_date, current_index))
        
        # 5. 买卖决策生成
        trade_decision(ContextInfo)
        
        # 6. 做T交易执行
        t_trading(ContextInfo)
        
        # 7. 止盈止损检查
        check_stop_loss_take_profit(ContextInfo)
        
        # 8. 避险判断
        risk_avoidance(ContextInfo)
        
        print("[{}] 策略执行完成".format(current_date))
        
    except Exception as e:
        print("[{}] 策略执行异常: {}".format(current_date, str(e)))


def risk_check(ContextInfo):
    """
    风险评估
    """
    try:
        
        # 获取沪深300指数数据
        hs300_data = ContextInfo.get_market_data_ex(
            fields=['close', 'open', 'high', 'low'],
            stock_code=['000300.SH'],
            period='1d',
            start_time=calculate_start_date(current_date, 60),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        if '000300.SH' in hs300_data and not hs300_data['000300.SH'].empty:
            hs300_df = hs300_data['000300.SH']
            current_price = hs300_df['close'].iloc[-1]
            ma60 = hs300_df['close'].rolling(60).mean().iloc[-1]
            ma20 = hs300_df['close'].rolling(20).mean().iloc[-1]
            
            # 系统性风险：沪深300指数跌破60日均线且跌幅>3%
            if current_price < ma60 and (current_price / hs300_df['close'].iloc[-2] - 1) < -0.03:
                ContextInfo.market_risk_level = 2  # 高风险
                print("[{}] 系统性风险：沪深300指数跌破60日均线且跌幅>3%".format(current_date))
            elif current_price < ma20:
                ContextInfo.market_risk_level = 1  # 中等风险
            else:
                ContextInfo.market_risk_level = 0  # 低风险
                
        # 检查市场成交量
        volume_data = ContextInfo.get_market_data_ex(
            fields=['volume'],
            stock_code=['000300.SH'],
            period='1d',
            start_time=calculate_start_date(current_date, 3),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        if '000300.SH' in volume_data and not volume_data['000300.SH'].empty:
            volume_df = volume_data['000300.SH']
            if len(volume_df) >= 3:
                # 市场成交量连续3日萎缩20%以上
                vol_change = (volume_df['volume'].iloc[-1] / volume_df['volume'].iloc[-3]) - 1
                if vol_change < -0.2:
                    ContextInfo.market_risk_level = max(ContextInfo.market_risk_level, 1)
                    print("[{}] 流动性风险：市场成交量连续萎缩".format(current_date))
                    
    except Exception as e:
        print("[{}] 风险评估异常: {}".format(current_date, str(e)))


def sector_analysis(ContextInfo):
    """
    板块轮动分析 - 增强版
    综合评估各行业板块的市场热度，用于指导选股方向
    """
    try:
        sector_scores = {}
        
        sector_stocks_map = {}
        
        for sector_name, sector_key in sectors.items():
            # 获取板块成分股
            stocks = ContextInfo.get_stock_list_in_sector(sector_key)
            if not stocks or len(stocks) == 0:
                print("[{}] 板块 {} 成分子股票为空".format(current_date, sector_name))
                continue
            
            # 限制股票数量避免接口压力
            sample_stocks = stocks[:min(50, len(stocks))]
            sector_stocks_map[sector_name] = sample_stocks
        
        for sector_name, sample_stocks in sector_stocks_map.items():
            try:
                # 批量获取行情数据
                sector_data = ContextInfo.get_market_data_ex(
                    fields=['close', 'volume', 'amount'],
                    stock_code=sample_stocks,
                    period='1d',
                    start_time=calculate_start_date(current_date, 5),
                    end_time=current_date.replace('-', '').replace(' ', '')[:8],
                    count=-1
                )
                
                # 初始化统计变量
                total_price_change = 0
                total_volume_change = 0
                total_amount = 0
                valid_count = 0
                
                # 遍历成分股计算各项指标
                for stock in sample_stocks:
                    if stock not in sector_data or sector_data[stock] is None or sector_data[stock].empty:
                        continue
                        
                    df = sector_data[stock]
                    # 确保有足够的数据
                    if len(df) < 2:
                        continue
                        
                    close_prices = df['close']
                    volumes = df['volume'] if 'volume' in df.columns else pd.Series([np.nan]*len(df))
                    amounts = df['amount'] if 'amount' in df.columns else pd.Series([np.nan]*len(df))
                    
                    # 检查昨日和今日的收盘价是否为有效数值
                    prev_close = close_prices.iloc[-2]
                    curr_close = close_prices.iloc[-1]
                    if np.isnan(prev_close) or np.isnan(curr_close) or prev_close == 0:
                        continue
                    price_change = (curr_close / prev_close) - 1
                    total_price_change += price_change
                    
                    # 检查昨日和今日的成交量是否为有效数值
                    prev_vol = volumes.iloc[-2]
                    curr_vol = volumes.iloc[-1]
                    if not np.isnan(prev_vol) and not np.isnan(curr_vol) and prev_vol != 0:
                        volume_change = (curr_vol / prev_vol) - 1
                        total_volume_change += volume_change
                    
                    # 检查今日成交金额是否为有效数值
                    curr_amount = amounts.iloc[-1]
                    if not np.isnan(curr_amount):
                        total_amount += float(curr_amount)
                    
                    valid_count += 1
                
                # 如果没有有效样本，则跳过该板块
                if valid_count == 0:
                    print("[{}] 板块 {} 无有效样本数据".format(current_date, sector_name))
                    continue
                
                # 计算平均值
                avg_price_change = total_price_change / valid_count
                avg_volume_change = total_volume_change / valid_count if valid_count > 0 else 0
                
                # 计算板块热度得分
                # 使用更简单的线性加权模型，并直接使用总成交额（已按样本数平均）
                heat_score = (0.4 * avg_price_change +
                              0.3 * avg_volume_change +
                              0.3 * (total_amount / 1e8))  # 将成交额单位转换为亿元
                
                # 最终验证：确保得分是有效数字
                if not np.isnan(heat_score) and not np.isinf(heat_score):
                    sector_scores[sector_name] = heat_score
                    print("[{}] {}板块分析: 样本{}只, "
                          "均价涨{:.2%}, "
                          "均量变{:.2%}, "
                          "总额{:.2f}亿, "
                          "热度分{:.4f}".format(current_date, sector_name, valid_count, avg_price_change, avg_volume_change, total_amount/1e8, heat_score))
                else:
                    print("[{}] {}板块计算得分无效: {}".format(current_date, sector_name, heat_score))
                    
            except Exception as e:
                print("[{}] 板块 {} 分析过程出现异常: {}".format(current_date, sector_name, str(e)))
                continue
        
        # 排序并保存结果
        if sector_scores:
            # 按得分从高到低排序，处理可能的NaN值
            sorted_sectors = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
            # 保留前5个热门板块
            top_sectors = [item for item in sorted_sectors if not np.isnan(item[1])][:5]
            ContextInfo.sector_heat = dict(top_sectors)
            
            # 输出可读性更好的日志
            ranked_output = [f"{name}({score:.3f})" for name, score in top_sectors]
            print("[{}] 【板块热度排行榜】: {}".format(current_date, ' > '.join(ranked_output)))
        else:
            print("[{}] 未能计算出有效的板块热度排名".format(current_date))
            ContextInfo.sector_heat = {}
        
    except Exception as e:
        print("[{}] 板块轮动分析主流程异常: {}".format(current_date, str(e)))
        ContextInfo.sector_heat = {}


def select_stocks(ContextInfo):
    """
    选股逻辑
    """
    try:
        print("[{}] 开始选股...".format(current_date))
        
        # 获取热门板块股票
        sector_list = ContextInfo.sector_heat
        all_stocks_for_download = []  # 收集所有需要下载历史数据的股票代码
        
        for key in sector_list:
            all_stocks = ContextInfo.get_stock_list_in_sector(sectors[key])
            print("[{}] {} 待选股票总数: {}".format(current_date, key, len(all_stocks)))
            
            # 初步筛选条件
            # 1. 剔除ST/*ST股票、上市不足60天的次新股
            filtered_stocks = []
            for stock in all_stocks:
                try:
                    # 检查是否为ST股
                    stock_name = ContextInfo.get_stock_name(stock)
                    if 'ST' in stock_name:
                        continue
                    
                    # 检查上市时间
                    open_date = ContextInfo.get_open_date(stock)
                    if open_date > 0:
                        open_datetime = datetime.datetime.strptime(str(open_date), '%Y%m%d')
                        current_datetime = datetime.datetime.now()
                        if (current_datetime - open_datetime).days < 60:
                            continue
                    
                    filtered_stocks.append(stock)
                except:
                    continue
            
            print("[{}] 初步筛选后股票数量: {}".format(current_date, len(filtered_stocks)))
        
        # 处理每个板块的选股逻辑
        for key in sector_list:
            all_stocks = ContextInfo.get_stock_list_in_sector(sectors[key])
            
            # 初步筛选条件
            # 1. 剔除ST/*ST股票、上市不足60天的次新股
            filtered_stocks = []
            for stock in all_stocks:
                try:
                    # 检查是否为ST股
                    stock_name = ContextInfo.get_stock_name(stock)
                    if 'ST' in stock_name:
                        continue
                    
                    # 检查上市时间
                    open_date = ContextInfo.get_open_date(stock)
                    if open_date > 0:
                        open_datetime = datetime.datetime.strptime(str(open_date), '%Y%m%d')
                        current_datetime = datetime.datetime.now()
                        if (current_datetime - open_datetime).days < 60:
                            continue
                    
                    filtered_stocks.append(stock)
                except:
                    continue
            
            # 2. 选择市值排名前80%的股票（避免流动性风险）
            market_values = {}
            for stock in filtered_stocks:
                try:
                    float_caps = ContextInfo.get_float_caps(stock)
                    close_data = ContextInfo.get_market_data_ex(
                        fields=['close'],
                        stock_code=[stock],
                        period='1d',
                        start_time=calculate_start_date(current_date, 1),
                        end_time=current_date.replace('-', '').replace(' ', '')[:8],
                        count=-1
                    )
                    if stock in close_data and not close_data[stock].empty:
                        close_price = close_data[stock]['close'].iloc[-1]
                        market_value = float_caps * close_price
                        market_values[stock] = market_value
                except:
                    continue
            
            # 按市值排序，取前80%
            sorted_by_market_value = sorted(market_values.items(), key=lambda x: x[1], reverse=True)
            top_80_percent_count = int(len(sorted_by_market_value) * 0.8)
            selected_by_market_value = [item[0] for item in sorted_by_market_value[:top_80_percent_count]]
            
            print("[{}] 筛选后市值前80%股票数量: {}".format(current_date, len(selected_by_market_value)))
            # 3. 计算综合评分
            stock_scores = {}
            for stock in selected_by_market_value:
                try:
                    score = calculate_stock_score(ContextInfo, stock)
                    if score > 0:
                        stock_scores[stock] = score
                except:
                    continue
            
            print("[{}] 筛选后评分前20%股票数量: {}".format(current_date, len(stock_scores)))
            # 4. 选择评分排名前20%的股票
            sorted_by_score = sorted(stock_scores.items(), key=lambda x: x[1], reverse=True)
            top_20_percent_count = max(int(len(sorted_by_score) * 0.2), 20)  # 至少20只
            selected_by_score = [item[0] for item in sorted_by_score[:top_20_percent_count]]
            
            # 5. 从中筛选主力连续3日净流入且K线形态健康的股票
            final_selected = []
            for stock in selected_by_score:
                try:
                    # 检查资金流入
                    money_flow = check_money_flow(ContextInfo, stock)
                    # 检查均线多头排列
                    ma_aligned = check_ma_alignment(ContextInfo, stock)
                    print("[{}] {}资金流入: {}, 均线多头排列: {}".format(current_date, stock, money_flow, ma_aligned))
                    if money_flow and ma_aligned:
                        final_selected.append(stock)
                except:
                    continue
            
            # 如果严格条件筛选后没有股票，则使用宽松条件
            if len(final_selected) == 0:
                print("[{}] 严格条件未选出股票，使用宽松条件选股...".format(current_date))
                for stock in selected_by_score:
                    try:
                        # 使用技术指标综合判断
                        tech_score = calculate_technical_score(ContextInfo, stock)
                        if tech_score > 0.5:  # 技术面得分超过0.5认为可以接受
                            final_selected.append(stock)
                    except:
                        continue
                        
            # # 如果仍然没有股票，则使用基础条件选股
            if len(final_selected) == 0:
                print("[{}] 宽松条件未选出股票，使用基础条件选股...".format(current_date))
                # 基础条件：只需要满足均线排列或资金流入其中一个条件
                for stock in selected_by_score:
                    try:
                        money_flow = check_money_flow(ContextInfo, stock)
                        ma_aligned = check_ma_alignment(ContextInfo, stock)
                        
                        if money_flow or ma_aligned:  # 只需要满足其中一个条件
                            final_selected.append(stock)
                    except:
                        continue
            
            ContextInfo.selected_stocks = final_selected[:ContextInfo.portfolio_size]  # 最终选股数量不超过持仓限制
            print("[{}] {} 选股完成，共选出{}只股票: {}".format(current_date, key, len(ContextInfo.selected_stocks), ContextInfo.selected_stocks))
            
    except Exception as e:
        print("[{}] 选股异常: {}".format(current_date, str(e)))


def calculate_stock_score(ContextInfo, stock):
    """
    计算股票综合评分
    综合评分 = 0.3*价值评分 + 0.2*质量评分 + 0.2*成长评分 + 0.3*技术评分
    """
    try:
        
        # # 获取财务数据
        # finance_data = ContextInfo.get_finance([stock])
        # if not finance_data or stock not in finance_data:
        #     return 0
        
        # fin_data = finance_data[stock]
        
        # # 价值因子评分 (市净率、市盈率、市销率)
        # pb_score = 0
        # pe_score = 0
        # ps_score = 0
        
        # if 'PB' in fin_data and fin_data['PB'] > 0:
        #     pb = fin_data['PB']
        #     pb_score = max(0, 1 - pb/10)  # 假设合理PB在0-10之间
        
        # if 'PE' in fin_data and fin_data['PE'] > 0:
        #     pe = fin_data['PE']
        #     pe_score = max(0, 1 - pe/50)  # 假设合理PE在0-50之间
            
        # if 'PS' in fin_data and fin_data['PS'] > 0:
        #     ps = fin_data['PS']
        #     ps_score = max(0, 1 - ps/10)  # 假设合理PS在0-10之间
            
        # value_score = (pb_score + pe_score + ps_score) / 3
        
        # # 质量因子评分 (ROE、经营现金流增长率)
        # quality_score = 0
        # if 'ROE' in fin_data:
        #     roe = fin_data['ROE']
        #     quality_score += max(0, min(1, roe/0.2))  # 假设优秀ROE为20%
        
        # 成长因子评分 (营收增长率、净利润增长率)
        # growth_score = 0
        # if 'RevenueGrowth' in fin_data:
        #     revenue_growth = fin_data['RevenueGrowth']
        #     growth_score += max(0, min(1, revenue_growth/0.3))  # 假设优秀增长率为30%
            
        # if 'NetProfitGrowth' in fin_data:
        #     profit_growth = fin_data['NetProfitGrowth']
        #     growth_score += max(0, min(1, profit_growth/0.3))  # 假设优秀增长率为30%
            
        # growth_score = growth_score / 2
        
        # 技术因子评分 (价格动量、均线多头排列、RSI)
        tech_score = 0
        try:
            # 获取价格数据
            price_data = ContextInfo.get_market_data_ex(
                fields=['close'],
                stock_code=[stock],
                period='1d',
                start_time=calculate_start_date(current_date, 60),
                end_time=current_date.replace('-', '').replace(' ', '')[:8],
                count=-1
            )
            
            if stock in price_data and not price_data[stock].empty and len(price_data[stock]) >= 30:
                df = price_data[stock]
                # 价格动量 (最近一个月)
                momentum = df['close'].iloc[-1] / df['close'].iloc[-20] - 1
                tech_score += max(0, min(1, momentum/0.2))  # 假设优秀动量为20%
                
                # RSI计算
                rsi = calculate_rsi(df['close'].values, 14)
                if rsi:
                    rsi_score = 1 - abs(rsi - 50) / 50  # RSI接近50为佳
                    tech_score += rsi_score
                    
                tech_score = tech_score / 2
        except Exception as e:
            print("[{}] 获取股票数据异常: {}".format(current_date, str(e)))
            pass
        
        
        # 综合评分
        # total_score = 0.3 * value_score + 0.2 * quality_score + 0.2 * growth_score + 0.3 * tech_score
        return tech_score
        
    except Exception as e:
        print("[{}] 获取股票数据异常: {}".format(current_date, str(e)))
        return 0


def check_money_flow(ContextInfo, stock):
    """
    检查主力资金连续3日净流入
    """
    try:
        
        # 这里简化处理，实际应使用资金流数据接口
        # 由于平台接口限制，我们用价格和成交量变化来近似判断
        data = ContextInfo.get_market_data_ex(
            fields=['close', 'volume'],
            stock_code=[stock],
            period='1d',
            start_time=calculate_start_date(current_date, 3),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        if stock in data and not data[stock].empty and len(data[stock]) >= 3:
            df = data[stock]
            # 检查是否连续3日量价齐升
            price_up = True
            volume_up = True
            
            for i in range(1, 3):
                if df['close'].iloc[-i] <= df['close'].iloc[-i-1]:
                    price_up = False
                if df['volume'].iloc[-i] <= df['volume'].iloc[-i-1]:
                    volume_up = False
                    
            return price_up and volume_up
        return False
    except:
        return False


def check_ma_alignment(ContextInfo, stock):
    """
    检查均线多头排列 (5日/20日/60日均线多头排列)
    """
    try:
        
        data = ContextInfo.get_market_data_ex(
            fields=['close'],
            stock_code=[stock],
            period='1d',
            start_time=calculate_start_date(current_date, 60),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        if stock in data and not data[stock].empty and len(data[stock]) >= 60:
            df = data[stock]
            ma5 = df['close'].rolling(5).mean().iloc[-1]
            ma20 = df['close'].rolling(20).mean().iloc[-1]
            ma60 = df['close'].rolling(60).mean().iloc[-1]
            
            # 检查是否多头排列
            return ma5 > ma20 > ma60
        return False
    except:
        return False


def calculate_rsi(prices, period=14):
    """
    计算RSI指标
    """
    try:
        delta = np.diff(prices)
        gain = delta.copy()
        loss = delta.copy()
        gain[gain < 0] = 0
        loss[loss > 0] = 0
        loss = np.abs(loss)
        
        avg_gain = np.mean(gain[:period])
        avg_loss = np.mean(loss[:period])
        
        for i in range(period, len(gain)):
            avg_gain = (avg_gain * (period - 1) + gain[i]) / period
            avg_loss = (avg_loss * (period - 1) + loss[i]) / period
            
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except:
        return None


def trade_decision(ContextInfo):
    """
    买卖决策生成
    """
    try:
        print("[{}] 开始执行买卖：{}".format(current_date, ContextInfo.selected_stocks))
        current_positions = get_holdings(ContextInfo, "STOCK")
        
        # 1. 处理现有持仓
        for stock in list(current_positions.keys()):
            # 检查是否需要调仓
            should_sell = False
            
            # 获取股票最近一段时间的表现
            price_data = ContextInfo.get_market_data_ex(
                fields=['close'],
                stock_code=[stock],
                period='1d',
                start_time=calculate_start_date(current_date, 5),
                end_time=current_date.replace('-', '').replace(' ', '')[:8],
                count=-1
            )
            
            # 检查最近5日收益率
            if stock in price_data and not price_data[stock].empty and len(price_data[stock]) >= 5:
                df = price_data[stock]
                # 计算最近5日的收益率
                recent_return = (df['close'].iloc[-1] / df['close'].iloc[0]) - 1
                
                # 如果最近表现不佳（例如：跌幅超过2%），则平仓
                if recent_return < -0.02:
                    should_sell = True
            
            # 检查所属板块热度是否下降
            sector_hot = False
            for sector_name, sector_key in sectors.items():
                sector_stocks = ContextInfo.get_stock_list_in_sector(sector_key)
                if stock in sector_stocks and sector_name in ContextInfo.sector_heat:
                    sector_hot = True
                    break
            
            if not sector_hot:
                should_sell = True
                print("[{}] 股票 {} 所属板块热度下降，考虑平仓".format(current_date, stock))
            
            if should_sell:
                order_shares_local(stock, -current_positions[stock], "CLOSE_ALL", 0, ContextInfo, "strategy")
                print("[{}] 平仓股票: {}, 原因: 所属板块热度下降或近期表现不佳".format(current_date, stock))

        
        # 2. 买入新选股票
        for stock in ContextInfo.selected_stocks:
            if stock not in current_positions:
                print("[{}] 开始买入新股票: {}".format(current_date, stock))
                # 检查买入条件
                if check_buy_condition(ContextInfo, stock):
                    # 计算买入金额
                    available_capital = ContextInfo.capital / ContextInfo.portfolio_size
                    # 获取当前价格
                    price_data = ContextInfo.get_market_data_ex(
                        fields=['close'],
                        stock_code=[stock],
                        period='1d',
                        start_time=calculate_start_date(current_date, 1),
                        end_time=current_date.replace('-', '').replace(' ', '')[:8],
                        count=-1
                    )
                    print("[{}] 尝试买入股票: {}, {}".format(current_date, stock, price_data))
                    if stock in price_data and not price_data[stock].empty:
                        current_price = price_data[stock]['close'].iloc[-1]
                        quantity = int(available_capital / current_price / 100) * 100  # 100股整数倍
                        if quantity > 0:
                            order_shares_local(stock, quantity, "FIX", current_price, ContextInfo, "strategy")
                            print("[{}] 买入股票: {}, 数量: {}, 价格: {}".format(current_date, stock, quantity, current_price))
                            
    except Exception as e:
        print("[{}] 交易决策异常: {}".format(current_date, str(e)))


def check_buy_condition(ContextInfo, stock):
    """
    检查买入条件
    """
    try:
        
        # 获取多周期数据
        # 5分钟线
        data_5m = ContextInfo.get_market_data_ex(
            fields=['close', 'volume'],
            stock_code=[stock],
            period='5m',
            start_time=calculate_start_date(current_date, 20, '5m'),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        # 15分钟线
        data_15m = ContextInfo.get_market_data_ex(
            fields=['close', 'volume'],
            stock_code=[stock],
            period='15m',
            start_time=calculate_start_date(current_date, 20, '15m'),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        # 120分钟线
        data_120m = ContextInfo.get_market_data_ex(
            fields=['close', 'volume'],
            stock_code=[stock],
            period='120m',
            start_time=calculate_start_date(current_date, 20, '120m'),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        # 沪深300指数
        hs300_data = ContextInfo.get_market_data_ex(
            fields=['close'],
            stock_code=['000300.SH'],
            period='1d',
            start_time=calculate_start_date(current_date, 20),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )

        # print("[{}] {} 5分时数据: {}, 15分钟数据: {}, 120分钟数据: {}".format(current_date, stock, data_5m, data_15m, data_120m))
        
        # # 条件1: 5分钟线：价格突破近期平台，成交量放大2倍以上
        # condition1 = False
        # if stock in data_5m and not data_5m[stock].empty and len(data_5m[stock]) >= 10:
        #     df_5m = data_5m[stock]
        #     recent_high = df_5m['close'].iloc[-10:-1].max()
        #     current_volume = df_5m['volume'].iloc[-1]
        #     avg_volume = df_5m['volume'].iloc[-10:-1].mean()
        #     if df_5m['close'].iloc[-1] > recent_high and current_volume > 2 * avg_volume:
        #         condition1 = True
        
        # # 条件2: 15分钟线：RSI(14)处于40-60区间，刚形成金叉
        # condition2 = False
        # if stock in data_15m and not data_15m[stock].empty and len(data_15m[stock]) >= 14:
        #     df_15m = data_15m[stock]
        #     rsi = calculate_rsi(df_15m['close'].values, 14)
        #     if rsi and 40 <= rsi <= 60:
        #         # 简化金叉判断
        #         condition2 = True
        
        # # 条件3: 120分钟线：均线呈多头排列，MACD柱状线翻红
        # condition3 = False
        # if stock in data_120m and not data_120m[stock].empty and len(data_120m[stock]) >= 30:
        #     df_120m = data_120m[stock]
        #     ma5 = df_120m['close'].rolling(5).mean().iloc[-1]
        #     ma20 = df_120m['close'].rolling(20).mean().iloc[-1]
        #     if ma5 > ma20:  # 简化处理
        #         condition3 = True
        
        # 条件4: 整体市场情绪：沪深300指数处于20日均线上方
        condition4 = hs300_ma20_condition
        
        return condition4
        
    except Exception as e:
        print("[{}] 买入条件检查异常: {}".format(current_date, str(e)))
        return False


def t_trading(ContextInfo):
    """
    自动做T交易
    """
    try:
        current_positions = get_holdings(ContextInfo, "STOCK")
        
        for stock in current_positions:
            if stock not in ContextInfo.t_holdings:
                ContextInfo.t_holdings[stock] = {
                    'base_position': current_positions[stock] * 0.5,  # 保留50%底仓
                    't_position': current_positions[stock] * 0.5,     # 50%用于做T
                    'last_price': 0
                }
            
            # 获取实时数据
            data_5m = ContextInfo.get_market_data_ex(
                fields=['close', 'volume'],
                stock_code=[stock],
                period='5m',
                start_time=calculate_start_date(current_date, 20, '5m'),
                end_time=current_date.replace('-', '').replace(' ', '')[:8],
                count=-1
            )
            
            data_15m = ContextInfo.get_market_data_ex(
                fields=['close'],
                stock_code=[stock],
                period='15m',
                start_time=calculate_start_date(current_date, 20, '15m'),
                end_time=current_date.replace('-', '').replace(' ', '')[:8],
                count=-1
            )
            
            data_120m = ContextInfo.get_market_data_ex(
                fields=['close'],
                stock_code=[stock],
                period='120m',
                start_time=calculate_start_date(current_date, 20, '120m'),
                end_time=current_date.replace('-', '').replace(' ', '')[:8],
                count=-1
            )
            
            if stock in data_5m and not data_5m[stock].empty:
                current_price = data_5m[stock]['close'].iloc[-1]
                t_info = ContextInfo.t_holdings[stock]
                
                # 更新上次价格
                if t_info['last_price'] == 0:
                    t_info['last_price'] = current_price
                
                # 5分钟超买超卖：RSI(14)>70时准备卖出，<30时准备买入
                if stock in data_15m and not data_15m[stock].empty and len(data_15m[stock]) >= 14:
                    rsi = calculate_rsi(data_15m[stock]['close'].values, 14)
                    if rsi and rsi > 70:
                        # 超买，卖出做T仓位
                        if t_info['t_position'] > 0:
                            order_shares_local(stock, -100, "FIX", current_price, ContextInfo, "t_trade")  # 卖出100股
                            t_info['t_position'] -= 100
                            t_info['last_price'] = current_price
                            print("[{}] 做T卖出: {}, 价格: {}".format(current_date, stock, current_price))
                    elif rsi and rsi < 30:
                        # 超卖，买入做T仓位
                        order_shares_local(stock, 100, "FIX", current_price, ContextInfo, "t_trade")  # 买入100股
                        t_info['t_position'] += 100
                        t_info['last_price'] = current_price
                        print("[{}] 做T买入: {}, 价格: {}".format(current_date, stock, current_price))
                
                # 检查做T止损
                price_change = (current_price / t_info['last_price']) - 1
                if abs(price_change) > ContextInfo.t_stop_loss:
                    # 触发止损
                    if price_change < 0:
                        # 亏损超过1.5%，止损卖出
                        if t_info['t_position'] > 0:
                            order_shares_local(stock, -t_info['t_position'], "CLOSE_ALL", 0, ContextInfo, "t_stop_loss")
                            print("[{}] 做T止损卖出: {}, 亏损幅度: {:.2f}%".format(current_date, stock, price_change*100))
                            t_info['t_position'] = 0
                    else:
                        # 盈利超过1.5%，止盈
                        if t_info['t_position'] > 0:
                            order_shares_local(stock, -t_info['t_position'], "CLOSE_ALL", 0, ContextInfo, "t_take_profit")
                            print("[{}] 做T止盈卖出: {}, 盈利幅度: {:.2f}%".format(current_date, stock, price_change*100))
                            t_info['t_position'] = 0
                
    except Exception as e:
        print("[{}] 做T交易异常: {}".format(current_date, str(e)))


def check_stop_loss_take_profit(ContextInfo):
    """
    止盈止损检查
    """
    try:
        current_positions = get_holdings(ContextInfo, "STOCK")
        
        for stock in current_positions:
            # 获取持仓信息
            if stock not in ContextInfo.position_info:
                # 获取股票的持仓成本和持仓日期
                holdings = get_holdings(ContextInfo, "STOCK")
                buy_price = 0
                buy_date = datetime.datetime.now()
                
                # 尝试从交易记录中获取买入价格和日期
                try:
                    trade_details = get_trade_detail_data(ContextInfo.account_id, "STOCK", "POSITION")
                    for detail in trade_details:
                        if detail.m_strInstrumentID + "." + detail.m_strExchangeID == stock:
                            buy_price = detail.m_dOpenPrice  # 获取持仓均价
                            buy_date = datetime.datetime.fromtimestamp(detail.m_nOpenDate // 1000) if detail.m_nOpenDate else datetime.datetime.now()
                            break
                except Exception as e:
                    print("[{}] 获取持仓信息异常: {}".format(current_date, str(e)))
                
                ContextInfo.position_info[stock] = {
                    'buy_price': buy_price,
                    'buy_date': buy_date,
                    'highest_price': buy_price  # 初始最高价设为买入价
                }
            
            pos_info = ContextInfo.position_info[stock]
            
            # 获取当前价格
            price_data = ContextInfo.get_market_data_ex(
                fields=['close', 'high'],
                stock_code=[stock],
                period='1d',
                start_time=calculate_start_date(current_date, 1),
                end_time=current_date.replace('-', '').replace(' ', '')[:8],
                count=-1
            )
            
            if stock in price_data and not price_data[stock].empty:
                current_price = price_data[stock]['close'].iloc[-1]
                high_price = price_data[stock]['high'].iloc[-1]
                
                # 更新最高价
                if current_price > pos_info['highest_price']:
                    pos_info['highest_price'] = current_price
                
                # 计算收益率
                if pos_info['buy_price'] > 0:
                    return_rate = (current_price / pos_info['buy_price']) - 1
                    
                    # 1. 浮动止盈：收益率达到5%以上时，设置回撤2%止盈
                    if return_rate >= ContextInfo.take_profit:
                        drawdown = (pos_info['highest_price'] - current_price) / pos_info['highest_price']
                        if drawdown >= ContextInfo.drawdown_threshold:
                            # 触发回撤止盈
                            order_shares_local(stock, -current_positions[stock], "CLOSE_ALL", 0, ContextInfo, "drawdown_stop")
                            print("[{}] 回撤止盈: {}, 收益率: {:.2f}%, 回撤: {:.2f}%".format(
                                current_date, stock, return_rate*100, drawdown*100))
                            continue
                    
                    # 2. 硬止损：单笔交易最大亏损不超过3%
                    if return_rate <= -ContextInfo.stop_loss:
                        order_shares_local(stock, -current_positions[stock], "CLOSE_ALL", 0, ContextInfo, "hard_stop_loss")
                        print("[{}] 硬止损: {}, 亏损幅度: {:.2f}%".format(current_date, stock, return_rate*100))
                        continue
                
                # 3. 时间止盈：持仓超过5个交易日未盈利考虑平仓
                # hold_days = (datetime.datetime.now() - pos_info['buy_date']).days
                # if hold_days > ContextInfo.max_hold_days and pos_info['buy_price'] > 0:
                #     if current_price <= pos_info['buy_price']:
                #         order_shares_local(stock, -current_positions[stock], "CLOSE_ALL", 0, ContextInfo, "time_stop")
                #         print("[{}] 时间止盈: {}, 持仓天数: {}天".format(current_date, stock, hold_days))
                        
                # 4. 新增功能：持仓超过7-10天且没有盈利时清仓
                import random
                max_hold_days_random = random.randint(7, 10)  # 7-10天的随机天数
                if hold_days > max_hold_days_random and pos_info['buy_price'] > 0:
                    if current_price <= pos_info['buy_price']:  # 没有盈利
                        order_shares_local(stock, -current_positions[stock], "CLOSE_ALL", 0, ContextInfo, "no_profit_clear")
                        print("[{}] 无盈利清仓: {}, 持仓天数: {}天, 随机天数上限: {}天".format(current_date, stock, hold_days, max_hold_days_random))
                        
    except Exception as e:
        print("[{}] 止盈止损检查异常: {}".format(current_date, str(e)))


def risk_avoidance(ContextInfo):
    """
    自动避险机制
    """
    try:
        # 根据市场风险等级调整仓位
        if ContextInfo.market_risk_level == 2:
            # 高风险：减仓至50%以下
            current_positions = get_holdings(ContextInfo, "STOCK")
            reduce_ratio = 0.5
            for stock in current_positions:
                reduce_amount = int(current_positions[stock] * reduce_ratio)
                if reduce_amount > 0:
                    order_shares_local(stock, -reduce_amount, "FIX", 0, ContextInfo, "risk_avoidance")
                    print("[{}] 高风险避险减仓: {}, 减仓数量: {}".format(current_date, stock, reduce_amount))
        elif ContextInfo.market_risk_level == 1:
            # 中等风险：减仓至70%
            current_positions = get_holdings(ContextInfo, "STOCK")
            reduce_ratio = 0.3
            for stock in current_positions:
                reduce_amount = int(current_positions[stock] * reduce_ratio)
                if reduce_amount > 0:
                    order_shares_local(stock, -reduce_amount, "FIX", 0, ContextInfo, "risk_avoidance")
                    print("[{}] 中等风险减仓: {}, 减仓数量: {}".format(current_date, stock, reduce_amount))
                    
    except Exception as e:
        print("[{}] 避险机制异常: {}".format(current_date, str(e)))


def get_holdings(ContextInfo, datatype):
    """
    获取持仓信息
    """
    try:
        holdings = {}
        # 使用get_trade_detail_data获取实际持仓数据
        resultlist = get_trade_detail_data(ContextInfo.account_id, datatype, "POSITION")
        for obj in resultlist:
            # 将持仓数据转换为字典格式，键为股票代码，值为持仓数量
            holdings[obj.m_strInstrumentID + "." + obj.m_strExchangeID] = obj.m_nVolume
        return holdings
    except:
        return {}


def timetag_to_datetime(timetag, format):
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


# 策略辅助函数
def order_shares_local(stock_code, shares, order_type, price, ContextInfo, strategy_name):
    """
    下单函数（支持回测和实盘）
    """
    try:
        # 区分回测和实盘环境
        action = "买入" if shares > 0 else "卖出"
        
        result = order_shares(stock_code, shares, order_type, price, ContextInfo,strategy_name)
        print("[{}] 策略: {} 下单: {} {} {}股, 价格: {}, 结果: {}".format(current_date, strategy_name, action, stock_code, abs(shares), price, result))
        return result
    except Exception as e:
        print("[{}] 下单异常: {}".format(current_date, str(e)))
        return {"success": False, "error": str(e)}


def calculate_technical_score(ContextInfo, stock):
    """
    计算技术面综合评分，使用多种技术指标
    包括：RSI、CCI、MACD、均线排列、布林带等
    """
    try:
        score = 0
        indicators_count = 0
        
        # 获取价格数据
        data = ContextInfo.get_market_data_ex(
            fields=['close', 'high', 'low', 'open', 'volume'],
            stock_code=[stock],
            period='1d',
            start_time=calculate_start_date(current_date, 20),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        if stock not in data or data[stock].empty or len(data[stock]) < 14:
            return 0
            
        df = data[stock]
        
        # 1. RSI指标 (相对强弱指数)
        rsi = calculate_rsi(df['close'].values, 14)
        if rsi is not None:
            indicators_count += 1
            # RSI在30-70之间为较好区间
            if 30 <= rsi <= 70:
                score += 0.2
            elif 20 <= rsi <= 80:
                score += 0.1
                
        # 2. CCI指标 (顺势指标)
        cci = calculate_cci(df['high'].values, df['low'].values, df['close'].values, 14)
        if cci is not None:
            indicators_count += 1
            # CCI在-100到+100之间为盘整，>+100为强势，<-100为弱势
            if -100 <= cci <= 100:
                score += 0.2
            elif cci > 100:
                score += 0.15
            elif cci < -100:
                score += 0.05
                
        # 3. MACD指标
        macd_score = calculate_macd_score(df['close'].values)
        if macd_score is not None:
            indicators_count += 1
            score += 0.2 * macd_score
            
        # 4. 均线排列
        ma_score = calculate_ma_score(df['close'].values)
        if ma_score is not None:
            indicators_count += 1
            score += 0.2 * ma_score
            
        # 5. 布林带指标
        bb_score = calculate_bollinger_bands_score(df['close'].values)
        if bb_score is not None:
            indicators_count += 1
            score += 0.2 * bb_score
            
        # 返回平均得分
        if indicators_count > 0:
            return score / indicators_count
        else:
            return 0
            
    except Exception as e:
        print("[{}] 计算技术面评分异常 {}: {}".format(current_date, stock, str(e)))
        return 0


def calculate_cci(high, low, close, period=14):
    """
    计算CCI指标
    """
    try:
        if len(close) < period:
            return None
            
        # 计算典型价格
        tp = (high + low + close) / 3
        
        # 计算移动平均
        sma = np.zeros(len(tp))
        mean_dev = np.zeros(len(tp))
        
        for i in range(period - 1, len(tp)):
            # 计算TP的移动平均
            sma[i] = np.mean(tp[i - period + 1:i + 1])
            
            # 计算平均偏差
            mean_dev[i] = np.mean(np.abs(tp[i - period + 1:i + 1] - sma[i]))
            
        # 计算CCI
        cci = np.zeros(len(tp))
        for i in range(period - 1, len(tp)):
            if mean_dev[i] != 0:
                cci[i] = (tp[i] - sma[i]) / (0.015 * mean_dev[i])
            else:
                cci[i] = 0
                
        return cci[-1]
        
    except Exception as e:
        return None


def calculate_macd_score(prices):
    """
    计算MACD得分
    """
    try:
        if len(prices) < 26:
            return None
            
        # 计算MACD线和信号线
        ema12 = calculate_ema(prices, 12)
        ema26 = calculate_ema(prices, 26)
        macd_line = ema12 - ema26
        signal_line = calculate_ema(macd_line[-9:], 9)  # 9日信号线
        
        if len(signal_line) == 0:
            return None
            
        # MACD柱状图
        histogram = macd_line[-len(signal_line):] - signal_line
        
        # 评分逻辑
        score = 0
        # MACD线上穿信号线
        if len(histogram) >= 2 and histogram[-2] <= 0 and histogram[-1] > 0:
            score = 0.8  # 金叉信号强
        elif len(histogram) >= 2 and histogram[-2] >= 0 and histogram[-1] < 0:
            score = 0.2  # 死叉信号弱
        elif histogram[-1] > 0:
            score = 0.6  # MACD在零轴上方
        else:
            score = 0.4  # MACD在零轴下方
            
        return score
        
    except Exception as e:
        return None


def calculate_ema(prices, period):
    """
    计算指数移动平均线
    """
    try:
        if len(prices) < period:
            return np.array([])
            
        k = 2 / (period + 1)
        ema = np.zeros(len(prices))
        ema[period-1] = np.mean(prices[:period])  # 初始EMA为简单移动平均
        
        for i in range(period, len(prices)):
            ema[i] = prices[i] * k + ema[i-1] * (1 - k)
            
        return ema
    except Exception as e:
        return np.array([])


def calculate_ma_score(prices):
    """
    计算均线得分
    """
    try:
        if len(prices) < 20:
            return None
            
        # 计算不同周期的均线
        ma5 = np.mean(prices[-5:])
        ma10 = np.mean(prices[-10:])
        ma20 = np.mean(prices[-20:])
        
        score = 0
        # 均线多头排列得分
        if ma5 > ma10 > ma20:
            score = 1.0  # 完美多头排列
        elif ma5 > ma10 and ma10 > ma20:
            score = 0.8  # 基本多头排列
        elif ma5 > ma10 or ma10 > ma20:
            score = 0.5  # 部分多头排列
        elif ma5 < ma10 < ma20:
            score = 0.1  # 空头排列
        else:
            score = 0.3  # 混合排列
            
        return score
    except Exception as e:
        return None


def calculate_bollinger_bands_score(prices):
    """
    计算布林带得分
    """
    try:
        if len(prices) < 20:
            return None
            
        # 计算布林带
        ma20 = np.mean(prices[-20:])
        std20 = np.std(prices[-20:])
        upper_band = ma20 + 2 * std20
        lower_band = ma20 - 2 * std20
        current_price = prices[-1]
        
        score = 0
        # 根据价格在布林带中的位置评分
        if current_price > upper_band:
            score = 0.3  # 超买区域
        elif current_price < lower_band:
            score = 0.9  # 超卖区域，反弹机会大
        elif current_price > ma20:
            score = 0.6  # 中上区域
        else:
            score = 0.7  # 中下区域
        
        return score
    except Exception as e:
        return None


def check_hs300_ma20_condition(ContextInfo):
    """
    检查沪深300指数是否处于20日均线上方
    """
    try:
        
        # 获取沪深300指数数据
        hs300_data = ContextInfo.get_market_data_ex(
            fields=['close'],
            stock_code=['000300.SH'],
            period='1d',
            start_time=calculate_start_date(current_date, 20),
            end_time=current_date.replace('-', '').replace(' ', '')[:8],
            count=-1
        )
        
        if '000300.SH' in hs300_data and not hs300_data['000300.SH'].empty and len(hs300_data['000300.SH']) >= 20:
            df_hs300 = hs300_data['000300.SH']
            ma20 = df_hs300['close'].rolling(20).mean().iloc[-1]
            current_price = df_hs300['close'].iloc[-1]
            return current_price > ma20
        return False
    except Exception as e:
        print("[{}] 检查沪深300指数20日均线状态异常: {}".format(current_date, str(e)))
        return False
