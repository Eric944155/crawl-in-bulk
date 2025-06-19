import smtplib
import time
import pandas as pd
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlparse

# 邮件模板
DEFAULT_EMAIL_TEMPLATE = """
尊敬的{website_name}团队：

您好！

我是[您的姓名]，来自[您的公司/组织]。我们注意到贵公司的网站（{url}）非常出色，希望能够与贵方建立合作关系。

如果您对此感兴趣，请回复此邮件或通过以下方式联系我：
邮箱：[您的邮箱]

期待您的回复！

此致
[您的姓名]
[您的职位]
[您的公司/组织]
"""

# 群发邮件的函数
def send_bulk_email(contacts, smtp_config=None, email_template=None, email_subject="合作机会", daily_limit=50, interval_seconds=60):
    """
    群发邮件函数
    只针对有邮箱的网站进行群发，移除电话相关引用
    """
    if smtp_config is None:
        raise ValueError("SMTP配置未提供。请在侧边栏配置SMTP服务器。")
    if email_template is None:
        email_template = DEFAULT_EMAIL_TEMPLATE
    log_columns = ['url', 'recipient', 'status', 'error', 'timestamp']
    send_log = pd.DataFrame(columns=log_columns)
    sent_count = 0
    try:
        server = None
        if smtp_config['use_tls']:
            server = smtplib.SMTP(smtp_config['server'], smtp_config['port'])
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_config['server'], smtp_config['port'])
        server.login(smtp_config['email'], smtp_config['password'])
        for contact in contacts.itertuples():
            # 只群发有邮箱的网站
            if not hasattr(contact, 'emails') or not contact.emails:
                continue
            full_url = contact.url
            parsed_url = urlparse(full_url)
            website_name = parsed_url.netloc
            if website_name.startswith('www.'):
                website_name = website_name[4:]
            for email in contact.emails:
                if sent_count >= daily_limit:
                    log_entry = pd.DataFrame([{
                        'url': 'N/A',
                        'recipient': 'N/A',
                        'status': 'stopped',
                        'error': f'Daily send limit ({daily_limit}) reached.',
                        'timestamp': pd.Timestamp.now()
                    }])
                    send_log = pd.concat([send_log, log_entry], ignore_index=True)
                    return send_log
                msg = MIMEMultipart()
                formatted_subject = email_subject.format(website_name=website_name, url=full_url)
                msg['Subject'] = formatted_subject
                msg['From'] = smtp_config['email']
                msg['To'] = email
                email_content = email_template.format(
                    website_name=website_name,
                    url=full_url
                )
                msg.attach(MIMEText(email_content, 'plain', 'utf-8'))
                try:
                    server.send_message(msg)
                    status = 'success'
                    error_msg = ''
                except Exception as e:
                    status = 'failed'
                    error_msg = str(e)
                log_entry = pd.DataFrame([{
                    'url': contact.url,
                    'recipient': email,
                    'status': status,
                    'error': error_msg,
                    'timestamp': pd.Timestamp.now()
                }])
                send_log = pd.concat([send_log, log_entry], ignore_index=True)
                sent_count += 1
                if sent_count < daily_limit:
                    time.sleep(interval_seconds)
        server.quit()
    except Exception as e:
        log_entry = pd.DataFrame([{
            'url': 'N/A',
            'recipient': 'N/A',
            'status': 'global_error',
            'error': str(e),
            'timestamp': pd.Timestamp.now()
        }])
        send_log = pd.concat([send_log, log_entry], ignore_index=True)
    print(f"\n发送统计:\n总计尝试: {len(send_log)}\n成功: {len(send_log[send_log['status'] == 'success'])}\n失败: {len(send_log[send_log['status'] == 'failed'])}")
    return send_log

# 配置SMTP服务器信息的函数
def configure_smtp(server, port, email, password, use_tls=True):
    """
    配置SMTP服务器信息，并尝试连接以验证
    """
    try:
        # 使用with语句确保SMTP连接被正确关闭
        if use_tls:
            with smtplib.SMTP(server, port, timeout=10) as s: # 增加连接超时
                s.starttls()
                s.login(email, password)
        else:
            with smtplib.SMTP_SSL(server, port, timeout=10) as s: # 增加连接超时
                s.login(email, password)
        return {
            'server': server,
            'port': port,
            'email': email,
            'password': password,
            'use_tls': use_tls
        }
    except smtplib.SMTPAuthenticationError:
        raise Exception("SMTP认证失败。请检查您的邮箱和密码（或授权码）是否正确。")
    except smtplib.SMTPConnectError as e:
        raise Exception(f"无法连接到SMTP服务器。请检查服务器地址和端口是否正确，网络是否畅通。错误详情: {e}")
    except smtplib.SMTPException as e:
        raise Exception(f"SMTP服务器错误: {e}")
    except Exception as e:
        raise Exception(f"SMTP配置验证失败: {str(e)}")