import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
import time
import random # Corrected: Import the random module
from urllib.parse import urlparse, urljoin
from utils import extract_contacts_from_soup, extract_contact_pages, extract_social_links, clean_url

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
        site_error = None
        company_name = ''

        try:
            url = clean_url(url)
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            domain = parsed_url.netloc.replace('www.', '')

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

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

            emails_main, phones_main = extract_contacts_from_soup(soup, base_url)
            current_site_emails.extend(emails_main)
            current_site_phones.extend(phones_main)
            
            all_potential_contact_pages = extract_contact_pages(soup, base_url)
            current_site_contact_pages.extend(all_potential_contact_pages)
            
            social_links_main = extract_social_links(soup)
            current_site_social_links.extend(social_links_main)
            
            for contact_page_url in all_potential_contact_pages[:10]:
                try:
                    contact_response = requests.get(contact_page_url, headers=headers, timeout=10)
                    contact_response.raise_for_status()

                    contact_soup = BeautifulSoup(contact_response.text, 'html.parser')
                    
                    contact_emails, contact_phones = extract_contacts_from_soup(contact_soup, base_url)
                    current_site_emails.extend(contact_emails)
                    current_site_phones.extend(contact_phones)
                    
                    contact_social_links = extract_social_links(contact_soup)
                    current_site_social_links.extend(contact_social_links)
                    
                    time.sleep(1 + random.uniform(0.5, 1.5)) # Corrected: use random.uniform
                except requests.exceptions.RequestException as req_err_cp:
                    print(f"请求联系页面 {contact_page_url} 时出错: {req_err_cp}")
                except Exception as e_cp:
                    print(f"爬取联系页面 {contact_page_url} 时发生通用错误: {e_cp}")
            
            current_site_emails = list(set(current_site_emails))
            current_site_phones = list(set(current_site_phones))
            current_site_social_links = list(set(current_site_social_links))
            
        except requests.exceptions.SSLError as ssl_err:
            print(f"SSL 错误发生于 {url}: {ssl_err}。不进行 SSL 验证重试。")
            try:
                response = requests.get(url, headers=headers, timeout=10, verify=False)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                
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
                        time.sleep(1 + random.uniform(0.5, 1.5)) # Corrected: use random.uniform
                    except requests.exceptions.RequestException as req_err_cp:
                        print(f"请求联系页面 {contact_page_url} (SSL重试) 时出错: {req_err_cp}")
            except requests.exceptions.RequestException as req_err:
                site_error = f"主页请求失败 (SSL重试后): {req_err}"
                print(f"URL {url} 主页请求错误 (SSL重试后): {site_error}")

        except requests.exceptions.RequestException as req_err:
            site_error = f"主页请求失败: {req_err}"
            print(f"URL {url} 主页请求错误: {site_error}")
        except Exception as e:
            site_error = str(e)
            print(f'爬取 {url} 时发生通用错误: {site_error}')
        
        contacts.append({
            'url': url,
            'company_name': company_name,
            'emails': list(set(current_site_emails)),
            'phones': list(set(current_site_phones)),
            'contact_pages': list(set(current_site_contact_pages)),
            'social_links': list(set(current_site_social_links)),
            'error': site_error
        })
        
        time.sleep(2 + random.uniform(1, 2)) # Corrected: use random.uniform
    
    return pd.DataFrame(contacts)