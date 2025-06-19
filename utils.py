import re
import validators
import pandas as pd
import io 
from urllib.parse import urlparse, urljoin

# 社交媒体域名列表
# 进一步细化，包含更具体的社交媒体平台链接模式和常见路径
SOCIAL_DOMAINS = [
    'facebook.com/', 'twitter.com/', 'x.com/', 'instagram.com/', 
    'linkedin.com/company/', 'linkedin.com/in/', 'linkedin.com/groups/',
    'youtube.com/', # 更通用的YouTube链接，具体频道可在后面判断
    'pinterest.com/', 'tiktok.com/@', 'weibo.com/', 
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
    try:
        return validators.url(url)
    except validators.ValidationError:
        return False

# 清理和标准化URL
def clean_url(url):
    """
    清理和标准化URL格式
    """
    url = str(url).strip() # 确保是字符串
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url # 默认使用 http，requests 会自动重定向到 https
    return url

# 从BeautifulSoup对象中提取联系方式 (邮箱和电话)
def extract_contacts_from_soup(soup, base_url):
    """
    从BeautifulSoup对象中提取邮箱和电话
    """
    emails = []
    phones = []

    # 编译正则表达式，提高效率
    # 邮箱正则表达式：匹配标准的邮箱格式，支持多种顶级域名 (2到63位)
    email_regex = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,63}')
    
    # 电话号码正则表达式：匹配更广泛的电话号码格式，包括国家代码、区号、各种分隔符
    # 尽可能捕获常见的号码，但电话号码格式多样，难以完美覆盖所有情况
    phone_regex = re.compile(
        r'(?:(?:\+|00)\d{1,4}[-.\s]?)?' # 可选的国家代码，如 +86 或 0086
        r'(?:\(?\d{2,5}\)?[-.\s]?)?'    # 可选的区号，如 (010)
        r'\d{3,4}[-.\s]?\d{3,4}'        # 中间和最后一部分数字
        r'(?:[-.\s]?\d{1,4})?'         # 可选的扩展位或更长数字
    )

    # 1. 从纯文本内容中提取邮箱和电话
    # get_text() 会获取页面所有可见文本
    text = soup.get_text()
    
    found_emails = email_regex.findall(text)
    emails.extend(found_emails)

    found_phones = phone_regex.findall(text)
    for phone in found_phones:
        cleaned_phone = re.sub(r'[^\d+]', '', phone) # 移除所有非数字字符，只保留数字和可选的开头的'+'
        if cleaned_phone.startswith('+') and len(cleaned_phone) > 7: # 至少国家代码+7位数字
            phones.append(cleaned_phone)
        elif not cleaned_phone.startswith('+') and len(cleaned_phone) >= 7: # 至少7位纯数字
            phones.append(cleaned_phone)

    # 2. 从 'mailto:' 和 'tel:' 链接中提取邮箱和电话
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if href.startswith('mailto:'):
            email = href[len('mailto:'):].split('?')[0].strip() # 移除邮件主题等参数
            if '@' in email and '.' in email and email_regex.match(email): # 再次验证邮箱格式
                emails.append(email)
        elif href.startswith('tel:'):
            phone = href[len('tel:'):].split('?')[0].strip() # 移除电话参数
            cleaned_phone = re.sub(r'[^\d+]', '', phone)
            if len(cleaned_phone) >= 7:
                phones.append(cleaned_phone)
    
    # 3. 尝试从更广泛的HTML元素属性中提取 (例如：data-email, content, placeholder等)
    # 这种方式有助于捕获一些非标准但存在的联系信息
    for tag in soup.find_all(True): # 查找所有HTML标签
        for attr, value in tag.attrs.items():
            if isinstance(value, str): # 确保属性值是字符串
                # 检查邮箱
                found_emails_in_attr = email_regex.findall(value)
                emails.extend(found_emails_in_attr)
                
                # 检查电话
                found_phones_in_attr = phone_regex.findall(value)
                for phone in found_phones_in_attr:
                    cleaned_phone = re.sub(r'[^\d+]', '', phone)
                    if cleaned_phone.startswith('+') and len(cleaned_phone) > 7:
                        phones.append(cleaned_phone)
                    elif not cleaned_phone.startswith('+') and len(cleaned_phone) >= 7:
                        phones.append(cleaned_phone)

    # 去重并返回
    emails = list(set(emails))
    phones = list(set(phones))
    
    return emails, phones

# 从HTML中提取联系页面链接
def extract_contact_pages(soup, base_url):
    """
    从HTML中提取"联系我们"、"关于我们"、"常见问题"等页面链接
    """
    contact_keywords = ['contact', 'contact-us', 'contact_us', 'contactus', '联系', '联系我们', '与我们联系', '联络']
    about_keywords = ['about', 'about-us', 'about_us', 'aboutus', '关于', '关于我们']
    faq_keywords = ['faq', 'questions', '常见问题', 'help', '帮助']
    
    potential_pages = []
    
    # 优先级：直接的联系页面 -> 关于我们/FAQ页面
    # 同时检查链接文本和href属性
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        text = a.text.lower().strip()
        
        # 排除无效或内部锚点链接
        if not href or href == '#' or href.startswith('javascript:') or href.startswith('mailto:') or href.startswith('tel:'):
            continue
        
        # 将相对路径转换为绝对路径
        if not href.startswith(('http://', 'https://')):
            href = urljoin(base_url, href)
        
        # 确保是有效URL
        if not validate_url(href):
            continue

        # 检查链接文本或URL中是否包含联系关键词
        is_contact_page = any(keyword in href.lower() for keyword in contact_keywords) or \
                          any(keyword in text for keyword in contact_keywords)
        
        is_about_or_faq_page = (any(keyword in href.lower() for keyword in about_keywords) or any(keyword in text for keyword in about_keywords)) or \
                               (any(keyword in href.lower() for keyword in faq_keywords) or any(keyword in text for keyword in faq_keywords))
        
        if is_contact_page:
            potential_pages.append(href)
        elif is_about_or_faq_page: # 作为次要选项
            potential_pages.append(href)

    # 去重并返回
    return list(set(potential_pages))

# 从HTML中提取社交媒体链接
def extract_social_links(soup):
    """
    从HTML中提取社交媒体链接
    """
    social_links = []
    
    # 编译社交媒体域名列表，提高效率
    compiled_social_domains = [re.compile(re.escape(domain.rstrip('/'))) for domain in SOCIAL_DOMAINS]

    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        # 增加对链接的初步清理，移除末尾斜杠和参数，便于匹配
        clean_href = href.split('?')[0].split('#')[0].rstrip('/')
        
        for domain_pattern in compiled_social_domains:
            if domain_pattern.search(clean_href.lower()):
                social_links.append(href) # 保留原始链接以便完整性
                break # 找到一个匹配即可
    
    return list(set(social_links))

# 处理上传的网站列表文件或手动输入
def process_website_file(file):
    """
    处理上传的网站列表文件或手动输入的字符串，返回标准化的DataFrame。
    接受 file 对象 (UploadedFile 或 StringIO)。
    """
    df = None
    
    if hasattr(file, 'name') and file.name.endswith('.csv'):
        # 尝试使用UTF-8编码读取CSV，如果失败则尝试GBK
        try:
            df = pd.read_csv(file, encoding='utf-8')
        except UnicodeDecodeError:
            file.seek(0) # 重置文件指针
            df = pd.read_csv(file, encoding='gbk')
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

    # 尝试找到URL列，可能列名不是'URL'
    found_url_column = None
    for col in df.columns:
        if col.lower() == 'url':
            found_url_column = col
            break
    
    if found_url_column is None:
        if len(df.columns) == 1: # 如果只有一列，就当它是URL列
            df.columns = ['URL']
            found_url_column = 'URL'
        else:
            raise ValueError("文件中未找到'URL'列，请确保CSV文件包含名为'URL'的列或仅包含网址的单列。")
    
    df = df[[found_url_column]].rename(columns={found_url_column: 'URL'})

    # 清理 + 验证URL
    cleaned_urls = []
    # invalid_urls = [] # 暂时不需要记录无效URL，直接过滤掉
    for url in df['URL']:
        url = clean_url(str(url))
        if validate_url(url):
            cleaned_urls.append(url)
        # else:
            # invalid_urls.append(url) # 可以选择在此处记录并通知用户

    if not cleaned_urls:
        raise ValueError("未找到任何有效网址，请检查文件内容或输入格式。")

    valid_df = pd.DataFrame({'URL': list(set(cleaned_urls))})  # 去重
    return valid_df