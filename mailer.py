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
电话：[您的电话]
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
    
    参数：
    - contacts: 包含联系方式的DataFrame
    - smtp_config: SMTP服务器配置字典
    - email_template: 邮件模板字符串
    - email_subject: 邮件主题
    - daily_limit: 每日发送上限
    - interval_seconds: 两封邮件之间的间隔秒数
    """
    # 默认SMTP配置（如果未提供）
    if smtp_config is None:
        raise ValueError("SMTP配置未提供。请在侧边栏配置SMTP服务器。")
    
    # 使用默认邮件模板
    if email_template is None:
        email_template = DEFAULT_EMAIL_TEMPLATE
    
    # 创建发送日志DataFrame
    log_columns = ['url', 'recipient', 'status', 'error', 'timestamp']
    send_log = pd.DataFrame(columns=log_columns)
    
    # 计数器
    sent_count = 0
    
    try:
        # 创建SMTP连接
        server = None
        if smtp_config['use_tls']:
            server = smtplib.SMTP(smtp_config['server'], smtp_config['port'])
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_config['server'], smtp_config['port'])
        
        server.login(smtp_config['email'], smtp_config['password'])
        
        # 遍历联系人发送邮件
        for contact in contacts.itertuples():
            # 检查是否有邮箱
            if not hasattr(contact, 'emails') or not contact.emails:
                continue
            
            # 获取网站名称和完整URL，用于模板填充
            full_url = contact.url
            parsed_url = urlparse(full_url)
            website_name = parsed_url.netloc # Gets 'example.com' or 'www.example.com'
            if website_name.startswith('www.'):
                website_name = website_name[4:] # Gets 'example.com' if starts with www.

            # 为每个邮箱发送邮件
            # 注意：这里假设一个网站的多个邮箱都发送同一封邮件
            # 如果需要对每个邮箱单独定制内容，可能需要更复杂的逻辑
            for email in contact.emails:
                # 检查是否达到每日上限
                if sent_count >= daily_limit:
                    print(f"已达到每日发送上限 {daily_limit} 封。停止发送。")
                    # 记录停止发送的日志
                    log_entry = pd.DataFrame([{
                        'url': 'N/A', # 没有具体的URL，表示是停止发送的事件
                        'recipient': 'N/A',
                        'status': 'stopped',
                        'error': f'Daily send limit ({daily_limit}) reached.',
                        'timestamp': pd.Timestamp.now()
                    }])
                    send_log = pd.concat([send_log, log_entry], ignore_index=True)
                    # 清理性退出所有循环
                    return send_log # 直接返回，结束函数执行

                # 创建邮件
                msg = MIMEMultipart()
                # 替换邮件主题中的变量
                formatted_subject = email_subject.format(website_name=website_name, url=full_url)
                msg['Subject'] = formatted_subject
                msg['From'] = smtp_config['email']
                msg['To'] = email
                
                # 替换邮件内容模板中的变量
                email_content = email_template.format(
                    website_name=website_name,
                    url=full_url,
                    # 可以添加更多变量，例如联系人姓名，但需要爬取时获取
                    # contact_name=contact.get('contact_name', '客户') # 假设contacts DataFrame中有'contact_name'列
                )
                
                # 添加邮件内容
                msg.attach(MIMEText(email_content, 'plain', 'utf-8'))
                
                try:
                    # 发送邮件
                    server.send_message(msg)
                    status = 'success'
                    error_msg = ''
                    print(f'邮件发送成功: {contact.url} -> {email}')
                except Exception as e:
                    status = 'failed'
                    error_msg = str(e)
                    print(f'邮件发送失败: {contact.url} -> {email}, 错误: {e}')
                
                # 记录日志
                log_entry = pd.DataFrame([{
                    'url': contact.url,
                    'recipient': email,
                    'status': status,
                    'error': error_msg,
                    'timestamp': pd.Timestamp.now()
                }])
                send_log = pd.concat([send_log, log_entry], ignore_index=True)
                
                # 增加计数器
                sent_count += 1
                
                # 间隔发送，避免被封
                if sent_count < daily_limit: # 只有在未达到上限时才等待
                    time.sleep(interval_seconds)
            
        # 关闭连接
        server.quit()
        
    except Exception as e:
        print(f"SMTP连接或发送过程中发生错误: {e}")
        log_entry = pd.DataFrame([{
            'url': 'N/A',
            'recipient': 'N/A',
            'status': 'global_error',
            'error': str(e),
            'timestamp': pd.Timestamp.now()
        }])
        send_log = pd.concat([send_log, log_entry], ignore_index=True)
    
    # 打印发送统计 (这些信息也会在Streamlit界面中显示)
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