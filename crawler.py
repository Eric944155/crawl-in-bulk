import time
import requests
from bs4 import BeautifulSoup
from utils import extract_contacts_from_soup, extract_social_links, get_rendered_html
import pandas as pd

# 强化邮箱抓取，移除电话，结构极简

CONTACT_PAGE_KEYWORDS = [
    'contact', 'about', 'support', 'help', 'team', 'info', 'connect', 'privacy', 'impressum',
    'customer', 'service', '客服', '联系我们', '联系', '团队', '邮箱', '合作'
]
MAX_RETRIES = 2

def robust_get(url, headers, timeout=15):
    """
    自动切换 http/https，失败重试。
    """
    tried = set()
    for _ in range(MAX_RETRIES):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp, None
        except Exception as e:
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
            return None, str(e)
    return None, f'Failed after {MAX_RETRIES} retries'

def crawl_contacts(websites, use_selenium=True, max_depth=2):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'}
    contacts = []
    for url in websites['URL']:
        base_url = url if url.startswith('http') else 'http://' + url
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
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(k in href.lower() for k in CONTACT_PAGE_KEYWORDS):
                    full_url = requests.compat.urljoin(base_url, href)
                    contact_pages.add(full_url)
        contact_pages = list(contact_pages)[:max_depth]
        for contact_page_url in contact_pages:
            resp2, err2 = robust_get(contact_page_url, headers)
            if err2:
                error_msgs.append(f'{contact_page_url}: {err2}')
                continue
            contact_soup = BeautifulSoup(resp2.text, 'html.parser')
            emails = extract_contacts_from_soup(contact_soup, base_url)
            current_site_emails.update(emails)
            sl2 = extract_social_links(contact_soup)
            for k, v in sl2.items():
                social_links_main_dict.setdefault(k, set()).update(v)
        # 4. 若未找到邮箱，尝试 selenium 动态渲染
        if use_selenium and not current_site_emails:
            try:
                html = get_rendered_html(base_url)
                soup = BeautifulSoup(html, 'html.parser')
                emails_selenium = extract_contacts_from_soup(soup, base_url)
                current_site_emails.update(emails_selenium)
            except Exception as e:
                error_msgs.append(f'selenium: {e}')
        # 5. 去重整理
        emails_found = list(current_site_emails)
        social_links_found = {k: list(v) for k, v in social_links_main_dict.items()}
        error = '\n'.join(error_msgs) if error_msgs else None
        contacts.append({
            'url': url,
            'emails': emails_found,
            'social_links': social_links_found,
            'error': error
        })
        time.sleep(2)
    return pd.DataFrame(contacts)