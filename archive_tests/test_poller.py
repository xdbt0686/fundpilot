from monitors.price_poller import poll_once


def main():
    result = poll_once()

    print("\n本次轮询结果：\n")
    for ticker, data in result.items():
        print(f"{ticker}: {data}")


if __name__ == "__main__":
    main()