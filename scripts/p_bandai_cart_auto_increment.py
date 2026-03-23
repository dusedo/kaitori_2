"""
プレミアムバンダイ カート内商品の個数を自動変更するスクリプト

使い方:
  python p_bandai_cart_auto_increment.py

動作:
  1. ブラウザ起動 → 自動ログイン
  2. Enter押下で処理開始
  3. カートページをリロード → select要素の数量を最大4まで変更
  4. 3秒おきに繰り返し
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

LOGIN_URL = "https://p-bandai.jp/login/?c=1"
CART_URL = "https://p-bandai.jp/cart/"
LOGIN_ID = "kenduen@gmail.com"
LOGIN_PW = "ken0325"
MAX_QTY = 4
RELOAD_INTERVAL = 3  # 秒


def main():
    # ブラウザ起動（目視確認用にheadlessオフ）
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15)

    try:
        # --- 自動ログイン ---
        print("ログインページを開きます...")
        driver.get(LOGIN_URL)

        wait.until(EC.presence_of_element_located((By.ID, "login_id")))
        print("ログインID・パスワードを入力中...")

        login_input = driver.find_element(By.ID, "login_id")
        login_input.clear()
        login_input.send_keys(LOGIN_ID)

        pw_input = driver.find_element(By.ID, "password")
        pw_input.clear()
        pw_input.send_keys(LOGIN_PW)

        print("ログインボタンをクリック...")
        driver.find_element(By.ID, "btnLogin").click()

        # ページ遷移を待つ
        time.sleep(3)
        print(f"ログイン完了。現在のURL: {driver.current_url}")

        input("\nカート処理を開始するにはEnterを押してください...")

        # --- カート数量自動変更ループ ---
        print("自動処理を開始します...")
        round_num = 0

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
                elif current_val < target:
                    all_maxed = False

            if changed > 0:
                print(f"{changed}件の数量を変更。ページリロードを待ちます...")
            elif all_maxed and len(selects) > 0:
                print("\n全商品が最大数量に達しました。完了！")
                break
            else:
                print("変更不要。")

            print(f"{RELOAD_INTERVAL}秒後にリロードします...")
            time.sleep(RELOAD_INTERVAL)

        input("\n処理完了。Enterでブラウザを閉じます...")

    except KeyboardInterrupt:
        print("\n中断されました。")
    except Exception as e:
        print(f"エラー: {e}")
        input("Enterでブラウザを閉じます...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
