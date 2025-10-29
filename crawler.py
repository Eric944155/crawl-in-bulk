import time
import requests
from urllib.parse import urlparse, urlunparse
from bs4 import BeautifulSoup
from utils import extract_contacts_from_soup, extract_social_links, get_rendered_html, is_valid_email, clean_url
import pandas as pd

# 强化邮箱抓取，移除电话，结构极简

CONTACT_PAGE_KEYWORDS = [
    # 英文关键词
    'contact', 'contact-us', 'contactus', 'contact_us', 'reach-us', 'reach_us', 'reachus',
    'about', 'about-us', 'aboutus', 'about_us', 'company', 'our-team', 'our_team', 'ourteam',
    'support', 'customer-support', 'customer_support', 'customersupport',
    'help', 'helpdesk', 'help-desk', 'help_desk', 'faq', 'feedback',
    'team', 'staff', 'people', 'members', 'employees', 'leadership',
    'info', 'information', 'connect', 'get-in-touch', 'get_in_touch', 'getintouch',
    'privacy', 'impressum', 'imprint', 'legal', 'terms',
    'customer', 'service', 'customer-service', 'customer_service', 'customerservice',
    'email', 'mail', 'e-mail', 'email-us', 'email_us', 'emailus',
    'enquiry', 'enquiries', 'inquiry', 'inquiries',
    
    # 中文关键词
    '联系', '联系我们', '联络', '联络我们', '取得联系', '联系方式',
    '关于', '关于我们', '公司介绍', '企业介绍', '团队介绍',
    '客服', '客户服务', '服务支持', '技术支持', '帮助中心',
    '团队', '我们的团队', '专业团队', '员工', '成员',
    '邮箱', '电子邮件', '电子邮箱', '邮件联系',
    '合作', '商务合作', '业务合作', '合作伙伴',
    '咨询', '在线咨询', '信息咨询', '咨询服务'
]
MAX_RETRIES = 2

def _generate_url_variants(url):
    """生成一组候选URL，用于在网络不稳定或跳转规则复杂时重试。"""
    url = url.strip()
    if not url:
        return []
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    parsed = urlparse(url)
    netloc = parsed.netloc or ''
    path = parsed.path or '/'
    
    host_variants = []
    if netloc:
        host_variants.append(netloc)
        if not netloc.lower().startswith('www.'):
            host_variants.append(f'www.{netloc}')
    else:
        host_variants.append('')
    
    scheme_variants = []
    if parsed.scheme:
        scheme_variants.append(parsed.scheme)
    if 'https' not in scheme_variants:
        scheme_variants.insert(0, 'https')
    if 'http' not in scheme_variants:
        scheme_variants.append('http')
    
    variants = []
    for scheme in scheme_variants:
        for host in host_variants:
            variant = urlunparse((scheme, host, path, parsed.params, parsed.query, ''))
            variants.append(variant)
    # 去重同时保持顺序
    seen = set()
    ordered = []
    for v in variants:
        if v not in seen:
            ordered.append(v)
            seen.add(v)
    return ordered

def robust_get(url, headers, timeout=15):
    """
    增强版网页请求函数：
    1. 自动切换 http/https
    2. 处理常见错误（SSL错误、连接超时等）
    3. 智能重试
    4. 处理重定向
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # 禁用SSL警告
    session = requests.Session()
    session.headers.update(headers)
    errors = []
    variants = _generate_url_variants(url)
    for candidate in variants:
        try:
            resp = session.get(
                candidate,
                timeout=timeout,
                allow_redirects=True,
                verify=False
            )
            if resp.status_code < 400:
                return resp, None
            errors.append(f'{candidate}: HTTP {resp.status_code}')
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.TooManyRedirects, requests.exceptions.SSLError) as e:
            errors.append(f'{candidate}: {e}')
        except Exception as e:
            errors.append(f'{candidate}: {e}')
        if len(errors) >= MAX_RETRIES and len(errors) >= len(variants):
            break
    deduped_errors = []
    seen = set()
    for err in errors:
        if err not in seen:
            deduped_errors.append(err)
            seen.add(err)
    return None, '; '.join(deduped_errors) if deduped_errors else 'Unknown connection error'


def crawl_contacts(websites, use_selenium=True, max_depth=2):
    # 增强的请求头和配置
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Referer': 'https://www.google.com/'
    }
    contacts = []
    for url_entry in websites['URL']: # Iterate through the URL column
        base_url = clean_url(url_entry)
        current_site_emails = set()
        social_links_main_dict = {}
        error_msgs = []
            
        # 1. 主页面请求
        resp, err = robust_get(base_url, headers)
        if err:
            error_msgs.append(f'{base_url}: {err}')
            soup = None
        else:
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 2. 主页面邮箱与社媒
            try:
                current_site_emails.update(extract_contacts_from_soup(soup, base_url))
            except Exception as e:
                error_msgs.append(f'{base_url} extraction error: {e}')
            sl = extract_social_links(soup)
            for k, v in sl.items():
                social_links_main_dict.setdefault(k, set()).update(v)
        
        # 3. 递归所有潜在联系页
        contact_pages = set()
        if soup:
            # 更智能地识别联系页面
            # 1. 检查链接文本
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text().lower().strip()
                
                # 排除无效链接
                if not href or href == '#' or href.startswith('javascript:') or href.startswith('mailto:') or href.startswith('tel:'):
                    continue
                
                # 检查链接文本和href属性
                if any(k in href.lower() for k in CONTACT_PAGE_KEYWORDS) or any(k in text for k in CONTACT_PAGE_KEYWORDS):
                    full_url = requests.compat.urljoin(base_url, href)
                    contact_pages.add(full_url)
            
            # 2. 查找页脚中的联系链接（通常包含联系信息）
            footer_tags = soup.find_all(['footer', 'div', 'section'], class_=lambda c: c and any(x in str(c).lower() for x in ['footer', 'bottom']))
            for footer in footer_tags:
                for a in footer.find_all('a', href=True):
                    href = a['href']
                    if not href or href == '#' or href.startswith('javascript:'):
                        continue
                    full_url = requests.compat.urljoin(base_url, href)
                    contact_pages.add(full_url)
        
        # 限制爬取页面数量，优先处理最可能包含联系信息的页面
        contact_pages = sorted(list(contact_pages), key=lambda url: sum(1 for k in CONTACT_PAGE_KEYWORDS if k in url.lower()), reverse=True)[:max_depth]
        
        for contact_page_url in contact_pages:
            try:
                resp2, err2 = robust_get(contact_page_url, headers)
                if err2:
                    error_msgs.append(f'{contact_page_url}: {err2}')
                    continue
                
                contact_soup = BeautifulSoup(resp2.text, 'html.parser')
                
                # 提取邮箱
                try:
                    emails = extract_contacts_from_soup(contact_soup, base_url)
                    current_site_emails.update(emails)
                except Exception as e:
                    error_msgs.append(f'{contact_page_url} extraction error: {e}')
                    continue
                
                # 提取社交媒体链接
                sl2 = extract_social_links(contact_soup)
                for k, v in sl2.items():
                    social_links_main_dict.setdefault(k, set()).update(v)
            except Exception as e:
                error_msgs.append(f'Error processing {contact_page_url}: {str(e)}')
                continue
        # 4. 使用增强的 selenium 动态渲染策略
        if use_selenium:
            try:
                # 首先尝试主页
                html = get_rendered_html(base_url, wait_time=8)  # 增加等待时间
                soup = BeautifulSoup(html, 'html.parser')
                try:
                    emails_selenium = extract_contacts_from_soup(soup, base_url)
                    current_site_emails.update(emails_selenium)
                except Exception as e:
                    error_msgs.append(f'selenium main extraction error: {e}')
                
                # 如果主页没有找到足够的邮箱，尝试联系页面
                if len(current_site_emails) < 2 and contact_pages:
                    # 按关键词相关性排序联系页面
                    contact_pages.sort(key=lambda url: sum(1 for k in CONTACT_PAGE_KEYWORDS if k in url.lower()), reverse=True)
                    
                    # 尝试前两个最可能的联系页面
                    for contact_page in contact_pages[:2]:
                        try:
                            contact_html = get_rendered_html(contact_page, wait_time=8)
                            contact_soup = BeautifulSoup(contact_html, 'html.parser')
                            
                            # 提取联系页面的邮箱
                            try:
                                contact_emails = extract_contacts_from_soup(contact_soup, base_url)
                                current_site_emails.update(contact_emails)
                            except Exception as inner_e:
                                error_msgs.append(f'selenium extraction {contact_page}: {inner_e}')
                                continue
                            
                            # 如果找到了足够的邮箱，就停止搜索
                            if len(current_site_emails) >= 2:
                                break
                                
                        except Exception as e:
                            error_msgs.append(f'selenium contact page {contact_page}: {e}')
                            continue
            except Exception as e:
                error_msgs.append(f'selenium main page: {e}')
        
        # 5. 额外验证所有提取到的邮箱
        validated_emails = set()
        for email in current_site_emails:
            if is_valid_email(email):
                validated_emails.add(email)
        
        # 6. 去重整理
        emails_found = sorted(validated_emails)
        social_links_found = {k: sorted(v) for k, v in social_links_main_dict.items()}
        error = '\n'.join(error_msgs) if error_msgs else None
        
        # 7. 添加到结果
        contacts.append({
            'url': url_entry, # Use the original URL from the input DataFrame
            'emails': emails_found,
            'social_links': social_links_found,
            'error': error
        })
        
        # 8. 防止请求过快
        time.sleep(2)
    return pd.DataFrame(contacts)
