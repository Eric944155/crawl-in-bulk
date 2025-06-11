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
    phones = re.findall(r'\+?\d[\d\s-\(\)]{7,}\d', text)
    
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
    if file.name.endswith('.csv'):
        df = pd.read_csv(file)
    elif file.name.endswith('.txt'):
        # 假设txt文件每行一个URL
        content = file.read().decode('utf-8')
        urls = [url.strip() for url in content.split('\n') if url.strip()]
        df = pd.DataFrame({'URL': urls})
    else:
        raise ValueError("不支持的文件格式，请上传.csv或.txt文件")
    
    # 确保有URL列
    if 'URL' not in df.columns:
        if len(df.columns) == 1:
            # 如果只有一列，假设它是URL列
            df.columns = ['URL']
        else:
            raise ValueError("CSV文件中未找到URL列")
    
    # 清理和验证URL
    df['URL'] = df['URL'].apply(clean_url)
    df['is_valid'] = df['URL'].apply(validate_url)
    
    # 过滤无效URL
    valid_df = df[df['is_valid']].copy()
    valid_df.drop('is_valid', axis=1, inplace=True)
    
    # 去重
    valid_df.drop_duplicates(subset=['URL'], inplace=True)
    
    return valid_df