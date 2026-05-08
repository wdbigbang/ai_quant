# -*- coding: utf-8 -*-
"""
同花顺API高级测试脚本

用途：模拟真实浏览器请求，绕过反爬虫机制
运行环境：任何支持Python的服务器或本地环境
依赖：requests库
"""

import requests
import json
from datetime import datetime

# ============================================================================
# API配置
# ============================================================================
API_URL = "https://data.10jqka.com.cn/dataapi/limit_up/block_top"

# 完整的浏览器请求头（模拟Chrome浏览器）
HEADERS_V1 = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://data.10jqka.com.cn/",
    "Origin": "https://data.10jqka.com.cn",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "Sec-Ch-Ua": '"Google Chrome";v="123", "Not(A:Brand";v="99", "Chromium";v="123"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

# 另一种请求头（模拟Firefox浏览器）
HEADERS_V2 = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://data.10jqka.com.cn/",
    "Origin": "https://data.10jqka.com.cn",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

# ============================================================================
# 测试函数
# ============================================================================

def test_with_headers(headers, headers_name):
    """
    使用指定的请求头测试API
    
    参数:
        headers: 请求头字典
        headers_name: 请求头名称（用于输出）
    """
    print(f"\n{'='*80}")
    print(f"测试请求头: {headers_name}")
    print(f"{'='*80}")
    
    try:
        # 创建Session保持连接
        session = requests.Session()
        session.headers.update(headers)
        
        # 先访问主页（获取可能的Cookie）
        print("步骤1: 访问主页...")
        try:
            main_response = session.get("https://data.10jqka.com.cn/", timeout=10)
            print(f"  主页状态码: {main_response.status_code}")
            print(f"  Cookies: {dict(session.cookies)}")
        except Exception as e:
            print(f"  主页访问失败: {str(e)}")
        
        # 构造请求参数
        params = {
            "filter": "HS,GEM2STAR",
            "date": "2024-12-25"
        }
        
        # 发送API请求
        print(f"\n步骤2: 发送API请求...")
        print(f"  请求URL: {API_URL}")
        print(f"  参数: {params}")
        
        response = session.get(API_URL, params=params, timeout=10)
        
        # 显示响应信息
        print(f"\n响应状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        
        # 解析JSON
        data = response.json()
        
        # 检查状态码
        status_code = data.get("status_code", -1)
        print(f"\nAPI状态码: {status_code}")
        
        if status_code == 0:
            # 成功
            concepts = data.get("data", [])
            print(f"✅ 成功！获取到 {len(concepts)} 个热门概念\n")
            
            # 显示前2个概念
            for i, concept in enumerate(concepts[:2], 1):
                print(f"【概念 {i}】{concept['name']}")
                print(f"  涨停数: {concept['limit_up_num']}, 连板数: {concept['continuous_plate_num']}")
            
            return True
        else:
            # 失败
            error_msg = data.get("status_msg", "未知错误")
            print(f"❌ 失败！错误信息: {error_msg}")
            print(f"完整响应: {json.dumps(data, ensure_ascii=False, indent=2)}\n")
            return False
            
    except Exception as e:
        print(f"❌ 异常: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return False


def test_different_params():
    """
    测试不同的参数组合
    """
    print("\n" + "="*80)
    print("测试不同的参数组合")
    print("="*80)
    
    # 使用完整的Chrome请求头
    session = requests.Session()
    session.headers.update(HEADERS_V1)
    
    # 测试不同的参数组合
    test_cases = [
        {
            "name": "原始参数",
            "params": {
                "filter": "HS,GEM2STAR",
                "date": "2024-12-25"
            }
        },
        {
            "name": "简化filter参数",
            "params": {
                "filter": "HS",
                "date": "2024-12-25"
            }
        },
        {
            "name": "添加时间戳参数",
            "params": {
                "filter": "HS,GEM2STAR",
                "date": "2024-12-25",
                "_": int(datetime.now().timestamp())
            }
        },
        {
            "name": "只传date参数",
            "params": {
                "date": "2024-12-25"
            }
        },
    ]
    
    for test_case in test_cases:
        print(f"\n{'-'*80}")
        print(f"测试: {test_case['name']}")
        print(f"参数: {test_case['params']}")
        
        try:
            response = session.get(API_URL, params=test_case['params'], timeout=10)
            data = response.json()
            
            status_code = data.get("status_code", -1)
            if status_code == 0:
                concepts = data.get("data", [])
                print(f"✅ 成功！获取到 {len(concepts)} 个概念")
            else:
                error_msg = data.get("status_msg", "未知错误")
                print(f"❌ 失败: {error_msg}")
                
        except Exception as e:
            print(f"❌ 异常: {str(e)}")


def test_with_browser_developer_tools():
    """
    使用浏览器开发者工具中的真实请求头
    """
    print("\n" + "="*80)
    print("使用浏览器开发者工具中的真实请求头")
    print("="*80)
    print("\n请在浏览器中执行以下步骤：")
    print("1. 打开浏览器开发者工具（F12）")
    print("2. 访问 https://data.10jqka.com.cn/")
    print("3. 在Network标签中找到API请求")
    print("4. 复制完整的请求头")
    print("5. 将请求头粘贴到下面的HEADERS_BROWSER变量中\n")
    
    # 用户需要手动填入从浏览器复制的请求头
    HEADERS_BROWSER = {
        # 请在此处粘贴从浏览器复制的完整请求头
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://data.10jqka.com.cn/",
    }
    
    try:
        session = requests.Session()
        session.headers.update(HEADERS_BROWSER)
        
        params = {
            "filter": "HS,GEM2STAR",
            "date": "2024-12-25"
        }
        
        response = session.get(API_URL, params=params, timeout=10)
        data = response.json()
        
        status_code = data.get("status_code", -1)
        if status_code == 0:
            concepts = data.get("data", [])
            print(f"✅ 成功！获取到 {len(concepts)} 个概念\n")
            
            # 显示第一个概念的完整数据
            if concepts:
                print("第一个概念的完整数据：")
                print(json.dumps(concepts[0], ensure_ascii=False, indent=2))
        else:
            error_msg = data.get("status_msg", "未知错误")
            print(f"❌ 失败: {error_msg}")
            
    except Exception as e:
        print(f"❌ 异常: {str(e)}")


def test_alternative_apis():
    """
    测试其他可能的API端点
    """
    print("\n" + "="*80)
    print("测试其他可能的API端点")
    print("="*80)
    
    # 尝试其他可能的API地址
    alternative_urls = [
        "https://data.10jqka.com.cn/dataapi/limit_up/block_top",
        "https://data.10jqka.com.cn/dataapi/limit_up/plate",
        "https://data.10jqka.com.cn/dataapi/limit_up/sector",
    ]
    
    session = requests.Session()
    session.headers.update(HEADERS_V1)
    
    for url in alternative_urls:
        print(f"\n测试URL: {url}")
        
        try:
            params = {
                "filter": "HS,GEM2STAR",
                "date": "2024-12-25"
            }
            
            response = session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                status_code = data.get("status_code", -1)
                
                if status_code == 0:
                    concepts = data.get("data", [])
                    print(f"  ✅ 成功！获取到 {len(concepts)} 个概念")
                else:
                    error_msg = data.get("status_msg", "未知错误")
                    print(f"  ❌ 失败: {error_msg}")
            else:
                print(f"  ❌ HTTP状态码: {response.status_code}")
                
        except Exception as e:
            print(f"  ❌ 异常: {str(e)}")


# ============================================================================
# 主函数
# ============================================================================

def main():
    """
    主函数
    """
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                    同花顺API高级测试脚本                                 ║
║                                                                            ║
║  功能：模拟真实浏览器请求，绕过反爬虫机制                                 ║
║  用法：python test_ths_api_advanced.py                                    ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
""")
    
    # 测试1: Chrome请求头
    success1 = test_with_headers(HEADERS_V1, "Chrome浏览器请求头")
    
    # 测试2: Firefox请求头
    success2 = test_with_headers(HEADERS_V2, "Firefox浏览器请求头")
    
    # 测试3: 不同参数组合
    test_different_params()
    
    # 测试4: 其他API端点
    test_alternative_apis()
    
    # 测试5: 使用浏览器开发者工具中的真实请求头
    print("\n" + "="*80)
    print("是否要使用浏览器开发者工具中的真实请求头进行测试？（y/n）")
    choice = input("> ").strip().lower()
    if choice == 'y':
        test_with_browser_developer_tools()
    
    # 汇总结果
    print("\n" + "="*80)
    print("测试汇总")
    print("="*80)
    print(f"Chrome请求头: {'✅ 成功' if success1 else '❌ 失败'}")
    print(f"Firefox请求头: {'✅ 成功' if success2 else '❌ 失败'}")
    
    if success1 or success2:
        print("\n✅ 至少有一种方法成功！建议在代码中使用成功的方法。")
    else:
        print("\n❌ 所有方法都失败，建议：")
        print("1. 检查网络连接")
        print("2. 确认同花顺API是否需要Cookie或其他验证")
        print("3. 使用浏览器开发者工具查看完整的请求")
        print("4. 考虑使用Selenium等浏览器自动化工具")


if __name__ == "__main__":
    main()