import re
import sys
from types import ModuleType
import validators
import pandas as pd
import io 
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
import selenium
from selenium import webdriver
from email_validator import validate_email, EmailNotValidError

try:
    from bs4 import Comment as _BS4Comment
except ImportError:
    try:
        from bs4.element import Comment as _BS4Comment
    except ImportError:
        class _BS4Comment(str):
            """Fallback Comment type when bs4 Comment is unavailable."""
            pass

if 'bs4.Comment' not in sys.modules:
    comment_module = ModuleType('bs4.Comment')
    comment_module.Comment = _BS4Comment
    sys.modules['bs4.Comment'] = comment_module

Comment = _BS4Comment

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

EMAIL_KEYWORDS = [
    'email', 'e-mail', 'mail', 'contact', 'outreach', 'support', 'info', 'admin', 'sales', 'service', 'help',
    'gmail', '163', 'qq', 'yahoo', 'outlook', 'edu', 'org', 'net', 'com'
]
EMAIL_BLACKLIST = [
    # 常见的非真实邮箱关键词
    'copyright', 'allrightsreserved', 'example.com', 'test@', 'noreply', 'no-reply', 'donotreply', 'do-not-reply',
    'webmaster@', 'admin@', 'root@', 'abuse@', 'hostmaster@', 'postmaster@',
    
    # 版权和设计相关
    'designedby', 'designedand', 'developedby', 'designedanddevelopedby', 'allrights', 'reserved',
    'poweredby', 'createdby', 'maintainedby', 'hostedby', 'madeby', 'builtby',
    
    # 年份组合
    '2020-', '2021-', '2022-', '2023-', '2024-', '2025-', '-2020', '-2021', '-2022', '-2023', '-2024', '-2025',
    
    # 社交媒体相关
    'facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 'pinterest', 'snapchat', 'tiktok',
    
    # 明显的非邮箱域名
    'designedand.developedby', 'allrights.reserved', 'all.rightsreserved'
]

_BASIC_EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}$')

def is_valid_email(email):
    # 1. 基本格式检查
    if not email or not isinstance(email, str):
        return False
    
    candidate = email.strip()
    
    # 2. 长度检查 (RFC 5321)
    if len(candidate) < 5 or len(candidate) > 254:
        return False
    
    # 3. 黑名单检查 - 检查是否包含任何黑名单关键词
    lower_candidate = candidate.lower()
    if any(b in lower_candidate for b in EMAIL_BLACKLIST):
        return False
    
    # 4. 使用 email_validator 进行标准化与严格验证
    try:
        normalized = validate_email(candidate, check_deliverability=False).email
        candidate = normalized
        lower_candidate = candidate.lower()
    except EmailNotValidError:
        # 如果email_validator认为无效，再使用基础正则作为兜底
        if not _BASIC_EMAIL_REGEX.fullmatch(candidate):
            return False
    except Exception:
        return False
    
    # 5. 基本结构检查
    if '@' not in candidate:
        return False
    
    username, domain = candidate.rsplit('@', 1)
    domain = domain.lower()
    
    # 6. 用户名检查
    if not username or len(username) > 64 or '..' in username:
        return False
    
    # 7. 域名检查
    if not domain or len(domain) > 255 or '.' not in domain:
        return False
    
    domain_parts = domain.split('.')
    if any(not part for part in domain_parts):
        return False
    
    tld = domain_parts[-1]
    if not tld.isalpha() or not (2 <= len(tld) <= 24):
        return False
    
    # 8. 最终黑名单检查（针对标准化后的邮箱）
    if any(b in lower_candidate for b in EMAIL_BLACKLIST):
        return False
    
    return True

def extract_valid_emails(text):
    import re
    text = normalize_email_text(text)
    
    # 预处理：移除可能导致误匹配的字符串
    text = re.sub(r'\d{4}@\d{4}', '', text)  # 移除类似 2025@2020 这样的年份组合
    text = re.sub(r'copyright|allrightsreserved|designedanddevelopedby', ' ', text, flags=re.I)  # 移除常见的版权信息
    
    # 更精确的邮箱正则表达式
    # 用户名部分：允许字母、数字、点、下划线、百分号、加号、减号
    # 域名部分：要求至少有一个点，且顶级域名为2-10个字母
    email_pattern = r'[a-zA-Z0-9][a-zA-Z0-9._%+-]{2,63}@(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,10}'
    
    # 查找所有可能的邮箱
    raw_emails = re.findall(email_pattern, text)
    
    # 验证并过滤
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
    同时移除可能导致误匹配的内容，如版权信息、年份组合等。
    """
    import re, html
    if not text or not isinstance(text, str):
        return ''
    
    # 1. 预处理：移除可能导致误匹配的内容
    # 移除版权信息
    text = re.sub(r'©\s*\d{4}[-–]?\d{0,4}', ' ', text)
    text = re.sub(r'copyright\s*\d{4}[-–]?\d{0,4}', ' ', text, flags=re.I)
    text = re.sub(r'all\s*rights\s*reserved', ' ', text, flags=re.I)
    
    # 移除设计和开发信息
    text = re.sub(r'designed\s*(and|&)\s*developed\s*by', ' ', text, flags=re.I)
    text = re.sub(r'powered\s*by', ' ', text, flags=re.I)
    text = re.sub(r'created\s*by', ' ', text, flags=re.I)
    
    # 移除年份组合（可能被误识别为邮箱）
    text = re.sub(r'\d{4}[-–]\d{4}', ' ', text)
    
    # 2. 移除HTML实体和标签
    text = html.unescape(text)  # 解码HTML实体
    text = re.sub(r'<[^>]+>', ' ', text)  # 移除HTML标签
    
    # 3. 处理各种混淆的邮箱格式
    patterns = [
        # 基本的混淆替换
        (r'\s?\[at\]\s?|\s?\(at\)\s?|\s?\{at\}\s?|\s?\-at\-|\s?\#at\#|\s?\&commat;|\s?＠|\s?@\s?', '@'),
        (r'\s?\[dot\]\s?|\s?\(dot\)\s?|\s?\{dot\}\s?|\s?\-dot\-|\s?\#dot\#|\s?·|\s?点|\s?\.\s?', '.'),
        (r'\s?\[underscore\]\s?|\s?\(underscore\)\s?|\s?\_\s?', '_'),
        (r'\s?\[dash\]\s?|\s?\(dash\)\s?|\s?\-\s?', '-'),
        (r'\s?\[plus\]\s?|\s?\(plus\)\s?|\s?\+\s?', '+'),
        (r'\s?\[at symbol\]\s?', '@'),
        
        # 更多的混淆模式
        (r'\s+at\s+', '@'),  # 空格分隔的 at
        (r'\s+dot\s+', '.'),  # 空格分隔的 dot
        (r'\s+AT\s+', '@'),  # 大写的 AT
        (r'\s+DOT\s+', '.'),  # 大写的 DOT
        (r'\s+At\s+', '@'),  # 首字母大写的 At
        (r'\s+Dot\s+', '.'),  # 首字母大写的 Dot
        
        # HTML编码的替换
        (r'&#64;|&#0064;|&#x40;|&#x0040;', '@'),  # @ 的 HTML 编码
        (r'&#46;|&#0046;|&#x2e;|&#x002e;', '.'),  # . 的 HTML 编码
    ]
    
    # 应用所有模式
    for pat, repl in patterns:
        text = re.sub(pat, repl, text, flags=re.I)
    
    # 4. 处理更复杂的混淆模式
    # 处理形如 "name at domain dot com" 的格式
    text = re.sub(r'([a-zA-Z0-9._%+-]+)\s+(?:at|AT|At)\s+([a-zA-Z0-9.-]+)\s+(?:dot|DOT|Dot)\s+([a-zA-Z]{2,10})', r'\1@\2.\3', text)
    
    # 5. 移除多余空白并转为小写
    text = re.sub(r'\s+', ' ', text).strip().lower()
    
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
    """增强版联系信息提取函数，支持更多提取策略和反爬处理"""
    emails = set()
    
    # 1. 处理隐藏的邮箱元素
    def process_hidden_elements(element):
        # 检查style属性中的display:none和visibility:hidden
        style = element.get('style', '')
        if 'display:none' in style.replace(' ', '') or 'visibility:hidden' in style.replace(' ', ''):
            return True
        return False
    
    # 2. 提取文本中的邮箱，包括反爬处理
    def extract_from_text(text):
        # 预处理文本
        text = normalize_email_text(text)
        # 提取并验证邮箱
        found_emails = extract_valid_emails(text)
        return found_emails
    
    # 3. 从各种来源提取邮箱
    
    # 3.1 从mailto链接提取（最可靠的来源）
    for a in soup.find_all('a', href=True):
        href = a['href']
        if not href:
            continue
        normalized_href = normalize_email_text(href)
        if normalized_href.startswith('mailto:'):
            clean_email = normalized_href.replace('mailto:', '', 1).split('?', 1)[0].strip()
            if clean_email:
                emails.update(extract_valid_emails(clean_email))
        elif 'mailto:' in href.lower():
            # 处理复杂的mailto编写方式，如 javascript:location='mailto:name@domain'
            snippet = href[href.lower().index('mailto:') + len('mailto:'):]
            clean_email = normalize_email_text(snippet).split('?', 1)[0].strip()
            if clean_email:
                emails.update(extract_valid_emails(clean_email))
    
    # 3.2 从图片alt和title属性提取
    for img in soup.find_all('img', alt=True):
        if '@' in img.get('alt', ''):
            emails.update(extract_from_text(img['alt']))
        if '@' in img.get('title', ''):
            emails.update(extract_from_text(img['title']))
    
    # 3.3 从data属性提取
    for elem in soup.find_all(lambda tag: any(attr for attr in tag.attrs if 'data-' in attr or 'aria-' in attr or attr in {'content', 'value'})):
        for attr, value in elem.attrs.items():
            if isinstance(value, str) and '@' in value and any(marker in attr for marker in ['data-', 'aria-', 'content', 'value', 'email']):
                emails.update(extract_from_text(value))

    # 3.4 从表单输入的占位符/默认值提取
    for field in soup.find_all(['input', 'textarea']):
        for attr in ('value', 'placeholder', 'data-placeholder'):
            val = field.get(attr)
            if isinstance(val, str) and '@' in val:
                emails.update(extract_from_text(val))

    # 3.5 从元标签和结构化数据提取
    for meta in soup.find_all('meta'):
        for attr in ('content', 'value', 'name'):
            val = meta.get(attr)
            if isinstance(val, str) and '@' in val:
                emails.update(extract_from_text(val))

    # 3.6 从注释中提取
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        if '@' in comment:
            emails.update(extract_from_text(comment))

    # 3.7 从脚本、样式和noscript标签中提取
    for tag in soup.find_all(['script', 'style', 'noscript']):
        content = tag.string
        if isinstance(content, str):
            lowered = content.lower()
            if any(token in lowered for token in ['@', '[at]', '(at', '{at', ' at ', ' dot ', '[dot]', '(dot', '{dot']):
                emails.update(extract_from_text(content))
    
    # 3.8 从联系相关区域提取
    contact_keywords = ['contact', 'about', 'support', 'help', 'team', '联系', '关于', '支持', '团队']
    
    # 通过ID查找
    contact_sections = soup.find_all(lambda tag: tag.get('id', '').lower() and 
                                   any(keyword in tag.get('id', '').lower() for keyword in contact_keywords))
    
    # 通过class查找
    contact_sections += soup.find_all(lambda tag: tag.get('class', []) and 
                                    any(any(keyword in cls.lower() for keyword in contact_keywords) 
                                        for cls in tag.get('class', [])))
    
    # 通过role属性查找
    contact_sections += soup.find_all(['div', 'section'], role=lambda r: r and 'contentinfo' in r.lower())
    
    # 如果找到特定区域，优先在这些区域查找
    search_areas = contact_sections if contact_sections else [soup]
    
    # 在所有可能的区域中查找邮箱
    for area in search_areas:
        # 检查所有可能包含文本的元素
        for elem in area.find_all(['p', 'span', 'div', 'li', 'td', 'address', 'a', 'label', 'strong', 'em']):
            # 检查元素是否隐藏
            if process_hidden_elements(elem):
                continue
                
            # 获取元素文本
            text = elem.get_text(separator=' ', strip=True)
            
            # 检查是否包含邮箱相关特征
            if '@' in text or any(k in text.lower() for k in EMAIL_KEYWORDS):
                # 排除版权信息
                if not any(x in text.lower() for x in ['copyright', 'all rights reserved', '©']):
                    emails.update(extract_from_text(text))
            
            # 检查title属性
            if elem.get('title') and '@' in elem['title']:
                emails.update(extract_from_text(elem['title']))
    
    # 3.9 兜底：扫描整页文本，捕获遗漏的邮箱
    full_text = soup.get_text(separator=' ', strip=True)
    if full_text and '@' in full_text:
        emails.update(extract_from_text(full_text))
    
    # 4. 验证所有提取到的邮箱
    valid_emails = set()
    for email in emails:
        if is_valid_email(email):
            valid_emails.add(email)
    
    return list(valid_emails)

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
def get_rendered_html(url, wait_time=5):
    """增强版动态渲染函数，支持更多配置和更好的稳定性"""
    from selenium import webdriver
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import TimeoutException, WebDriverException
    import time
    
    options = webdriver.ChromeOptions()
    # 基本配置
    options.add_argument('--headless=new')  # 新版无头模式
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    # 性能优化
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-setuid-sandbox')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-logging')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    
    # 内存优化
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-default-apps')
    
    # 反爬虫配置
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    
    # 模拟真实浏览器
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--start-maximized')
    options.add_argument(f'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{webdriver.__version__} Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=options)
        # 修改 navigator.webdriver 标志
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # 设置页面加载超时
        driver.set_page_load_timeout(wait_time * 2)
        driver.get(url)
        
        # 等待页面加载完成
        try:
            WebDriverWait(driver, wait_time).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # 执行滚动以触发懒加载
            driver.execute_script("""
                window.scrollTo(0, 0);
                window.scrollTo(0, document.body.scrollHeight/2);
                window.scrollTo(0, document.body.scrollHeight);
            """)
            
            # 等待动态内容加载
            time.sleep(wait_time / 2)
            
            # 尝试点击可能的展开按钮或"显示更多"链接
            try:
                buttons = driver.find_elements(By.XPATH, "//*[contains(text(), 'more') or contains(text(), 'Show') or contains(text(), 'expand') or contains(text(), '更多') or contains(text(), '展开')]") 
                for button in buttons[:3]:  # 限制尝试次数
                    try:
                        button.click()
                        time.sleep(1)
                    except:
                        continue
            except:
                pass
            
        except TimeoutException:
            pass  # 即使超时也继续获取页面源码
        
        # 获取渲染后的HTML
        html = driver.page_source
        return html
    
    except Exception as e:
        raise Exception(f"Selenium error: {str(e)}")
    
    finally:
        try:
            driver.quit()
        except:
            pass

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
        # 修正：手动输入时，确保每行非空网址被正确提取
        urls = [line.strip() for line in content.splitlines() if line.strip()] # 关键修正行
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
    for url in df['URL']:
        url = clean_url(str(url))
        if validate_url(url):
            cleaned_urls.append(url)

    if not cleaned_urls:
        raise ValueError("未找到任何有效网址，请检查文件内容或输入格式。")

    valid_df = pd.DataFrame({'URL': list(set(cleaned_urls))})  # 去重
    return valid_df
