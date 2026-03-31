from tools.etf_profile import get_etf_profile


def main():
    ticker = input("请输入 ETF ticker：").strip().upper()
    result = get_etf_profile(ticker)

    if not result:
        print("没有找到对应 ETF。")
        return

    print("\nETF 基本信息：\n")
    for k, v in result.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()