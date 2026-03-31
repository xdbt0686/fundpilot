from tools.price_tool import get_latest_price


def main():
    ticker = input("请输入 ETF ticker：").strip().upper()
    result = get_latest_price(ticker)

    if not result:
        print("没有获取到价格数据。")
        return

    print("\nETF 最新价格：\n")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()