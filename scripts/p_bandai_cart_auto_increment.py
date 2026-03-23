"""
プレミアムバンダイ カート内商品の個数を自動変更するスクリプト

使い方:
  1. まずChromeを完全に閉じる（タスクバーも）
  2. コマンドプロンプトで以下を実行してChromeを起動:
     chrome.exe --remote-debugging-port=9222
  3. 開いたChromeで手動でログイン（https://p-bandai.jp/login/?c=1）
  4. ログイン後、別のコマンドプロンプトでこのスクリプトを実行:
     python p_bandai_cart_auto_increment.py
  5. Enterで処理開始

動作:
  - 手動で開いたChromeに接続（Bot検出されない）
  - カートページをリロード → select要素の数量を最大4まで変更
  - 3秒おきに繰り返し
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

CART_URL = "https://p-bandai.jp/cart/"
MAX_QTY = 4
RELOAD_INTERVAL = 3  # 秒


def connect_to_chrome():
    """既に起動済みのChromeに接続する"""
    options = Options()
    options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=options)
    return driver


def main():
    print("=" * 50)
    print("プレミアムバンダイ カート数量自動変更ツール")
    print("=" * 50)
    print()
    print("【事前準備】")
    print("1. Chromeを完全に閉じる")
    print("2. コマンドプロンプトで以下を実行:")
    print('   chrome.exe --remote-debugging-port=9222')
    print("   （パスが通っていない場合）")
    print('   "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
    print("3. 開いたChromeでプレバンにログイン")
    print()
    input("準備ができたらEnterを押してください...")

    print("\nChromeに接続中...")
    try:
        driver = connect_to_chrome()
    except Exception as e:
        print(f"接続エラー: {e}")
        print("\nChromeが --remote-debugging-port=9222 で起動しているか確認してください。")
        input("Enterで終了...")
        return

    print(f"接続成功！ 現在のURL: {driver.current_url}")
    input("\nカート処理を開始するにはEnterを押してください...")

    # --- カート数量自動変更ループ ---
    print("自動処理を開始します...")
    round_num = 0

    try:
        while True:
            round_num += 1
            print(f"\n--- ラウンド {round_num} ---")

            try:
                driver.get(CART_URL)
                time.sleep(2)  # ページ読み込み待ち
            except Exception as e:
                print(f"ページ読み込みエラー: {e}")
                time.sleep(RELOAD_INTERVAL)
                continue

            # select要素を検出（name が "odr_" で始まるもの）
            selects = driver.find_elements(By.CSS_SELECTOR, 'select[name^="odr_"]')
            print(f"商品数: {len(selects)}")

            if not selects:
                print("カートに商品がありません。")
                time.sleep(RELOAD_INTERVAL)
                continue

            changed = 0
            all_maxed = True

            for sel_elem in selects:
                select = Select(sel_elem)
                name = sel_elem.get_attribute("name")
                current_val = int(select.first_selected_option.get_attribute("value"))

                # 選択可能な最大値を取得
                available_values = []
                for opt in select.options:
                    try:
                        available_values.append(int(opt.get_attribute("value")))
                    except ValueError:
                        pass
                max_available = max(available_values) if available_values else 0
                target = min(MAX_QTY, max_available)

                print(f"  {name}: 現在={current_val}, 最大={max_available}, 目標={target}")

                if current_val < target:
                    all_maxed = False
                    select.select_by_value(str(target))
                    changed += 1
                    print(f"    → {target} に変更しました")
                    # onchange="document.recalc.submit()" が発火するので待つ
                    time.sleep(2)
                    # ページがリロードされるので、残りのselectは次のラウンドで処理
                    break

            if changed > 0:
                print(f"{changed}件の数量を変更。ページリロードを待ちます...")
            elif all_maxed and len(selects) > 0:
                print("\n全商品が最大数量に達しました。完了！")
                break
            else:
                print("変更不要。")

            print(f"{RELOAD_INTERVAL}秒後にリロードします...")
            time.sleep(RELOAD_INTERVAL)

    except KeyboardInterrupt:
        print("\n中断されました。")
    except Exception as e:
        print(f"エラー: {e}")

    print("\n処理終了。Chromeはそのまま使えます。")
    input("Enterで終了...")


if __name__ == "__main__":
    main()
