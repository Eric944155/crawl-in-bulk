import re
import validators
import pandas as pd
import io 
from urllib.parse import urlparse, urljoin

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
    
    # 更严格的电话号码正则表达式：
    # 目标：匹配更精确的电话号码，减少误报（排除日期、普通数字）
    # 尝试匹配格式：
    # 1. 国际格式：+国家码 (区号) 号码-号码 (如 +86 10 12345678, +1 (555) 123-4567)
    # 2. 国内格式：区号-号码 (如 010-12345678, 021-98765432)
    # 3. 手机号：1开头，11位数字 (中国大陆)
    # 4. 其它常见号码模式，如不带区号的本地号码
    # 主要改进：更长的数字序列，更明确的分隔符和前缀要求
    phone_regex = re.compile(
        r'''
        (?:                                # 非捕获组，用于匹配可选的国家代码或国际拨号前缀
            (?:\+)?\d{1,4}[-.\s]?           # 可选的 '+' 后面跟1-4位数字的国家代码，可选分隔符
            |00\d{1,4}[-.\s]?              # 或者 '00' 后面跟1-4位数字，可选分隔符
        )?
        (?:                                # 非捕获组，用于匹配可选的区号
            \(?\d{2,5}\)?[-.\s]?           # 可选的括号，2-5位数字的区号，可选分隔符
        )?
        \d{3,4}[-.\s]?\d{3,4}[-.\s]?\d{0,4} # 3-4位数字，可选分隔符，再3-4位数字，可选分隔符，最后0-4位（如分机号或更长号码）
        |                                  # 或者
        1[3-9]\d{9}                        # 严格匹配中国大陆11位手机号码 (13x, 14x, 15x, 16x, 17x, 18x, 19x)
        ''',
        re.VERBOSE # 允许使用注释和空白符，提高可读性
    )

    # 1. 从纯文本内容中提取邮箱和电话
    # get_text() 会获取页面所有可见文本
    text = soup.get_text()
    
    found_emails = email_regex.findall(text)
    emails.extend(found_emails)

    found_phones = phone_regex.findall(text)
    for phone in found_phones:
        cleaned_phone = re.sub(r'[^\d+]', '', phone) # 移除所有非数字字符，只保留数字和可选的开头的'+'
        # 进一步筛选：排除明显过短或过长的数字串，以及纯粹的日期数字串
        if 7 <= len(cleaned_phone) <= 15: # 一般电话号码长度在7-15位之间
            # 简单排除常见日期格式的纯数字串，如20230101，但这仍不完美
            if len(cleaned_phone) == 8 and cleaned_phone.startswith(('19', '20')): # 简单的年份日期排除
                continue 
            phones.append(cleaned_phone)

    # 2. 从 'mailto:' 和 'tel:' 链接中提取邮箱和电话
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']
        if href.startswith('mailto:'):
            email = href[len('mailto:'):].split('?')[0].strip() # 移除邮件主题等参数
            if email_regex.match(email): # 再次验证邮箱格式
                emails.append(email)
        elif href.startswith('tel:'):
            phone = href[len('tel:'):].split('?')[0].strip() # 移除电话参数
            cleaned_phone = re.sub(r'[^\d+]', '', phone)
            if 7 <= len(cleaned_phone) <= 15:
                phones.append(cleaned_phone)
    
    # 3. 尝试从更广泛的HTML元素属性中提取 (例如：data-email, content, placeholder, value, title等)
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
                    if 7 <= len(cleaned_phone) <= 15:
                        if len(cleaned_phone) == 8 and cleaned_phone.startswith(('19', '20')):
                            continue
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