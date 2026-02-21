"""
クイズアプリのテストコード

テストとは「プログラムが正しく動くか自動でチェックする仕組み」
実行方法: python quiz/test_quiz.py
"""

import json
import re
import sys
import io

# Windows の文字コード問題を回避
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# questions.js からデータを読み込む
def load_questions():
    with open("quiz/questions.js", encoding="utf-8") as f:
        content = f.read()
    # JavaScript の配列部分を抜き出す
    match = re.search(r'\[.*\]', content, re.DOTALL)
    # JavaScript → JSON に変換（末尾カンマを除去）
    json_str = match.group()
    # JavaScript のキー名にダブルクォートを付ける（question: → "question":）
    json_str = re.sub(r'(\w+)\s*:', r'"\1":', json_str)
    # シングルクォートをダブルクォートに変換
    json_str = json_str.replace("'", '"')
    # 末尾カンマを除去
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)
    return json.loads(json_str)


# --- テスト関数 ---

def test_問題が10個ある():
    questions = load_questions()
    assert len(questions) == 10, f"問題数が{len(questions)}個です（期待: 10個）"
    print("✅ 問題が10個ある")


def test_すべての問題に必要な項目がある():
    questions = load_questions()
    必要な項目 = ["question", "choices", "answer", "explanation"]
    for i, q in enumerate(questions):
        for key in 必要な項目:
            assert key in q, f"問題{i+1}に「{key}」がありません"
    print("✅ すべての問題に必要な項目がある")


def test_選択肢が4つずつある():
    questions = load_questions()
    for i, q in enumerate(questions):
        count = len(q["choices"])
        assert count == 4, f"問題{i+1}の選択肢が{count}個です（期待: 4個）"
    print("✅ 選択肢が4つずつある")


def test_正解の番号が選択肢の範囲内():
    questions = load_questions()
    for i, q in enumerate(questions):
        answer = q["answer"]
        max_index = len(q["choices"]) - 1
        assert 0 <= answer <= max_index, \
            f"問題{i+1}の正解番号が{answer}ですが、選択肢は0〜{max_index}です"
    print("✅ 正解の番号が選択肢の範囲内")


def test_問題文が空でない():
    questions = load_questions()
    for i, q in enumerate(questions):
        assert len(q["question"]) > 0, f"問題{i+1}の問題文が空です"
        assert len(q["explanation"]) > 0, f"問題{i+1}の解説が空です"
    print("✅ 問題文と解説が空でない")


# --- テスト実行 ---

if __name__ == "__main__":
    print("🧪 クイズアプリのテストを実行します...\n")

    tests = [
        test_問題が10個ある,
        test_すべての問題に必要な項目がある,
        test_選択肢が4つずつある,
        test_正解の番号が選択肢の範囲内,
        test_問題文が空でない,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1

    print(f"\n📊 結果: {passed}個成功 / {len(tests)}個中")
    if failed == 0:
        print("🎉 全テスト合格！")
    else:
        print(f"⚠️ {failed}個のテストが失敗しました")
