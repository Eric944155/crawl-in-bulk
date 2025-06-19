import re
import validators
import pandas as pd
import io # 确保这里导入了io模块
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup # 明确导入BeautifulSoup
import html # 用于HTML实体解码

# 社交媒体域名列表
SOCIAL_DOMAINS = [
    'facebook.com/', 'twitter.com/', 'x.com/', 'instagram.com/',
    'linkedin.com/company/', 'linkedin.com/in/', 'linkedin.com/groups/',
    'youtube.com/', 'pinterest.com/', 'tiktok.com/@', 'weibo.com/',
    'vk.com/', 'reddit.com/user/', 'snapchat.com/add/',
    'whatsapp.com/', 'telegram.org/', 'medium.com/@', 'github.com/',
    'flickr.com/', 'tumblr.com/', 'behance.net/', 'dribbble.com/'
]

# 验证URL格式
def validate_url(url):
    """
    验证URL格式是否正确
    """
    # 增加对URL验证的健壮性，允许更多的有效URL格式
    return validators.url(url)

# 清理和标准化URL
def clean_url(url):
    """
    清理和标准化URL格式
    """
    url = str(url).strip() # 确保是字符串
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url # 默认使用 http，requests 会自动重定向到 https
    return url

# 从BeautifulSoup对象中提取联系方式
def extract_contacts_from_soup(soup, base_url):
    """
    从BeautifulSoup对象中提取邮箱和电话
    """
    emails = []
    phones = []

    # 1. 从纯文本中提取邮箱和电话
    # 先进行HTML实体解码，再进行正则匹配
    decoded_text = html.unescape(soup.get_text())
    text_emails, text_phones = extract_contacts_from_text_regex(decoded_text)
    emails.extend(text_emails)
    phones.extend(text_phones)

    # 2. 从 'mailto:' 和 'tel:' 链接中提取邮箱和电话
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if href.startswith('mailto:'):
            email = href[len('mailto:'):].split('?')[0] # 移除邮件主题等参数
            if '@' in email and '.' in email: # 简单验证邮箱格式
                emails.append(email)
        elif href.startswith('tel:'):
            phone = href[len('tel:'):].split('?')[0] # 移除电话参数
            cleaned_phone = clean_phone_number(phone) # 使用新的清洗函数
            if cleaned_phone:
                phones.append(cleaned_phone)
    
    # 3. 尝试从 <script> 标签中提取邮箱 (有限的动态内容尝试)
    # 有些网站会在JS变量中存储邮箱
    for script in soup.find_all('script'):
        script_content = script.string
        if script_content:
            script_emails, _ = extract_contacts_from_text_regex(script_content)
            emails.extend(script_emails)

    # 4. 尝试从常见的邮箱显示位置提取
    # 比如查找class或id中包含'email', 'contact', 'mail'的元素
    for tag in soup.find_all(lambda tag: tag.name in ['div', 'span', 'p', 'li', 'a'] and 
                                          (tag.get('class', '') and any(c in str(tag.get('class')).lower() for c in ['email', 'mail', 'contact']) or
                                           tag.get('id', '') and any(i in str(tag.get('id')).lower() for i in ['email', 'mail', 'contact']))):
        element_text = html.unescape(tag.get_text()) # 对元素文本也进行解码
        element_emails, element_phones = extract_contacts_from_text_regex(element_text)
        emails.extend(element_emails)
        phones.extend(element_phones)

    # 去重
    emails = list(set(emails))
    phones = list(set(phones))
    
    return emails, phones

# 新增一个函数，用于从纯文本中提取邮箱和电话（原 extract_contacts_from_text 逻辑）
def extract_contacts_from_text_regex(text):
    """
    从纯文本中提取邮箱和电话号码，并尝试处理一些简单的混淆
    """
    # 邮箱正则表达式：更鲁棒，尝试处理 [at] [dot] 混淆
    # 匹配标准邮箱，也尝试匹配 info[at]domain[dot]com 这样的形式
    email_regex = re.compile(
        r'[a-zA-Z0-9._%+-]+(?:\s*\[?at\]?|\s*@\s*)[a-zA-Z0-9.-]+(?:\s*\[?dot\]?|\s*\.\s*)[a-zA-Z]{2,63}',
        re.IGNORECASE
    )
    
    raw_emails = email_regex.findall(text)
    emails = []
    for email in raw_emails:
        # 清理混淆
        cleaned_email = email.replace('[at]', '@').replace('(at)', '@').replace('[dot]', '.').replace('(dot)', '.').replace(' at ', '@').replace(' dot ', '.').replace(' ', '').strip()
        # 再次验证清理后的邮箱格式
        if '@' in cleaned_email and '.' in cleaned_email and cleaned_email.count('@') == 1:
            emails.append(cleaned_email)
    
    # 电话号码正则表达式：匹配更广泛的格式
    # 匹配模式如：+1 (123) 456-7890, 0086-10-87654321, (021) 12345678, 13812345678
    # 这是一个相对复杂的正则，旨在覆盖多种情况
    phone_regex = re.compile(
        r'(?:(?:\+|00)\d{1,3}[-.\s]?)?'          # 可选的国家代码，如 +86 或 0086
        r'(?:\(?\d{2,5}\)?[-.\s]?)?'             # 可选的区号，如 (010)
        r'\d{3,4}[-.\s]?\d{3,4}'                 # 中间和最后一部分数字
        r'(?:[-.\s]?\d{1,4})?',                  # 可选的扩展位或更长数字
        re.IGNORECASE
    )
    
    raw_phones = phone_regex.findall(text)
    phones = [clean_phone_number(p) for p in raw_phones if clean_phone_number(p)]

    return list(set(emails)), list(set(phones))

def clean_phone_number(phone):
    """
    清理电话号码，只保留数字和可选的开头的'+'
    """
    cleaned_phone = re.sub(r'[^\d+]', '', phone) # 移除所有非数字字符，只保留数字和可选的开头的'+'
    # 检查是否以'+'开头且后面是数字，或者直接是纯数字，并且长度合理
    if (cleaned_phone.startswith('+') and len(cleaned_phone) > 7) or \
       (not cleaned_phone.startswith('+') and len(cleaned_phone) >= 7):
        return cleaned_phone
    return None


# 从HTML中提取联系页面链接
def extract_contact_pages(soup, base_url):
    """
    从HTML中提取"联系我们"页面链接，并扩展到“关于我们”等相关页面
    """
    contact_keywords = ['contact', 'contact-us', 'contact_us', 'contactus', '联系', '联系我们', 'support', '服务']
    about_keywords = ['about', 'about-us', 'about_us', 'aboutus', '关于', '关于我们', 'company', '企业']
    faq_keywords = ['faq', 'questions', '常见问题', '帮助']
    
    potential_pages = []
    
    # 优先查找导航栏和页脚中的链接，因为联系信息常出现在这些位置
    nav_footer_tags = soup.find_all(['nav', 'footer'])
    search_scope_tags = [soup] + nav_footer_tags # 优先在导航和页脚中查找，然后是整个页面

    for scope_tag in search_scope_tags:
        for a in scope_tag.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True).lower() # 更健壮地获取文本
            
            # 将相对路径转换为绝对路径
            if not href.startswith(('http://', 'https://')):
                href = urljoin(base_url, href)

            # 避免无效或内部锚点链接
            if not href or href == '#' or href.startswith('javascript:'):
                continue
            
            # 检查链接文本或URL中是否包含联系、关于、FAQ关键词
            if any(keyword in href.lower() for keyword in contact_keywords + about_keywords + faq_keywords) or \
               any(keyword in text for keyword in contact_keywords + about_keywords + faq_keywords):
                potential_pages.append(href)
    
    # 对所有收集到的链接进行去重并返回
    return list(set(potential_pages))

# 从HTML中提取社交媒体链接
def extract_social_links(soup):
    """
    从HTML中提取社交媒体链接
    """
    social_links = []
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        # 检查是否包含社交媒体域名
        # 增加对链接的初步清理，移除末尾斜杠和参数，便于匹配
        clean_href = href.split('?')[0].split('#')[0].rstrip('/')
        
        if any(domain.rstrip('/') in clean_href.lower() for domain in SOCIAL_DOMAINS):
            social_links.append(href) # 保留原始链接以便完整性
    
    return list(set(social_links))

# 处理上传的网站列表文件
def process_website_file(file):
    """
    处理上传的网站列表文件，返回标准化的DataFrame
    """
    df = None
    
    if hasattr(file, 'name') and file.name.endswith('.csv'):
        df = pd.read_csv(file)
    elif hasattr(file, 'name') and file.name.endswith('.txt'):
        content = file.read().decode('utf-8', errors='ignore')
        urls = [line.strip() for line in content.splitlines() if line.strip()]
        df = pd.DataFrame({'URL': urls})
    elif isinstance(file, io.StringIO): # 专门处理StringIO对象（例如手动输入）
        content = file.read()
        urls = [line.strip() for line in content.splitlines() if line.strip()]
        df = pd.DataFrame({'URL': urls})
    else:
        raise ValueError("不支持的文件格式或无效的输入，请上传.csv或.txt文件，或提供有效的网址字符串。")

    if df is None or df.empty:
        raise ValueError("未能从文件中解析出有效数据。请检查文件内容或格式。")

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

    if not cleaned_urls:
        raise ValueError("未找到任何有效网址，请检查文件内容")

    valid_df = pd.DataFrame({'URL': list(set(cleaned_urls))})  # 去重
    return valid_df