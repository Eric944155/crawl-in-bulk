import re
import validators
import pandas as pd
import io # 确保这里导入了io模块

# 社交媒体域名列表
SOCIAL_DOMAINS = [
    'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com',
    'youtube.com', 'pinterest.com', 'tiktok.com', 'weibo.com',
    'wechat.com', 'qq.com', 'whatsapp.com', 'telegram.org'
]

# 验证URL格式
def validate_url(url):
    """
    验证URL格式是否正确
    """
    return validators.url(url)

# 清理和标准化URL
def clean_url(url):
    """
    清理和标准化URL格式
    """
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    return url

# 从文本中提取联系方式
def extract_contacts_from_text(text):
    """
    从文本中提取邮箱、电话、社交媒体链接等联系方式
    """
    # 提取邮箱
    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.[\w\.-]+', text)
    
    # 提取电话号码
    # 改进的正则表达式，尝试匹配常见的电话号码格式，包括可选的国家代码、区号以及各种分隔符
    # 匹配格式如：
    # +XX XXX XXX XXXX
    # (XXX) XXX-XXXX
    # XXX-XXX-XXXX
    # XXX XXX XXXX
    # 允许空格、连字符、括号、点、中间点作为分隔符，至少7位数字（不包括国家代码和区号）
    phones = re.findall(r'(?:\+\d{1,3}[-.●\s]?)?\(?\d{2,4}\)?[-.●\s]?\d{3,4}[-.●\s]?\d{3,4}(?:[-.●\s]?\d{1,4})?', text) #
    
    cleaned_phones = [] #
    for phone in phones: #
        # 移除所有非数字字符，只保留数字和可选的开头的'+'
        cleaned_phone = re.sub(r'[^\d+]', '', phone) #
        # 检查是否以'+'开头且后面是数字，或者直接是纯数字
        if cleaned_phone.startswith('+') and len(cleaned_phone) > 7: # 至少国家代码+7位数字
            cleaned_phones.append(cleaned_phone) #
        elif not cleaned_phone.startswith('+') and len(cleaned_phone) >= 7: # 至少7位纯数字
            cleaned_phones.append(cleaned_phone) #

    return list(set(emails)), list(set(cleaned_phones)) # 返回去重后的清理过的电话号码

# 从HTML中提取联系页面链接
def extract_contact_pages(soup, base_url):
    """
    从HTML中提取"联系我们"页面链接
    """
    contact_keywords = ['contact', 'contact-us', 'contact_us', 'contactus', '联系', '联系我们']
    contact_pages = []
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.text.lower()
        
        # 检查链接文本或URL中是否包含联系关键词
        if any(keyword in href.lower() for keyword in contact_keywords) or \
           any(keyword in text for keyword in contact_keywords):
            # 处理相对URL
            if not href.startswith(('http://', 'https://')):
                if href.startswith('/'):
                    href = base_url + href
                else:
                    href = base_url + '/' + href
            contact_pages.append(href)
    
    return list(set(contact_pages))

# 从HTML中提取社交媒体链接
def extract_social_links(soup):
    """
    从HTML中提取社交媒体链接
    """
    social_links = []
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        if any(domain in href.lower() for domain in SOCIAL_DOMAINS):
            social_links.append(href)
    
    return list(set(social_links))

# 处理上传的网站列表文件
def process_website_file(file):
    """
    处理上传的网站列表文件，返回标准化的DataFrame
    """
    # 无需再次导入io，因为它已经在文件顶部导入
    df = None # 初始化df，以防没有任何条件匹配
    
    # 增加对 StringIO 对象的处理，并使用 hasattr 检查 'name' 属性
    if hasattr(file, 'name') and file.name.endswith('.csv'):
        df = pd.read_csv(file)
    elif hasattr(file, 'name') and file.name.endswith('.txt'):
        # 对于txt文件，读取并解码
        content = file.read().decode('utf-8', errors='ignore')
        urls = [line.strip() for line in content.splitlines() if line.strip()]
        df = pd.DataFrame({'URL': urls})
    elif isinstance(file, io.StringIO): # 专门处理StringIO对象（例如手动输入）
        # 对于StringIO，它已经是字符串内容，无需解码
        content = file.read()
        urls = [line.strip() for line in content.splitlines() if line.strip()]
        df = pd.DataFrame({'URL': urls})
    else:
        raise ValueError("不支持的文件格式或无效的输入，请上传.csv或.txt文件，或提供有效的网址字符串。")

    # 如果df仍然为None，表示没有有效内容被处理
    if df is None or df.empty:
        raise ValueError("未能从文件中解析出有效数据。请检查文件内容或格式。")

    # 尝试识别URL列
    if 'URL' not in df.columns:
        if len(df.columns) == 1:
            df.columns = ['URL']
        else:
            raise ValueError("CSV文件中未找到URL列，或者文件中包含多列但没有名为'URL'的列。")

    # 清理 + 验证URL
    cleaned_urls = []
    invalid_urls = []
    for url in df['URL']:
        url = clean_url(str(url))
        try:
            if validate_url(url):
                cleaned_urls.append(url)
            else:
                invalid_urls.append(url)
        except Exception:
            invalid_urls.append(url)

    # 返回DataFrame
    if not cleaned_urls:
        raise ValueError("未找到任何有效网址，请检查文件内容")

    valid_df = pd.DataFrame({'URL': list(set(cleaned_urls))})  # 去重
    return valid_df