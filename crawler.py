import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
import time
from urllib.parse import urlparse
from utils import extract_contacts_from_text, extract_contact_pages, extract_social_links

# 爬取联系方式的函数
def crawl_contacts(websites):
    contacts = []
    for url in websites['URL']:
        try:
            # 获取基础URL（域名部分）
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # 请求网页
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            # *** 关键修改 1: 添加 verify=False ***
            response = requests.get(url, headers=headers, timeout=10, verify=False) # 
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取邮箱和电话
            emails, phones = extract_contacts_from_text(soup.text)
            
            # 提取联系页面链接
            contact_pages = extract_contact_pages(soup, base_url)
            
            # 提取社交媒体链接
            social_links = extract_social_links(soup)
            
            # 递归爬取联系页面
            if contact_pages:
                for contact_page in contact_pages[:1]:  # 只爬取第一个联系页面
                    try:
                        # *** 关键修改 2: 添加 verify=False ***
                        contact_response = requests.get(contact_page, headers=headers, timeout=10, verify=False) # 
                        contact_soup = BeautifulSoup(contact_response.text, 'html.parser')
                        
                        # 提取联系页面中的邮箱和电话
                        contact_emails, contact_phones = extract_contacts_from_text(contact_soup.text)
                        emails.extend(contact_emails)
                        phones.extend(contact_phones)
                        
                        # 提取联系页面中的社交媒体链接
                        contact_social_links = extract_social_links(contact_soup)
                        social_links.extend(contact_social_links)
                        
                        # 避免请求过快
                        time.sleep(1)
                    except Exception as e:
                        print(f"Error crawling contact page {contact_page}: {e}")
            
            # 去重
            emails = list(set(emails))
            phones = list(set(phones))
            social_links = list(set(social_links))
            
            contacts.append({
                'url': url,
                'emails': emails,
                'phones': phones,
                'contact_pages': contact_pages,
                'social_links': social_links
            })
            
            # 避免请求过快
            time.sleep(2)
            
        except Exception as e:
            print(f'Error crawling {url}: {e}')
            contacts.append({
                'url': url,
                'emails': [],
                'phones': [],
                'contact_pages': [],
                'social_links': [],
                'error': str(e)
            })
    
    return pd.DataFrame(contacts)