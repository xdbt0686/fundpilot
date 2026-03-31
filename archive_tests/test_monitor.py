from monitors.watchlist_monitor import monitor_watchlist


def main():
    watchlist = ["VUAG", "CSP1", "SWDA", "VWRP"]

    results = monitor_watchlist(
        tickers=watchlist,
        drop_threshold=-1.0,
        rise_threshold=1.0
    )

    print("\n监控结果：\n")
    for item in results:
        print(item["message"])


if __name__ == "__main__":
    main()