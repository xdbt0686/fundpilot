def notify_console(message: str):
    print("\n" + "=" * 60)
    print("AI 监控提醒")
    print("=" * 60)
    print(message)
    print("=" * 60 + "\n")


def notify_windows(title: str, message: str, duration: int = 10):
    try:
        from win10toast import ToastNotifier

        toaster = ToastNotifier()
        toaster.show_toast(
            title=title,
            msg=message,
            duration=duration,
            threaded=True
        )
    except Exception as e:
        print(f"[WARN] Windows 弹窗失败: {e}")
        print(f"[FALLBACK NOTIFY] {title}: {message}")