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
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    for url in websites['URL']:
        current_site_emails = []
        current_site_phones = []
        current_site_contact_pages = []
        current_site_social_links = []
        site_error = None # 初始化错误信息为 None

        try:
            # 获取基础URL（域名部分）
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # 请求网页，首先尝试进行SSL验证
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status() # 检查HTTP响应状态码，如果不是200会抛出异常
            except requests.exceptions.SSLError as ssl_err:
                # 如果遇到SSL错误，则不进行SSL验证再次尝试（并打印警告）
                print(f"SSL 错误发生于 {url}: {ssl_err}。不进行 SSL 验证重试。")
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                response.raise_for_status() # 再次检查响应状态
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取邮箱和电话
            emails_main, phones_main = extract_contacts_from_text(soup.text)
            current_site_emails.extend(emails_main)
            current_site_phones.extend(phones_main)
            
            # 提取联系页面链接
            contact_pages = extract_contact_pages(soup, base_url)
            current_site_contact_pages.extend(contact_pages)
            
            # 提取社交媒体链接
            social_links_main = extract_social_links(soup)
            current_site_social_links.extend(social_links_main)
            
            # 递归爬取联系页面（最多爬取前3个联系页面，以增加找到信息的几率）
            for contact_page in contact_pages[:3]:
                try:
                    # 尝试进行SSL验证
                    try:
                        contact_response = requests.get(contact_page, headers=headers, timeout=10)
                        contact_response.raise_for_status()
                    except requests.exceptions.SSLError as ssl_err_cp:
                        print(f"联系页面 {contact_page} 发生 SSL 错误: {ssl_err_cp}。不进行 SSL 验证重试。")
                        contact_response = requests.get(contact_page, headers=headers, timeout=10, verify=False)
                        contact_response.raise_for_status()

                    contact_soup = BeautifulSoup(contact_response.text, 'html.parser')
                    
                    # 提取联系页面中的邮箱和电话
                    contact_emails, contact_phones = extract_contacts_from_text(contact_soup.text)
                    current_site_emails.extend(contact_emails)
                    current_site_phones.extend(contact_phones)
                    
                    # 提取联系页面中的社交媒体链接
                    contact_social_links = extract_social_links(contact_soup)
                    current_site_social_links.extend(contact_social_links)
                    
                    # 短暂延迟，避免请求过快
                    time.sleep(0.5)
                except requests.exceptions.RequestException as req_err_cp:
                    print(f"请求联系页面 {contact_page} 时出错: {req_err_cp}")
                    # 可以考虑将此错误记录到 site_error 中，或者专门的 contact_page_errors 字段
                except Exception as e_cp:
                    print(f"爬取联系页面 {contact_page} 时发生通用错误: {e_cp}")
            
            # 对所有收集到的联系方式进行去重
            current_site_emails = list(set(current_site_emails))
            current_site_phones = list(set(current_site_phones))
            current_site_social_links = list(set(current_site_social_links))
            
        except requests.exceptions.RequestException as req_err:
            # 捕获所有请求相关的错误 (例如 HTTP 错误、连接错误、超时)
            site_error = f"请求失败: {req_err}"
            print(f"URL {url} 请求错误: {site_error}")
        except Exception as e:
            # 捕获其他所有通用错误
            site_error = str(e)
            print(f'爬取 {url} 时发生通用错误: {site_error}')
        
        contacts.append({
            'url': url,
            'emails': current_site_emails,
            'phones': current_site_phones,
            'contact_pages': current_site_contact_pages,
            'social_links': current_site_social_links,
            'error': site_error # 记录主URL的错误信息
        })
        
        # 避免请求过快
        time.sleep(2)
    
    return pd.DataFrame(contacts)