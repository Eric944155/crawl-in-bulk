import time
import requests
from bs4 import BeautifulSoup
from utils import extract_contacts_from_soup, extract_contact_pages, extract_social_links, get_rendered_html
import pandas as pd

# 强化邮箱抓取，移除电话，结构极简

def crawl_contacts(websites, use_selenium=True, max_depth=2):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Connection': 'keep-alive'
    }
    contacts = []
    for url in websites['URL']:
        current_site_emails = []
        current_site_social_links_dict = {}
        site_error = None
        try:
            parsed_url = requests.utils.urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            # 1. 主页面抓取
            try:
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()
            except requests.exceptions.SSLError as ssl_err:
                response = requests.get(url, headers=headers, timeout=15, verify=False)
                response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            emails_main = extract_contacts_from_soup(soup, base_url)
            current_site_emails.extend(emails_main)
            # 社交媒体
            social_links_main_dict = extract_social_links(soup)
            for platform, links in social_links_main_dict.items():
                current_site_social_links_dict.setdefault(platform, []).extend(links)
            # 2. 联系页面递归抓取
            all_potential_contact_pages = extract_contact_pages(soup, base_url)
            for contact_page_url in all_potential_contact_pages[:max_depth]:
                if not contact_page_url.startswith(('http://', 'https://')):
                    contact_page_url = requests.compat.urljoin(base_url, contact_page_url)
                try:
                    contact_response = requests.get(contact_page_url, headers=headers, timeout=10)
                    contact_response.raise_for_status()
                    contact_soup = BeautifulSoup(contact_response.text, 'html.parser')
                    contact_emails = extract_contacts_from_soup(contact_soup, base_url)
                    current_site_emails.extend(contact_emails)
                    contact_social_links_dict = extract_social_links(contact_soup)
                    for platform, links in contact_social_links_dict.items():
                        current_site_social_links_dict.setdefault(platform, []).extend(links)
                    time.sleep(0.5)
                except Exception:
                    continue
            # 3. selenium 动态渲染补充
            if use_selenium and not current_site_emails:
                try:
                    html = get_rendered_html(url)
                    soup = BeautifulSoup(html, 'html.parser')
                    emails_selenium = extract_contacts_from_soup(soup, base_url)
                    current_site_emails.extend(emails_selenium)
                except Exception as e:
                    site_error = f'动态抓取失败: {e}'
            # 去重
            current_site_emails = list(set(current_site_emails))
            for platform in current_site_social_links_dict:
                current_site_social_links_dict[platform] = list(set(current_site_social_links_dict[platform]))
        except Exception as e:
            site_error = str(e)
        contacts.append({
            'url': url,
            'emails': current_site_emails,
            'social_links': current_site_social_links_dict,
            'error': site_error if not current_site_emails else None
        })
        time.sleep(2)
    return pd.DataFrame(contacts)