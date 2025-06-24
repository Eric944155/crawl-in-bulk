import time
import requests
from bs4 import BeautifulSoup
from utils import extract_contacts_from_soup, extract_social_links, get_rendered_html, is_valid_email
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
                return resp, None
            else:
                resp.raise_for_status()  # 触发异常以便捕获
                
        except requests.exceptions.SSLError:
            # SSL错误，尝试不验证SSL证书
            try:
                resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
                if resp.status_code < 400:
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
    for url_entry in websites['URL']: # Iterate through the URL column
        base_url = url_entry if url_entry.startswith('http') else 'http://' + url_entry
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
            current_site_emails.update(extract_contacts_from_soup(soup, base_url))
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
                emails = extract_contacts_from_soup(contact_soup, base_url)
                current_site_emails.update(emails)
                
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
                emails_selenium = extract_contacts_from_soup(soup, base_url)
                current_site_emails.update(emails_selenium)
                
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
                            contact_emails = extract_contacts_from_soup(contact_soup, base_url)
                            current_site_emails.update(contact_emails)
                            
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
        emails_found = list(validated_emails)
        social_links_found = {k: list(v) for k, v in social_links_main_dict.items()}
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