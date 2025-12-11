# -*- coding: gbk -*-
"""
持仓与资金管理模块
实现持仓管理、资金管理和买入判断逻辑
"""

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
            total_amount = position.m_dPositionCost
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
            ContextInfo.total_amount = account.m_dInstrumentValue  # 总资产
            ContextInfo.available_amount = account.m_dAvailable    # 可用资金
            ContextInfo.stock_amount = total_stock_value           # 持仓总金额
            
        # 更新买入标志
        update_buy_flag(ContextInfo)
        
    except Exception as e:
        print("更新持仓数据时出错: ", str(e))

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
        print("更新买入标志时出错: ", str(e))
        ContextInfo.enable_flag = False
def print_position_info(ContextInfo):
    """
    打印持仓和资金信息
    """
    print("=" * 50)
    print("持仓信息:")
    for stock_code, info in ContextInfo.holdings.items():
        print(f"股票代码: {stock_code}, 持仓股数: {info['volume']}, 成本价: {info['price']:.2f}, 持仓金额: {info['total_amount']:.2f}")
    
    print("\n资金信息:")
    print(f"总资产: {ContextInfo.total_amount:.2f}")
    print(f"可用资金: {ContextInfo.available_amount:.2f}")
    print(f"持仓总金额: {ContextInfo.stock_amount:.2f}")
    print(f"是否可以买入: {ContextInfo.enable_flag}")
    print("=" * 50)