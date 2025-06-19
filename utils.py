import re
import validators
import pandas as pd

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
    # 新的正则表达式：匹配可选的+，然后是数字，
    # 接着是7个或更多个数字、空格、破折号或括号，最后以数字结尾。
    # 注意：在字符集[]中，-如果是字面字符，需要放在开头或结尾，或者转义。
    # 这里我们使用 r'[\d\s\-\(\)]' 来明确匹配数字、空白、连字符、左括号和右括号。
    phones = re.findall(r'\+?\d[\d\s\-\(\)]{7,}\d', text)
    
    return list(set(emails)), list(set(phones))

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
    import io

    # 尝试判断文件类型，优先使用文件名，如果file是StringIO对象则尝试读取内容判断
    # 加载内容
    file_content_decoded = None
    if hasattr(file, 'name') and file.name.endswith('.csv'): #
        df = pd.read_csv(file) #
    elif hasattr(file, 'name') and file.name.endswith('.txt'): #
        file_content_decoded = file.read().decode('utf-8', errors='ignore') #
        urls = [line.strip() for line in file_content_decoded.splitlines() if line.strip()] #
        df = pd.DataFrame({'URL': urls}) #
    elif isinstance(file, io.StringIO): #  <--- 新增：针对手动输入场景
        # 对于StringIO，我们假定它是txt格式的网址列表
        file_content_decoded = file.read() # StringIO已经包含解码后的字符串
        urls = [line.strip() for line in file_content_decoded.splitlines() if line.strip()]
        df = pd.DataFrame({'URL': urls})
    else:
        raise ValueError("不支持的文件格式或无效的输入，请上传.csv或.txt文件")

    # 尝试识别URL列
    if 'URL' not in df.columns:
        if len(df.columns) == 1:
            df.columns = ['URL']
        else:
            raise ValueError("CSV文件中未找到URL列")

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
