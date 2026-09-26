import random
import string
from db import (
    init_db, create_user, get_user_by_name,
    create_class, get_class_by_code, join_class,
    list_classes_for_user, list_members,
    add_message, get_messages,
)
import ollama_client


def gen_code():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def input_nonempty(prompt):
    while True:
        v = input(prompt).strip()
        if v:
            return v


def login():
    print("\n=== ログイン ===")
    name = input_nonempty("名前: ")
    user = get_user_by_name(name)
    if user:
        print(f"おかえりなさい、{name}さん")
        return user
    uid = create_user(name)
    if uid is None:
        print("登録失敗")
        return None
    print(f"新規登録しました（{name}）")
    return get_user_by_name(name)


def create_class_flow(user):
    print("\n=== クラス作成 ===")
    title = input_nonempty("クラス名: ")
    subject = input_nonempty("科目（例: 数学 / 英語 / プログラミング）: ")
    description = input("説明（任意）: ").strip()
    code = gen_code()
    cid = create_class(title, subject, description, user["id"], code)
    if cid is None:
        print("作成失敗（コード重複の可能性）")
        return
    print(f"\nクラス作成完了！")
    print(f"参加コード: {code}")
    print(f"このコードを生徒に共有してください。")


def join_class_flow(user):
    print("\n=== クラス参加 ===")
    code = input_nonempty("参加コード: ")
    cls = get_class_by_code(code)
    if not cls:
        print("そのコードのクラスはありません")
        return
    ok = join_class(cls["id"], user["id"], role="student")
    if ok:
        print(f"「{cls['title']}」に参加しました")
    else:
        print("すでに参加しています")


def class_room(user, cls):
    print(f"\n=== {cls['title']}（{cls['subject']}）===")
    print("コマンド: /members /history /exit")
    print("AI教師に話しかけるには、そのまま入力\n")

    while True:
        user_input = input(f"{user['name']}> ").strip()
        if not user_input:
            continue
        if user_input == "/exit":
            print("退出しました")
            return
        if user_input == "/members":
            members = list_members(cls["id"])
            print("\n【メンバー】")
            for m in members:
                print(f"  - {m['name']}（{m['role']}）")
            print()
            continue
        if user_input == "/history":
            history = get_messages(cls["id"], limit=20)
            print("\n【履歴】")
            for m in history:
                tag = "AI" if m["sender_type"] == "ai" else m["sender_name"]
                print(f"  {tag}: {m['content']}")
            print()
            continue

        # ユーザー発言を保存
        add_message(cls["id"], "user", user["name"], user_input)

        # AI教師に渡す用の履歴
        history = get_messages(cls["id"], limit=30)
        members = [f"{m['name']}({m['role']})" for m in list_members(cls["id"])]

        msgs = ollama_client.build_teacher_prompt(
            subject=cls["subject"],
            title=cls["title"],
            description=cls["description"] or "",
            members=members,
            history=history,
        )

        print("AI教師: 考え中...", end="", flush=True)
        try:
            answer = ollama_client.chat(msgs)
        except Exception as e:
            print(f"\n[エラー] AIに接続できません: {e}")
            print("Ollamaが起動しているか確認してください。")
            continue
        print("\r" + " " * 30 + "\r", end="")
        print(f"AI教師: {answer}\n")
        add_message(cls["id"], "ai", "AI教師", answer)


def my_classes_flow(user):
    classes = list_classes_for_user(user["id"])
    if not classes:
        print("\n参加中のクラスはありません")
        return
    print("\n=== 参加中のクラス ===")
    for i, c in enumerate(classes, 1):
        print(f"{i}. {c['title']}（{c['subject']}）[{c['role']}]")

    sel = input("\n入るクラス番号（Enterで戻る）: ").strip()
    if not sel.isdigit():
        return
    idx = int(sel) - 1
    if 0 <= idx < len(classes):
        class_room(user, classes[idx])


def main():
    init_db()
    print("=== 仮想教室（AI教師入り）===")

    user = login()
    if user is None:
        return

    while True:
        print("\n--- メニュー ---")
        print("1. クラス作成（教師として）")
        print("2. クラス参加（生徒として）")
        print("3. 参加中のクラス")
        print("4. 終了")
        sel = input("> ").strip()

        if sel == "1":
            create_class_flow(user)
        elif sel == "2":
            join_class_flow(user)
        elif sel == "3":
            my_classes_flow(user)
        elif sel == "4":
            print("さようなら")
            break
        else:
            print("1〜4で選んで")


if __name__ == "__main__":
    main()