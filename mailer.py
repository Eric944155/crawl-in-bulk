import smtplib
import time
import pandas as pd
from email.message import EmailMessage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random # 导入 random 模块

# 邮件模板
DEFAULT_EMAIL_TEMPLATE = """
尊敬的{company_or_website_name}团队：

您好！

我是[您的姓名]，来自[您的公司/组织]。我们注意到您的网站/产品/服务非常出色，希望能够与贵方建立合作关系。

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
def send_bulk_email(contacts, smtp_config=None, email_template=None, email_subject=None, daily_limit=50, interval_seconds=60):
    """
    群发邮件函数
    
    参数：
    - contacts: 包含联系方式的DataFrame
    - smtp_config: SMTP服务器配置字典
    - email_template: 邮件模板字符串
    - email_subject: 邮件主题字符串
    - daily_limit: 每日发送上限
    """
    # 默认SMTP配置
    if smtp_config is None:
        smtp_config = {
            'server': 'smtp.gmail.com',
            'port': 587,
            'email': 'your_email@gmail.com',
            'password': 'your_password',
            'use_tls': True
        }
    
    # 使用默认邮件模板
    if email_template is None:
        email_template = DEFAULT_EMAIL_TEMPLATE
    
    # 创建发送日志DataFrame
    log_columns = ['url', 'recipient', 'status', 'error', 'timestamp']
    send_log = pd.DataFrame(columns=log_columns)
    
    # 计数器
    sent_count = 0
    success_count = 0
    error_count = 0
    
    server = None # 初始化 server 变量
    try:
        # 创建SMTP连接
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
            
            # 获取网站名称和公司名称
            website_name = contact.url.split('//')[1].split('/')[0]
            if website_name.startswith('www.'):
                website_name = website_name[4:]

            company_or_website_name = contact.company_name if contact.company_name else website_name

            # 为每个邮箱发送邮件
            for email in contact.emails:
                # 再次检查是否达到每日上限，以防在遍历内层循环时超出
                if sent_count >= daily_limit:
                    print(f"已达到每日发送上限 {daily_limit} 封")
                    log_entry = pd.DataFrame([{
                        'url': 'N/A',
                        'recipient': 'N/A',
                        'status': 'stopped',
                        'error': f'Daily send limit ({daily_limit}) reached.',
                        'timestamp': pd.Timestamp.now()
                    }])
                    send_log = pd.concat([send_log, log_entry], ignore_index=True)
                    break # 跳出当前邮箱的循环
                
                # 创建邮件
                msg = MIMEMultipart()
                
                # 使用传入的主题，如果没有则构建一个
                subject = email_subject if email_subject else f'关于与{company_or_website_name}的合作机会'
                msg['Subject'] = subject
                msg['From'] = smtp_config['email']
                msg['To'] = email
                
                # 替换模板中的变量
                email_content = email_template.format(
                    website_name=website_name,
                    company_or_website_name=company_or_website_name, # 新增的变量
                    # 可以添加更多变量，如 {contact_name}，但需要爬取时获取
                    # {company_name} 也可以通过 website_name 来近似
                )
                
                # 添加邮件内容
                msg.attach(MIMEText(email_content, 'plain', 'utf-8'))
                
                try:
                    # 发送邮件
                    server.send_message(msg)
                    status = 'success'
                    error_msg = ''
                    success_count += 1
                    print(f'邮件发送成功: {contact.url} -> {email}')
                except Exception as e:
                    status = 'failed' # 更改为 'failed' 更明确
                    error_msg = str(e)
                    error_count += 1
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
                
                # 间隔发送，避免被封，增加随机性
                time.sleep(interval_seconds + random.uniform(0.5, 2.0))
            
            # 如果内层循环因为达到上限而跳出，外层循环也应跳出
            if sent_count >= daily_limit:
                break
        
        # 关闭连接
        if server: # 确保server存在再关闭
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
    
    # 打印发送统计
    print(f"\n发送统计:\n总计: {sent_count}\n成功: {success_count}\n失败: {error_count}")
    
    return send_log

# 配置SMTP服务器信息的函数
def configure_smtp(server, port, email, password, use_tls=True):
    """
    配置SMTP服务器信息
    """
    # 尝试连接SMTP服务器以验证配置
    try:
        if use_tls:
            with smtplib.SMTP(server, port) as s:
                s.starttls()
                s.login(email, password)
        else:
            with smtplib.SMTP_SSL(server, port) as s:
                s.login(email, password)
        return {
            'server': server,
            'port': port,
            'email': email,
            'password': password,
            'use_tls': use_tls
        }
    except Exception as e:
        raise Exception(f"SMTP配置验证失败: {str(e)}")

# 自定义邮件模板的函数 (保持不变)
def create_email_template(subject, body):
    """
    创建邮件模板，可以根据需求自定义
    """
    # 这里只是一个示例，您可以根据需要扩展模板功能
    return f"Subject: {subject}\n\n{body}"