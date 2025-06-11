import streamlit as st
import pandas as pd
import time
import os
from crawler import crawl_contacts
from mailer import send_bulk_email, configure_smtp, DEFAULT_EMAIL_TEMPLATE
from utils import process_website_file

# 设置页面配置
st.set_page_config(
    page_title="批量联系方式爬取与群发工具",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 应用标题
st.title('📧 批量联系方式爬取与群发工具')
st.markdown('---')

# 初始化会话状态
if 'contacts' not in st.session_state:
    st.session_state.contacts = None
if 'websites' not in st.session_state:
    st.session_state.websites = None
if 'crawling' not in st.session_state:
    st.session_state.crawling = False
if 'sending' not in st.session_state:
    st.session_state.sending = False

# 创建侧边栏
with st.sidebar:
    st.header('⚙️ 配置')
    
    # SMTP配置
    st.subheader('SMTP服务器设置')
    smtp_server = st.text_input('SMTP服务器', 'smtp.gmail.com')
    smtp_port = st.number_input('SMTP端口', value=587, min_value=1, max_value=65535)
    smtp_email = st.text_input('发件人邮箱')
    smtp_password = st.text_input('邮箱密码', type='password')
    use_tls = st.checkbox('使用TLS', value=True)
    
    # 邮件发送设置
    st.subheader('邮件发送设置')
    daily_limit = st.slider('每日发送上限', min_value=1, max_value=200, value=50)
    interval_seconds = st.slider('发送间隔(秒)', min_value=10, max_value=300, value=60)

# 创建主要内容区域的选项卡
tab1, tab2, tab3 = st.tabs(["1️⃣ 上传网站列表", "2️⃣ 爬取联系方式", "3️⃣ 邮件群发"])

# Tab 1: 上传网站列表
with tab1:
    st.header('上传网站列表')
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('### 从文件导入')
        uploaded_file = st.file_uploader('上传网站列表文件', type=['txt', 'csv'])
        
        if uploaded_file is not None:
            try:
                # 处理上传的文件
                websites_df = process_website_file(uploaded_file)
                st.session_state.websites = websites_df
                st.success(f'成功导入 {len(websites_df)} 个有效网址')
            except Exception as e:
                st.error(f'文件处理错误: {e}')
    
    with col2:
        st.markdown('### 手动输入')
        manual_urls = st.text_area('每行输入一个网址')
        
        if st.button('添加网址'):
            if manual_urls:
                urls = [url.strip() for url in manual_urls.split('\n') if url.strip()]
                if urls:
                    # 创建临时文件
                    temp_file_path = 'temp_urls.txt'
                    with open(temp_file_path, 'w') as f:
                        for url in urls:
                            f.write(f"{url}\n")
                    
                    # 处理临时文件
                    with open(temp_file_path, 'r') as f:
                        try:
                            from io import StringIO
                            file_content = StringIO(f.read())
                            file_content.name = 'manual_input.txt'
                            websites_df = process_website_file(file_content)
                            st.session_state.websites = websites_df
                            st.success(f'成功添加 {len(websites_df)} 个有效网址')
                        except Exception as e:
                            st.error(f'处理错误: {e}')
                    
                    # 删除临时文件
                    if os.path.exists(temp_file_path):
                        os.remove(temp_file_path)
                else:
                    st.warning('请输入至少一个有效网址')
    
    # 显示导入的网址列表
    if st.session_state.websites is not None:
        st.markdown('### 网址列表预览')
        st.dataframe(st.session_state.websites)

# Tab 2: 爬取联系方式
with tab2:
    st.header('爬取联系方式')
    
    if st.session_state.websites is None:
        st.warning('请先在第一步上传网站列表')
    else:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if not st.session_state.crawling:
                if st.button('开始爬取联系方式', key='start_crawl'):
                    st.session_state.crawling = True
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # 开始爬取
                    websites = st.session_state.websites
                    total_sites = len(websites)
                    
                    contacts = []
                    for i, (_, row) in enumerate(websites.iterrows()):
                        # 创建单行DataFrame
                        single_site = pd.DataFrame([row])
                        status_text.text(f'正在爬取 {i+1}/{total_sites}: {row["URL"]}')
                        
                        # 爬取单个网站
                        site_contacts = crawl_contacts(single_site)
                        contacts.append(site_contacts)
                        
                        # 更新进度条
                        progress_bar.progress((i + 1) / total_sites)
                        
                    # 合并结果
                    if contacts:
                        all_contacts = pd.concat(contacts, ignore_index=True)
                        st.session_state.contacts = all_contacts
                        status_text.text('爬取完成！')
                    else:
                        status_text.text('爬取完成，但未找到联系方式')
                    
                    st.session_state.crawling = False
        
        with col2:
            st.markdown('### 爬取设置')
            st.markdown('爬取内容包括：')
            st.markdown('- ✉️ 邮箱地址')
            st.markdown('- 📞 电话号码')
            st.markdown('- 🔗 联系页面')
            st.markdown('- 📱 社交媒体链接')
        
        # 显示爬取结果
        if st.session_state.contacts is not None:
            st.markdown('### 爬取结果')
            st.dataframe(st.session_state.contacts)
            
            # 导出功能
            if st.button('导出数据', key='export_data'):
                st.session_state.contacts.to_csv('contacts.csv', index=False)
                st.success('数据已导出到 contacts.csv')

# Tab 3: 邮件群发
with tab3:
    st.header('邮件群发')
    
    if st.session_state.contacts is None:
        st.warning('请先在第二步爬取联系方式')
    else:
        # 检查是否有邮箱地址
        has_emails = False
        for _, row in st.session_state.contacts.iterrows():
            if row['emails'] and len(row['emails']) > 0:
                has_emails = True
                break
        
        if not has_emails:
            st.warning('未找到任何邮箱地址，无法发送邮件')
        else:
            # 邮件模板设置
            st.subheader('邮件模板设置')
            email_template = st.text_area('邮件内容模板', DEFAULT_EMAIL_TEMPLATE, height=300)
            
            # SMTP配置检查
            if not smtp_email or not smtp_password:
                st.warning('请在侧边栏配置SMTP服务器信息')
            else:
                # 配置SMTP
                smtp_config = configure_smtp(
                    server=smtp_server,
                    port=smtp_port,
                    email=smtp_email,
                    password=smtp_password,
                    use_tls=use_tls
                )
                
                # 发送邮件按钮
                if not st.session_state.sending:
                    if st.button('开始群发邮件', key='start_send'):
                        st.session_state.sending = True
                        
                        # 开始发送邮件
                        with st.spinner('正在发送邮件...'):
                            send_log = send_bulk_email(
                                contacts=st.session_state.contacts,
                                smtp_config=smtp_config,
                                email_template=email_template,
                                daily_limit=daily_limit,
                                interval_seconds=interval_seconds
                            )
                        
                        # 显示发送结果
                        st.success('邮件发送完成！')
                        st.dataframe(send_log)
                        
                        st.session_state.sending = False

# 页脚
st.markdown('---')
st.markdown('📧 批量联系方式爬取与群发工具 | 版本 1.0.0')