# -*- coding: utf-8 -*-
import os
import boto3
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv

# srs_logicから忘却曲線アルゴリズムを拝借
from srs_logic import evaluate_history_retention

# 環境変数の読み込み (.env)
load_dotenv()

def get_boto3_session():
    return boto3.Session(
        region_name=os.getenv('AWS_REGION'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
    )

def get_all_users_to_notify():
    """通知設定がONで、メアドが登録されているユーザーを取得"""
    session = get_boto3_session()
    dynamodb = session.resource('dynamodb')
    table = dynamodb.Table('Exam_Learning_Users')
    
    try:
        response = table.scan()
        users = response.get('Items', [])
        # 通知ON (True) かつ、emailが空文字ではないユーザーをリストアップ
        return [u for u in users if u.get('receive_notifications') and u.get('email')]
    except Exception as e:
        print(f"🚨 ユーザー取得エラー: {e}")
        return []

def get_user_history_raw(username):
    """Streamlitに依存せず純粋なPythonとして学習履歴を取得して忘却曲線を計算"""
    session = get_boto3_session()
    dynamodb = session.resource('dynamodb')
    table = dynamodb.Table('Exam_Learning_Logs')
    
    history = {}
    response = table.query(KeyConditionExpression=Key('user_id').eq(username))
    items = response.get('Items', [])
    while 'LastEvaluatedKey' in response:
        response = table.query(KeyConditionExpression=Key('user_id').eq(username), ExclusiveStartKey=response['LastEvaluatedKey'])
        items.extend(response.get('Items', []))
        
    items.sort(key=lambda x: x.get('timestamp', ''))
    
    for item in items:
        time_taken = float(item.get('time_taken', 0.0))
        if time_taken >= 900.0: # 15分以上は除外
            continue
            
        q_key = f"{item.get('exam_code')}_{item.get('year')}_{item.get('question_id')}"
        is_correct = bool(item.get('is_correct', False))
        confidence = str(item.get('answer_confidence', '少し自信あり'))
        ts_str = str(item.get('timestamp', ''))
        
        if q_key not in history:
            history[q_key] = {
                'last_correct': is_correct,
                'last_confidence': confidence,
                'last_timestamp': ts_str,
                'streak': 1 if is_correct else 0
            }
        else:
            history[q_key]['last_correct'] = is_correct
            history[q_key]['last_confidence'] = confidence
            history[q_key]['last_timestamp'] = ts_str
            history[q_key]['streak'] = history[q_key]['streak'] + 1 if is_correct else 0
            
    # 忘却曲線の計算アルゴリズムを通す
    return evaluate_history_retention(history)

def send_email(ses_client, to_email, subject, body_text):
    """SESを使用してメールを送信"""
    # ★ 送信元の名前をアプリ名で装飾します
    SENDER = "基本情報学習アプリ (送信専用) <exam.app.noreply@gmail.com>"
    
    try:
        response = ses_client.send_email(
            Source=SENDER,
            Destination={'ToAddresses': [to_email]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {'Text': {'Data': body_text, 'Charset': 'UTF-8'}}
            }
        )
        return True
    except Exception as e:
        print(f"🚨 {to_email} への送信に失敗: {e}")
        return False

def main():
    print("=== 🚀 リマインドメール送信バッチを開始します ===")
    session = get_boto3_session()
    ses_client = session.client('ses')
    
    users = get_all_users_to_notify()
    if not users:
        print("ℹ️ 通知対象のユーザーがいませんでした。処理を終了します。")
        return
        
    for user in users:
        user_id = user['user_id']
        email = user['email']
        
        history = get_user_history_raw(user_id)
        
        review_count = 0
        trick_count = 0
        
        for q_key, data in history.items():
            retention = data.get('retention', 100.0)
            last_correct = data.get('last_correct', False)
            last_confidence = data.get('last_confidence', '')
            
            # 💡 条件1: 記憶保持率が40%以下
            is_forgetting = retention <= 40.0
            # 💡 条件2: 自信満々で間違えた問題（メタ認知ギャップ）
            is_trick = (not last_correct) and (last_confidence == "自信あり")
            
            if is_forgetting or is_trick:
                review_count += 1
                if is_trick:
                    trick_count += 1
                    
        if review_count > 0:
            subject = "【基本情報学習アプリ】本日の復習リマインド"
            body = f"""{user_id} さん

現在、あなたの学習データと忘却曲線に基づき、「復習が強く推奨される問題」が【 {review_count} 問 】あります。

"""
            if trick_count > 0:
                body += f"⚠️ 特に、過去に「自信ありと答えて間違えた問題（思い込みの可能性）」が {trick_count} 問含まれています。\n\n"
            
            body += """記憶が完全に消えてしまう前に、アプリを開いて「要復習」フィルターから再挑戦しましょう！

▼ 学習アプリはこちら
https://(ここに後でStreamlitのURLを記載します)

--------------------------------------------------
※本メールは送信専用アドレスから自動配信されています。
※試験に合格したなど、今後の通知が不要な場合は、アプリのメニュー画面より「通知設定」をオフにしてください。
--------------------------------------------------
"""
            print(f"📧 {user_id} ({email}) にメールを送信します... (復習対象: {review_count}問)")
            if send_email(ses_client, email, subject, body):
                print("   -> ✅ 送信成功！")
        else:
            print(f"👍 {user_id} ({email}) は記憶が定着しており、復習対象の問題はありません。")
            
    print("=== 🎉 すべての送信処理が完了しました ===")

if __name__ == "__main__":
    main()