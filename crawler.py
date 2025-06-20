import time
import requests
from bs4 import BeautifulSoup
from utils import extract_contacts_from_soup, extract_social_links, get_rendered_html
import pandas as pd
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # 禁用SSL警告

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

def robust_get(url, headers, timeout=15):
    """
    增强版网页请求函数：
    1. 自动切换 http/https
    2. 处理常见错误（SSL错误、连接超时等）
    3. 智能重试
    4. 处理重定向
    5. 新增：检查内容是否是JS重定向或WAF挑战页面
    """
    
    tried = set()
    for attempt in range(MAX_RETRIES):
        try:
            # 允许重定向，但不验证SSL证书（提高兼容性）
            resp = requests.get(
                url, 
                headers=headers, 
                timeout=timeout,
                allow_redirects=True,
                verify=False  # 不验证SSL证书
            )
            
            # 检查是否成功
            if resp.status_code < 400:
                # 新增：检查常见的JS重定向或WAF挑战模式
                if '<noscript data-cf-backend="dynamic_page_load">' in resp.text.lower() or 'just a moment' in resp.text.lower():
                    return None, "WAF/CDN challenge detected, requires dynamic rendering."
                return resp, None
            else:
                resp.raise_for_status()  # 触发异常以便捕获
                
        except requests.exceptions.SSLError:
            # SSL错误，尝试不验证SSL证书
            try:
                resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
                if resp.status_code < 400:
                    # 新增：检查WAF/CDN挑战
                    if '<noscript data-cf-backend="dynamic_page_load">' in resp.text.lower() or 'just a moment' in resp.text.lower():
                        return None, "WAF/CDN challenge detected, requires dynamic rendering."
                    return resp, None
            except Exception as inner_e:
                pass  # 继续尝试其他方法
                
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, 
                requests.exceptions.TooManyRedirects, requests.exceptions.HTTPError) as e:
            tried.add(url)
            
            # 尝试切换 http/https
            if url.startswith('http://'):
                alt_url = url.replace('http://', 'https://', 1)
            elif url.startswith('https://'):
                alt_url = url.replace('https://', 'http://', 1)
            else:
                alt_url = 'https://' + url
                
            if alt_url not in tried:
                url = alt_url
                continue
                
            # 最后一次尝试，增加www前缀
            if attempt == MAX_RETRIES - 1 and 'www.' not in url.lower():
                if url.startswith('http://'):
                    www_url = url.replace('http://', 'http://www.', 1)
                elif url.startswith('https://'):
                    www_url = url.replace('https://', 'https://www.', 1)
                else:
                    www_url = 'http://www.' + url
                    
                if www_url not in tried:
                    try:
                        resp = requests.get(www_url, headers=headers, timeout=timeout, verify=False)
                        if resp.status_code < 400:
                            # 新增：检查WAF/CDN挑战
                            if '<noscript data-cf-backend="dynamic_page_load">' in resp.text.lower() or 'just a moment' in resp.text.lower():
                                return None, "WAF/CDN challenge detected, requires dynamic rendering."
                            return resp, None
                    except Exception:
                        pass  # 忽略错误，继续尝试
            
            if attempt == MAX_RETRIES - 1:  # 最后一次尝试失败
                return None, f"Connection error: {str(e)}"
                
        except Exception as e:
            if attempt == MAX_RETRIES - 1:  # 最后一次尝试失败
                return None, f"Error: {str(e)}"
    
    return None, f'Failed after {MAX_RETRIES} retries'

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
    for url in websites['URL']:
        base_url = url if url.startswith('http') else 'http://' + url
        current_site_emails = set()
        social_links_main_dict = {}
        error_msgs = []
        soup = None # Initialize soup for requests
        soup_selenium = None # Initialize soup for selenium

        # 1. 主页面请求 (Requests)
        resp, err = robust_get(base_url, headers)
        if err and "WAF/CDN challenge detected" not in err: # If not a WAF/CDN error, record it as a general error
            error_msgs.append(f'Requests main page error for {base_url}: {err}')
        elif resp:
            soup = BeautifulSoup(resp.text, 'html.parser')
            current_site_emails.update(extract_contacts_from_soup(soup, base_url))
            sl = extract_social_links(soup)
            for k, v in sl.items():
                social_links_main_dict.setdefault(k, set()).update(v)

        # 2. 如果通过 requests 没有找到足够的邮箱，或者遇到WAF/CDN挑战，则尝试 Selenium
        # 阈值可以根据实际情况调整，例如：len(current_site_emails) == 0
        should_use_selenium_for_main = use_selenium and (not current_site_emails or ("WAF/CDN challenge detected" in str(err)))
        
        if should_use_selenium_for_main:
            try:
                # 尝试主页的动态渲染
                # 增加wait_time，确保JS充分加载
                html_selenium = get_rendered_html(base_url, wait_time=10) # 适当增加等待时间
                soup_selenium = BeautifulSoup(html_selenium, 'html.parser')
                emails_selenium = extract_contacts_from_soup(soup_selenium, base_url)
                current_site_emails.update(emails_selenium)
                
                # 合并社交媒体链接（如果Selenium获取到了）
                sl_selenium = extract_social_links(soup_selenium)
                for k, v in sl_selenium.items():
                    social_links_main_dict.setdefault(k, set()).update(v)

            except Exception as e:
                error_msgs.append(f'Selenium main page error for {base_url}: {e}')

        # 3. 递归所有潜在联系页
        # 优化联系页面发现逻辑：优先从Selenium生成的soup中提取链接，如果没有，则从requests生成的soup中提取
        effective_soup_for_links = soup_selenium if should_use_selenium_for_main and soup_selenium else soup

        contact_pages = set()
        if effective_soup_for_links:
            # 1. 检查链接文本和href属性
            for a in effective_soup_for_links.find_all('a', href=True):
                href = a['href']
                text = a.get_text().lower().strip()
                
                # 排除无效链接
                if not href or href == '#' or href.startswith('javascript:') or href.startswith('mailto:') or href.startswith('tel:'):
                    continue
                
                # 将相对路径转换为绝对路径
                full_url = requests.compat.urljoin(base_url, href)

                # 检查链接文本和href属性
                if any(k in href.lower() for k in CONTACT_PAGE_KEYWORDS) or any(k in text for k in CONTACT_PAGE_KEYWORDS):
                    contact_pages.add(full_url)
            
            # 2. 查找页脚中的联系链接（通常包含联系信息）
            footer_tags = effective_soup_for_links.find_all(['footer', 'div', 'section'], class_=lambda c: c and any(x in str(c).lower() for x in ['footer', 'bottom']))
            for footer in footer_tags:
                for a in footer.find_all('a', href=True):
                    href = a['href']
                    if not href or href == '#' or href.startswith('javascript:'):
                        continue
                    full_url = requests.compat.urljoin(base_url, href)
                    contact_pages.add(full_url)
        
        # 限制爬取页面数量，优先处理最可能包含联系信息的页面
        contact_pages = sorted(list(contact_pages), key=lambda url: sum(1 for k in CONTACT_PAGE_KEYWORDS if k in url.lower()), reverse=True)[:max_depth]
        
        # 遍历联系页面
        for contact_page_url in contact_pages:
            page_emails = set()
            page_social_links = {}
            
            # 优先尝试 requests
            resp2, err2 = robust_get(contact_page_url, headers)
            if err2 and "WAF/CDN challenge detected" not in err2:
                error_msgs.append(f'Requests contact page error for {contact_page_url}: {err2}')
                contact_soup = None
            elif resp2:
                contact_soup = BeautifulSoup(resp2.text, 'html.parser')
                page_emails.update(extract_contacts_from_soup(contact_soup, base_url))
                sl2 = extract_social_links(contact_soup)
                for k, v in sl2.items():
                    page_social_links.setdefault(k, set()).update(v)

            # 如果 requests 没有找到邮箱，或者遇到WAF/CDN挑战，则尝试 Selenium
            should_use_selenium_for_contact = use_selenium and (not page_emails or ("WAF/CDN challenge detected" in str(err2)))
            
            if should_use_selenium_for_contact:
                try:
                    contact_html_selenium = get_rendered_html(contact_page_url, wait_time=10) # 适当增加等待时间
                    contact_soup_selenium = BeautifulSoup(contact_html_selenium, 'html.parser')
                    page_emails.update(extract_contacts_from_soup(contact_soup_selenium, base_url))
                    
                    sl2_selenium = extract_social_links(contact_soup_selenium)
                    for k, v in sl2_selenium.items():
                        page_social_links.setdefault(k, set()).update(v)

                except Exception as e:
                    error_msgs.append(f'Selenium contact page error for {contact_page_url}: {e}')
                    
            current_site_emails.update(page_emails)
            for k, v in page_social_links.items():
                social_links_main_dict.setdefault(k, set()).update(v)

        # 4. 额外验证所有提取到的邮箱
        from utils import is_valid_email
        validated_emails = set()
        for email in current_site_emails:
            if is_valid_email(email):
                validated_emails.add(email)
        
        # 5. 去重整理
        emails_found = list(validated_emails)
        social_links_found = {k: list(v) for k, v in social_links_main_dict.items()}
        error = '\n'.join(error_msgs) if error_msgs else None
        
        # 6. 添加到结果
        contacts.append({
            'url': url,
            'emails': emails_found,
            'social_links': social_links_found,
            'error': error
        })
        
        # 7. 防止请求过快
        time.sleep(2) # 适当增加延迟，特别是在使用Selenium时，因为Selenium本身有加载时间
    return pd.DataFrame(contacts)