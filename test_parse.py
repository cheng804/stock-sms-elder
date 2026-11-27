from app.sms_handler import parse_command

# debug 買字比對
test = "2303買"
buy_keywords = ["買", "分析", "要不要", "值不值", "貴不貴", "buy"]
print(f"msg={test!r}")
print(f"msg bytes={test.encode('utf-8')}")
for kw in buy_keywords:
    print(f"  kw={kw!r}, in msg: {kw in test}, lower: {kw.lower() in test.lower()}")

print()
tests = ["2303買", "2303 買", "2330買", "買2330", "2330分析"]
for t in tests:
    result = parse_command(t)
    print(f"{t!r:15} -> type={result['type']}, stock={result['stock_code']}")
