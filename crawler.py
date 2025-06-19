import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
import time
from urllib.parse import urlparse, urljoin # 导入 urljoin
from utils import extract_contacts_from_soup, extract_contact_pages, extract_social_links, clean_url # 更新导入

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
        company_name = '' # 初始化公司名称

        try:
            # 清理和规范化 URL
            url = clean_url(url)
            # 获取基础URL（域名部分）
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            domain = parsed_url.netloc.replace('www.', '') # 获取不带www的域名

            # 尝试获取公司名称 (从<title>或<h1>)
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status() # 检查HTTP响应状态码，如果不是200会抛出异常
            soup = BeautifulSoup(response.text, 'html.parser')

            if soup.title and soup.title.string:
                company_name = soup.title.string.split('|')[0].split('-')[0].strip()
                # 简单清洗公司名，移除域名部分或通用词
                if company_name.lower().startswith(domain.lower()):
                    company_name = company_name[len(domain):].strip()
                if 'official website' in company_name.lower():
                    company_name = company_name.lower().replace('official website', '').strip()
                if not company_name: # 如果清洗后为空，尝试从url重新提取
                     company_name = domain.split('.')[0]
            elif soup.h1 and soup.h1.string:
                company_name = soup.h1.string.strip()
            else:
                company_name = domain.split('.')[0] # 默认使用域名作为公司名

            # 从主页的HTML内容中提取邮箱和电话
            emails_main, phones_main = extract_contacts_from_soup(soup, base_url) # 使用新的函数
            current_site_emails.extend(emails_main)
            current_site_phones.extend(phones_main)
            
            # 提取联系页面链接（包含联系我们、关于我们、FAQ等）
            all_potential_contact_pages = extract_contact_pages(soup, base_url)
            current_site_contact_pages.extend(all_potential_contact_pages) # 记录所有找到的潜在联系页面
            
            # 提取社交媒体链接
            social_links_main = extract_social_links(soup)
            current_site_social_links.extend(social_links_main)
            
            # 递归爬取找到的潜在联系页面（最多爬取前5个，可以根据需求调整）
            # 增加爬取深度至最多10个，并增加随机延迟
            for contact_page_url in all_potential_contact_pages[:10]:
                try:
                    contact_response = requests.get(contact_page_url, headers=headers, timeout=10)
                    contact_response.raise_for_status()

                    contact_soup = BeautifulSoup(contact_response.text, 'html.parser')
                    
                    # 提取联系页面中的邮箱和电话
                    contact_emails, contact_phones = extract_contacts_from_soup(contact_soup, base_url) # 使用新的函数
                    current_site_emails.extend(contact_emails)
                    current_site_phones.extend(contact_phones)
                    
                    # 提取联系页面中的社交媒体链接
                    contact_social_links = extract_social_links(contact_soup)
                    current_site_social_links.extend(contact_social_links)
                    
                    # 短暂延迟，避免请求过快
                    time.sleep(1 + time.random.uniform(0.5, 1.5)) # 增加随机延迟
                except requests.exceptions.RequestException as req_err_cp:
                    print(f"请求联系页面 {contact_page_url} 时出错: {req_err_cp}")
                except Exception as e_cp:
                    print(f"爬取联系页面 {contact_page_url} 时发生通用错误: {e_cp}")
            
            # 对所有收集到的联系方式进行去重
            current_site_emails = list(set(current_site_emails))
            current_site_phones = list(set(current_site_phones))
            current_site_social_links = list(set(current_site_social_links))
            
        except requests.exceptions.SSLError as ssl_err:
            # 如果遇到SSL错误，则不进行SSL验证再次尝试（并打印警告）
            print(f"SSL 错误发生于 {url}: {ssl_err}。不进行 SSL 验证重试。")
            try:
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                response.raise_for_status() # 再次检查响应状态
                soup = BeautifulSoup(response.text, 'html.parser') # 重新解析 soup
                
                # 从主页的HTML内容中提取邮箱和电话 (针对SSL错误后的重试)
                emails_main, phones_main = extract_contacts_from_soup(soup, base_url)
                current_site_emails.extend(emails_main)
                current_site_phones.extend(phones_main)
                all_potential_contact_pages = extract_contact_pages(soup, base_url)
                current_site_contact_pages.extend(all_potential_contact_pages)
                social_links_main = extract_social_links(soup)
                current_site_social_links.extend(social_links_main)

                if soup.title and soup.title.string:
                    company_name = soup.title.string.split('|')[0].split('-')[0].strip()
                    if company_name.lower().startswith(domain.lower()):
                        company_name = company_name[len(domain):].strip()
                    if 'official website' in company_name.lower():
                        company_name = company_name.lower().replace('official website', '').strip()
                    if not company_name:
                         company_name = domain.split('.')[0]
                elif soup.h1 and soup.h1.string:
                    company_name = soup.h1.string.strip()
                else:
                    company_name = domain.split('.')[0]

                # 爬取联系页面 (SSL重试后)
                for contact_page_url in all_potential_contact_pages[:10]:
                    try:
                        contact_response = requests.get(contact_page_url, headers=headers, timeout=10, verify=False)
                        contact_response.raise_for_status()
                        contact_soup = BeautifulSoup(contact_response.text, 'html.parser')
                        contact_emails, contact_phones = extract_contacts_from_soup(contact_soup, base_url)
                        current_site_emails.extend(contact_emails)
                        current_site_phones.extend(contact_phones)
                        contact_social_links = extract_social_links(contact_soup)
                        current_site_social_links.extend(contact_social_links)
                        time.sleep(1 + time.random.uniform(0.5, 1.5))
                    except requests.exceptions.RequestException as req_err_cp:
                        print(f"请求联系页面 {contact_page_url} (SSL重试) 时出错: {req_err_cp}")
            except requests.exceptions.RequestException as req_err:
                site_error = f"主页请求失败 (SSL重试后): {req_err}"
                print(f"URL {url} 主页请求错误 (SSL重试后): {site_error}")

        except requests.exceptions.RequestException as req_err:
            site_error = f"主页请求失败: {req_err}"
            print(f"URL {url} 主页请求错误: {site_error}")
        except Exception as e:
            # 捕获其他所有通用错误
            site_error = str(e)
            print(f'爬取 {url} 时发生通用错误: {site_error}')
        
        contacts.append({
            'url': url,
            'company_name': company_name, # 添加公司名称
            'emails': list(set(current_site_emails)), # 去重后确保是列表
            'phones': list(set(current_site_phones)), # 去重后确保是列表
            'contact_pages': list(set(current_site_contact_pages)), # 确保联系页面列表也去重
            'social_links': list(set(current_site_social_links)), # 去重后确保是列表
            'error': site_error # 记录主URL的错误信息
        })
        
        # 避免请求过快
        time.sleep(2 + time.random.uniform(1, 2)) # 增加随机延迟
    
    return pd.DataFrame(contacts)