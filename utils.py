import re
import validators
import pandas as pd
import io 
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import selenium
from selenium import webdriver
from email_validator import validate_email, EmailNotValidError

# 社交媒体域名和对应的平台名称映射
# 优化：更全面，更精准的匹配模式
SOCIAL_MEDIA_PATTERNS = {
    "facebook": [r"facebook\.com/(?!sharer\.php)[\w\d\.-]+/?$", r"fb\.com/"], # 排除分享链接
    "twitter": [r"(?:twitter|x)\.com/[\w\d_]+/?$", r"t\.co/"],
    "linkedin": [r"linkedin\.com/(?:company|in|groups)/[\w\d\.-]+/?$"],
    "youtube": [r"youtube\.com/(?:channel/|user/|c/)?[\w\d\-_]+/?$", r"youtu\.be/"],
    "instagram": [r"instagram\.com/[\w\d\.-]+/?$"],
    "pinterest": [r"pinterest\.com/[\w\d\.-]+/?$"],
    "tiktok": [r"tiktok\.com/@[\w\d\.-]+/?$"],
    "weibo": [r"weibo\.com/(?:u/)?[\w\d]+/?$"],
    "vk": [r"vk\.com/(?!share\.php)[\w\d\.-]+/?$"],
    "reddit": [r"reddit\.com/user/[\w\d\.-]+/?$"],
    "snapchat": [r"snapchat\.com/add/[\w\d\.-]+/?$"],
    "whatsapp": [r"wa\.me/\d+", r"api\.whatsapp\.com/send"], # WhatsApp Direct links
    "telegram": [r"t\.me/[\w\d_]+", r"telegram\.me/[\w\d_]+"], # Telegram channels/users
    "medium": [r"medium\.com/@[\w\d\.-]+/?$"],
    "github": [r"github\.com/[\w\d\.-]+/?$"],
    "flickr": [r"flickr\.com/(?:photos|people)/[\w\d\.-]+/?$"],
    "tumblr": [r"[\w\d\.-]+\.tumblr\.com/?$"],
    "behance": [r"behance\.net/[\w\d\.-]+/?$"],
    "dribbble": [r"dribbble\.com/[\w\d\.-]+/?$"],
    "discord": [r"discord\.(?:gg|com/invite)/[\w\d]+"], # Discord invite links
    "twitch": [r"twitch\.tv/[\w\d_]+/?$"],
    "bilibili": [r"bilibili\.com/(?:@)?\d+/?$"], # Bilibili user/space
    "douyin": [r"douyin\.com/user/[\w\d_]+/?$"], # Douyin user profile
    "kuaishou": [r"kuaishou\.com/user/[\w\d_]+/?$"], # Kuaishou user profile
    "zhihu": [r"zhihu\.com/people/[\w\d-]+/?$"], # Zhihu user profile
    "xiaohongshu": [r"xiaohongshu\.com/user/profile/[\w\d]+/?$"], # Xiaohongshu user profile
    "vimeo": [r"vimeo\.com/(?:channels/)?[\w\d]+/?$"],
    "soundcloud": [r"soundcloud\.com/[\w\d\.-]+/?$"],
    "spotify": [r"open\.spotify\.com/(?:artist|user|show)/[\w\d]+/?$"]
}

# 编译所有正则表达式，提高效率
COMPILED_SOCIAL_PATTERNS = {
    platform: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for platform, patterns in SOCIAL_MEDIA_PATTERNS.items()
}

# 严格邮箱抓取配置
EMAIL_DOMAIN_WHITELIST = (
    'gmail.com', 'outlook.com', 'hotmail.com', 'yahoo.com', 'protonmail.com', 'zoho.com', 'qq.com',
    '163.com', '126.com', 'sina.com', 'yeah.net', 'foxmail.com', 'icloud.com', 'me.com', 'mail.com',
    'edu', 'org', 'info', 'co', 'net', 'cn', 'com'
)
EMAIL_KEYWORDS = [
    'email', 'e-mail', 'mail', 'contact', 'outreach', 'support', 'info', 'admin', 'sales', 'service', 'help',
    'gmail', '163', 'qq', 'yahoo', 'outlook', 'edu', 'org', 'net', 'com'
]
EMAIL_BLACKLIST = [
    'copyright', 'allrightsreserved', 'example.com', 'test@', 'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'webmaster@', 'admin@', 'root@', 'abuse@', 'hostmaster@', 'postmaster@'
]

def is_valid_email(email):
    if not isinstance(email, str) or len(email) < 6 or len(email) > 64:
        return False
    email = email.lower()
    if any(bad in email for bad in EMAIL_BLACKLIST):
        return False
    if not any(email.endswith('@' + d) or email.endswith('.' + d) for d in EMAIL_DOMAIN_WHITELIST):
        return False
    try:
        from email_validator import validate_email, EmailNotValidError
        validate_email(email, check_deliverability=False)
        return True
    except Exception:
        return False

def extract_valid_emails(text):
    import re
    text = normalize_email_text(text)
    lines = [line for line in text.split() if any(k in line.lower() for k in EMAIL_KEYWORDS)]
    text = ' '.join(lines)
    email_pattern = r'[a-zA-Z0-9._%+-]{3,64}@[a-zA-Z0-9.-]{2,64}\.[a-zA-Z]{2,10}'
    raw_emails = re.findall(email_pattern, text)
    emails = set()
    for email in raw_emails:
        if is_valid_email(email):
            emails.add(email)
    return list(emails)

# 邮箱反爬归一化函数
def normalize_email_text(text):
    """
    将各种反爬邮箱写法归一化为标准邮箱格式。
    支持多种混淆写法，如 [at]、(at)、{at}、#at#、-at-、&commat;、＠、[dot]、(dot)、{dot}、#dot#、-dot-、·、点、等。
    """
    import re
    if not text or not isinstance(text, str):
        return ''
    patterns = [
        (r'\s?\[at\]\s?|\s?\(at\)\s?|\s?\{at\}\s?|\s?\-at\-|\s?\#at\#|\s?\&commat;|\s?＠|\s?@\s?', '@'),
        (r'\s?\[dot\]\s?|\s?\(dot\)\s?|\s?\{dot\}\s?|\s?\-dot\-|\s?\#dot\#|\s?·|\s?点|\s?\.\s?', '.'),
        (r'\s?\[underscore\]\s?|\s?\(underscore\)\s?|\s?\_\s?', '_'),
        (r'\s?\[dash\]\s?|\s?\(dash\)\s?|\s?\-\s?', '-'),
        (r'\s?\[plus\]\s?|\s?\(plus\)\s?|\s?\+\s?', '+'),
        (r'\s?\[at symbol\]\s?', '@'),
    ]
    text = text.lower()
    for pat, repl in patterns:
        text = re.sub(pat, repl, text, flags=re.I)
    text = re.sub(r'\s+', '', text)
    return text

# 验证URL格式
def validate_url(url):
    """
    验证URL格式是否正确
    """
    try:
        # validators.url 已经足够健壮，但额外检查是否为空字符串
        if not url:
            return False
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

def extract_contacts_from_soup(soup, base_url):
    emails = set()
    # 1. 只在 mailto 提取
    for a in soup.find_all('a', href=True):
        href = normalize_email_text(a['href'])
        if href.startswith('mailto:'):
            emails.update(extract_valid_emails(href.replace('mailto:', '').split('?')[0]))
    # 2. 如果 mailto 没有，再在正文“强信号”区域查找
    if not emails:
        allowed_tags = ['p', 'span', 'div', 'li', 'td', 'address', 'section', 'article', 'main']
        for tag in soup.find_all(allowed_tags):
            txt = tag.get_text(separator=' ', strip=True)
            if any(k in txt.lower() for k in EMAIL_KEYWORDS):
                emails.update(extract_valid_emails(txt))
    # 3. 去重、去空、去伪邮箱
    emails = {e for e in emails if is_valid_email(e)}
    return list(emails)

# 从HTML中提取联系页面链接
def extract_contact_pages(soup, base_url):
    contact_keywords = ['contact', 'contact-us', 'contact_us', 'contactus', '联系', '联系我们', '与我们联系', '联络', '支持', 'support', 'help']
    about_keywords = ['about', 'about-us', 'about_us', 'aboutus', '关于', '关于我们', '公司', '企业', 'profile']
    faq_keywords = ['faq', 'questions', '常见问题', 'q&a']
    
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

# 从HTML中提取社交媒体链接并分类
def extract_social_links(soup):
    """
    从HTML中提取社交媒体链接，并按平台分类。
    返回一个字典，键为平台名称，值为该平台链接的列表。
    """
    social_links_by_platform = {}
    
    for a in soup.find_all('a', href=True):
        href = a['href'].strip()
        
        # 排除空链接、内部锚点、邮件或电话链接
        if not href or href == '#' or href.startswith(('javascript:', 'mailto:', 'tel:')):
            continue
        
        # 统一处理链接，移除查询参数和片段标识符，以便匹配
        clean_href = href.split('?')[0].split('#')[0].rstrip('/')
        
        found_platform = None
        for platform, patterns in COMPILED_SOCIAL_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(clean_href):
                    found_platform = platform
                    break
            if found_platform:
                break
        
        if found_platform:
            if found_platform not in social_links_by_platform:
                social_links_by_platform[found_platform] = []
            social_links_by_platform[found_platform].append(href) # 存储原始完整链接
    
    # 对每个平台的链接进行去重
    for platform in social_links_by_platform:
        social_links_by_platform[platform] = list(set(social_links_by_platform[platform]))
    
    return social_links_by_platform

# selenium 动态渲染支持
def get_rendered_html(url):
    from selenium import webdriver
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    html = driver.page_source
    driver.quit()
    return html

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