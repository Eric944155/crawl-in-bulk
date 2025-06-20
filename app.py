import streamlit as st
import pandas as pd
import time
import os
import base64
from datetime import datetime
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

# 自定义CSS样式
def local_css():
    st.markdown("""
    <style>
        /* 主题颜色和字体 */
        :root {
            --primary-color: #4F6DF5;
            --secondary-color: #05C3DE;
            --accent-color: #F25D50;
            --background-color: #F9FAFB;
            --text-color: #333;
            --light-gray: #EEF1F5;
        }
        
        /* 全局样式 */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-weight: 600;
            color: #1E293B;
        }
        
        /* 标题样式 */
        .main-title {
            font-size: 2.5rem !important;
            background: linear-gradient(90deg, var(--primary-color), var(--secondary-color));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem !important;
            padding-bottom: 0.5rem;
        }
        
        /* 卡片样式 */
        .stTabs [data-baseweb="tab-panel"] {
            background-color: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        }
        
        .stTabs [data-baseweb="tab"] {
            font-weight: 600;
            font-size: 1rem;
        }
        
        .stTabs [aria-selected="true"] {
            background-color: var(--primary-color) !important;
            color: white !important;
            border-radius: 5px;
        }
        
        /* 按钮样式 */
        .stButton>button {
            background-color: var(--primary-color);
            color: white;
            border-radius: 5px;
            border: none;
            padding: 0.5rem 1rem;
            font-weight: 600;
            transition: all 0.3s;
        }
        
        .stButton>button:hover {
            background-color: #3A56D4;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
            transform: translateY(-2px);
        }
        
        /* 数据框样式 */
        .dataframe-container {
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        }
        
        /* 侧边栏样式 */
        .css-1d391kg, .css-12oz5g7 {
            background-color: #F9FAFB;
        }
        
        /* 进度条样式 */
        .stProgress > div > div > div > div {
            background-color: var(--primary-color);
        }
        
        /* 成功消息样式 */
        .element-container div[data-testid="stImage"] {
            text-align: center;
        }
        
        /* 页脚样式 */
        .footer {
            text-align: center;
            color: #64748B;
            font-size: 0.8rem;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid #E2E8F0;
        }
        
        /* 统计卡片 */
        .metric-card {
            background-color: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);\
            text-align: center;
            height: 100%;
        }
        
        .metric-value {
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--primary-color);
            margin: 0.5rem 0;
        }
        
        .metric-label {
            font-size: 1rem;
            color: #64748B;
            margin-bottom: 0;
        }
        
        /* 表单输入样式 */
        .stTextInput>div>div>input, .stTextArea>div>div>textarea {
            border-radius: 5px;
            border: 1px solid #E2E8F0;
        }
    </style>
    """, unsafe_allow_html=True)

local_css()

# 应用标题
st.markdown('<h1 class="main-title">批量联系方式爬取与群发工具</h1>', unsafe_allow_html=True)
st.markdown('<p style="font-size: 1.2rem; color: #64748B;">高效获取网站联系信息并进行邮件营销</p>', unsafe_allow_html=True)

# 初始化会话状态
if 'contacts' not in st.session_state:
    st.session_state.contacts = None
if 'websites' not in st.session_state:
    st.session_state.websites = None
if 'crawling' not in st.session_state:
    st.session_state.crawling = False
if 'sending' not in st.session_state:
    st.session_state.sending = False
if 'smtp_configured' not in st.session_state:
    st.session_state.smtp_configured = False
if 'current_date' not in st.session_state:
    st.session_state.current_date = datetime.now().strftime("%Y-%m-%d")
if 'selected_social_platforms' not in st.session_state: # 新增：用于存储选中的社交媒体平台
    st.session_state.selected_social_platforms = []

# 创建侧边栏
with st.sidebar:
    st.markdown('<h2 style="color: #1E293B; font-weight: 600; margin-bottom: 1.5rem;">⚙️ 系统配置</h2>', unsafe_allow_html=True)
    
    # SMTP配置卡片
    st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); margin-bottom: 2rem;">', unsafe_allow_html=True)
    st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">📧 SMTP 配置</h3>', unsafe_allow_html=True)
    
    smtp_server = st.text_input('SMTP 服务器', 'smtp.gmail.com', help="例如: smtp.gmail.com, smtp.qq.com")
    smtp_port = st.number_input('SMTP 端口', value=587, min_value=1, max_value=65535, help="常用端口: 25, 465 (SSL), 587 (TLS)")
    smtp_email = st.text_input('发件人邮箱', help="通常是您的邮箱地址")
    smtp_password = st.text_input('邮箱密码', type='password', help="对于一些邮箱服务，这可能是应用专用密码或授权码")
    use_tls = st.checkbox('使用TLS (推荐)', value=True, help="大多数现代邮件服务器使用TLS加密连接 (端口587)。部分旧服务可能使用SSL (端口465)。")
    
    smtp_test_col1, smtp_test_col2 = st.columns([3, 1])
    with smtp_test_col1:
        smtp_test_button = st.button('测试SMTP配置', use_container_width=True)
    with smtp_test_col2:
        if st.session_state.smtp_configured:
            st.markdown('<div style="background-color: #DCFCE7; color: #166534; padding: 0.5rem; border-radius: 5px; text-align: center; margin-top: 0.2rem;">✓ 已配置</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="background-color: #FEF2F2; color: #991B1B; padding: 0.5rem; border-radius: 5px; text-align: center; margin-top: 0.2rem;">✗ 未配置</div>', unsafe_allow_html=True)
    
    if smtp_test_button:
        try:
            with st.spinner('正在测试SMTP连接...'):
                # 尝试配置SMTP
                configure_smtp(
                    server=smtp_server,
                    port=smtp_port,
                    email=smtp_email,
                    password=smtp_password,
                    use_tls=use_tls
                )
            st.success('SMTP 配置成功!')
            st.session_state.smtp_configured = True
            st.session_state.smtp_email = smtp_email # Store for later use
            st.session_state.smtp_password = smtp_password # Store for later use
        except Exception as e:
            st.error(f'SMTP 配置失败: {str(e)}')
            st.session_state.smtp_configured = False
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 邮件发送设置卡片
    st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); margin-bottom: 2rem;">', unsafe_allow_html=True)
    st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">📤 邮件发送设置</h3>', unsafe_allow_html=True)
    
    # 修改每日发送上限的默认值和最大值
    daily_limit = st.slider('每日发送上限', min_value=1, max_value=200, value=30, help="设置每日最大发送邮件数量，避免触发邮件服务商限制。个人邮箱建议不超过50封。")
    interval_seconds = st.slider('发送间隔(秒)', min_value=10, max_value=300, value=60, help="两封邮件之间的时间间隔，建议不少于10秒，以降低被识别为垃圾邮件的风险。")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 添加使用统计
    st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);">',
                unsafe_allow_html=True)
    st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">📊 使用统计</h3>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        website_count = 0
        if st.session_state.websites is not None:
            website_count = len(st.session_state.websites)
        st.markdown(
            f'<div class="metric-card" style="padding: 1rem;">'            
            f'<p class="metric-value">{website_count}</p>'            
            f'<p class="metric-label">已添加网站</p>'            
            f'</div>',            
            unsafe_allow_html=True
        )
    with col2:
        contact_count = 0
        if st.session_state.contacts is not None:
            # Flatten the list of social links for total count, or count rows with contacts
            contact_count = len(st.session_state.contacts)
        st.markdown(
            f'<div class="metric-card" style="padding: 1rem;">'            
            f'<p class="metric-value">{contact_count}</p>'            
            f'<p class="metric-label">已获取联系人</p>'            
            f'</div>',            
            unsafe_allow_html=True
        )
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 添加页脚
    st.markdown(
        '<div class="footer">'        
        f'<p>当前日期: {st.session_state.current_date}</p>'        
        '<p>批量联系方式爬取与群发工具 v1.0</p>'        
        '</div>',        
        unsafe_allow_html=True
    )

# 创建主要内容区域的选项卡
tab1, tab2, tab3 = st.tabs(["1️⃣ 上传网站列表", "2️⃣ 爬取联系方式", "3️⃣ 邮件群发"])

# Tab 1: 上传网站列表
with tab1:
    st.markdown('<h2 style="color: #1E293B; margin-bottom: 1.5rem;">上传网站列表</h2>', unsafe_allow_html=True)
    st.markdown('<p style="color: #64748B; margin-bottom: 2rem;">请通过文件导入或手动输入方式添加您需要爬取的网站列表</p>', unsafe_allow_html=True)
    
    # 创建两个卡片式列
    col1, col2 = st.columns(2, gap="large")
    
    with col1:
        # 文件导入卡片
        st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); height: 100%;">',
                    unsafe_allow_html=True)
        st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">📁 从文件导入</h3>', unsafe_allow_html=True)
        
        # 文件上传区域美化
        st.markdown('<div style="border: 2px dashed #E2E8F0; border-radius: 10px; padding: 1.5rem; text-align: center; margin-bottom: 1rem;">', unsafe_allow_html=True)
        st.markdown('<p style="color: #64748B; margin-bottom: 0.5rem;">支持 TXT 或 CSV 格式文件</p>', unsafe_allow_html=True)
        uploaded_file = st.file_uploader('', type=['txt', 'csv'], label_visibility="collapsed")
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 文件格式说明
        with st.expander("文件格式说明"):
            st.markdown("""
            - **TXT 文件**: 每行一个网址
            - **CSV 文件**: 包含 URL 列，每行一个网址
            - 网址格式: 建议包含 http:// 或 https:// 前缀，例如：`https://example.com`
            """)
        
        if uploaded_file is not None:
            try:
                # 处理上传的文件
                with st.spinner('正在处理文件...'):
                    websites_df = process_website_file(uploaded_file)
                    st.session_state.websites = websites_df
                st.success(f'✅ 成功导入 {len(websites_df)} 个有效网址')
            except Exception as e:
                st.error(f'❌ 文件处理错误: {e}')
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        # 手动输入卡片
        st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); height: 100%;">',
                    unsafe_allow_html=True)
        st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">✏️ 手动输入</h3>', unsafe_allow_html=True)
        
        # 文本输入区域美化
        st.markdown('<p style="color: #64748B; margin-bottom: 0.5rem;">每行输入一个网址</p>', unsafe_allow_html=True)
        manual_urls = st.text_area('', placeholder='例如:\nhttps://example.com\nhttps://another-site.com', height=150, label_visibility="collapsed")
        
        # 添加按钮
        add_button = st.button('添加网址', use_container_width=True)
        
        if add_button:
                    if manual_urls:
                        urls = [url.strip() for url in manual_urls.split('\n') if url.strip()]
                        if urls:
                            with st.spinner('正在处理网址...'):
                                try:
                                    from io import StringIO
                                    # 将手动输入的URLs字符串连接起来，模拟一个txt文件的内容
                                    file_content_string = "\n".join(urls)
                                    file_content = StringIO(file_content_string)
                            
                                    # 直接将StringIO对象传递给process_website_file函数
                                    websites_df = process_website_file(file_content)
                                    st.session_state.websites = websites_df
                                    st.success(f'✅ 成功添加 {len(websites_df)} 个有效网址')
                                except Exception as e:
                                    st.error(f'❌ 处理错误: {e}')
                        else:
                            st.warning('⚠️ 请输入至少一个有效网址')
                    else:
                        st.warning('⚠️ 请输入至少一个网址')
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # 显示导入的网址列表
    if st.session_state.websites is not None and len(st.session_state.websites) > 0:
        st.markdown('<div style="margin-top: 2rem;">', unsafe_allow_html=True)
        st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">🔍 网址列表预览</h3>', unsafe_allow_html=True)
        
        # 创建一个容器来包装数据框
        st.markdown('<div class="dataframe-container">', unsafe_allow_html=True)
        st.dataframe(st.session_state.websites, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 添加清除按钮
        if st.button('清除网址列表', key='clear_websites'):
            st.session_state.websites = None
            st.session_state.contacts = None # Also clear contacts if websites are cleared
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)

# Tab 2: 爬取联系方式
with tab2:
    st.markdown('<h2 style="color: #1E293B; margin-bottom: 1.5rem;">爬取联系方式</h2>', unsafe_allow_html=True)
    
    if st.session_state.websites is None or len(st.session_state.websites) == 0:
        # 美化警告信息
        st.markdown(
            '<div style="background-color: #FEF3C7; color: #92400E; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">'            
            '<h3 style="font-size: 1.2rem; margin-bottom: 0.5rem;">⚠️ 未找到网站列表</h3>'            
            '<p>请先在"上传网站列表"选项卡中添加需要爬取的网站。</p>'            
            '</div>',            
            unsafe_allow_html=True
        )
        
        # 添加快速跳转按钮
        if st.button('前往上传网站列表', use_container_width=True):
            # 使用JavaScript切换到第一个选项卡
            st.markdown(
                """<script>document.querySelector('[data-baseweb="tab"]').click();</script>""",
                unsafe_allow_html=True
            )
    else:
        # 创建两列布局
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # 爬取控制面板
            st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); margin-bottom: 1.5rem;">',
                        unsafe_allow_html=True)
            
            if not st.session_state.crawling:
                st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">🔍 开始爬取</h3>', unsafe_allow_html=True)
                st.markdown(f'<p style="color: #64748B; margin-bottom: 1rem;">准备爬取 {len(st.session_state.websites)} 个网站的联系方式</p>', unsafe_allow_html=True)
                
                # 爬取按钮
                start_crawl = st.button('开始爬取联系方式', key='start_crawl', use_container_width=True)
                
                if start_crawl:
                    st.session_state.crawling = True
                    st.rerun()
            else:
                st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">🔄 正在爬取中...</h3>', unsafe_allow_html=True)
                
                # 创建进度条和状态文本
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # 开始爬取
                websites = st.session_state.websites
                total_sites = len(websites)
                
                contacts = []
                for i, (_, row) in enumerate(websites.iterrows()):
                    # 创建单行DataFrame
                    single_site = pd.DataFrame([row])
                    status_text.markdown(f'<p style="color: #4F6DF5;">正在爬取 {i+1}/{total_sites}: <strong>{row["URL"]}</strong></p>', unsafe_allow_html=True)
                    
                    # 爬取单个网站
                    try:
                        site_contacts_df = crawl_contacts(single_site) # crawl_contacts now returns a DataFrame
                        contacts.append(site_contacts_df)
                        time.sleep(0.5) # 短暂延迟，避免请求过快
                    except Exception as e:
                        st.error(f"爬取 {row['URL']} 时出错: {str(e)}")
                    
                    # 更新进度条
                    progress_bar.progress((i + 1) / total_sites)
                
                # 合并结果
                if contacts:
                    all_contacts = pd.concat(contacts, ignore_index=True)
                    st.session_state.contacts = all_contacts
                    status_text.markdown('<p style="color: #047857; font-weight: bold;">✅ 爬取完成！</p>', unsafe_allow_html=True)
                    
                    # 显示统计信息
                    email_count = all_contacts['emails'].apply(lambda x: len(x) if isinstance(x, list) else 0).sum()
                    # Calculate total social links count
                    social_links_count = 0
                    for index, row in all_contacts.iterrows():
                        if isinstance(row['social_links'], dict):
                            for platform_links in row['social_links'].values():
                                social_links_count += len(platform_links)

                    st.markdown('<div style="display: flex; justify-content: space-around; margin-top: 1rem;">', unsafe_allow_html=True)
                    st.markdown(f'<div style="text-align: center;"><span style="font-size: 1.5rem; font-weight: bold; color: #4F6DF5;">{len(all_contacts)}</span><br><span style="color: #64748B;">网站</span></div>', unsafe_allow_html=True)
                    st.markdown(f'<div style="text-align: center;"><span style="font-size: 1.5rem; font-weight: bold; color: #4F6DF5;">{email_count}</span><br><span style="color: #64748B;">邮箱</span></div>', unsafe_allow_html=True)
                    st.markdown(f'<div style="text-align: center;"><span style="font-size: 1.5rem; font-weight: bold; color: #4F6DF5;">{social_links_count}</span><br><span style="color: #64748B;">社媒链接</span></div>', unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    status_text.markdown('<p style="color: #B91C1C; font-weight: bold;">⚠️ 爬取完成，但未找到任何联系方式</p>', unsafe_allow_html=True)
                
                st.session_state.crawling = False
                st.rerun() # Refresh to show results immediately

            st.markdown('</div>', unsafe_allow_html=True)
        
        with col2:
            # 爬取设置卡片
            st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); height: 100%;">',
                        unsafe_allow_html=True)
            st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">⚙️ 爬取设置</h3>', unsafe_allow_html=True)
            
            st.markdown('<p style="color: #64748B; margin-bottom: 0.5rem;">爬取内容包括：</p>', unsafe_allow_html=True)
            st.markdown('<div style="background-color: #F8FAFC; padding: 1rem; border-radius: 5px;">', unsafe_allow_html=True)
            st.markdown('<p style="margin-bottom: 0.5rem;">✉️ <strong>邮箱地址</strong> (包含文本、mailto链接及部分HTML属性中的邮箱)</p>', unsafe_allow_html=True)
            st.markdown('<p style="margin-bottom: 0.5rem;">🔗 <strong>联系页面</strong></p>', unsafe_allow_html=True)
            st.markdown('<p style="margin-bottom: 0;">📱 <strong>社交媒体链接</strong> (按平台分类)</p>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<br><h4 style="color: #1E293B; font-size: 1rem; margin-bottom: 0.5rem;">💡 注意</h4>', unsafe_allow_html=True)
            st.markdown('<p style="color: #64748B; font-size: 0.9rem;">本工具通过解析静态HTML内容进行爬取。对于大量依赖JavaScript动态加载内容的网站，可能无法获取所有联系方式。</p>', unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)
        
        # 显示爬取结果
        if st.session_state.contacts is not None and len(st.session_state.contacts) > 0:
            st.markdown('<div style="margin-top: 2rem;">', unsafe_allow_html=True)
            st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">📊 爬取结果</h3>', unsafe_allow_html=True)
            
            # ========== 动态社媒下拉框功能集成 ========== 
            # 替换原有静态facebook链接列与导出逻辑

            # 假定 contacts_df 为已处理的 DataFrame，包含 social_links 字段
            if 'contacts' in st.session_state and st.session_state.contacts is not None:
                contacts_df = st.session_state.contacts.copy()
                # 统计所有出现过的社交平台
                all_platforms = set()
                for links in contacts_df['social_links']:
                    if isinstance(links, dict):
                        all_platforms.update(links.keys())
                all_platforms = sorted(list(all_platforms))
                if not all_platforms:
                    all_platforms = ['(无社交链接)']  # 兜底，防止无社媒时报错
                # 下拉选择社交平台
                selected_platform = st.selectbox("选择社交平台", all_platforms, index=0)
                def get_links_str(social_links, platform):
                    if isinstance(social_links, dict) and platform in social_links:
                        return ', '.join(social_links[platform])
                    return '无'
                display_df = contacts_df.copy()
                if selected_platform == '(无社交链接)':
                    display_df["社交链接"] = "无"
                else:
                    display_df[f"{selected_platform} 链接"] = display_df['social_links'].apply(lambda x: get_links_str(x, selected_platform))
                # 只展示核心列
                columns_to_show = ["url", "emails"]
                if selected_platform != '(无社交链接)':
                    columns_to_show.append(f"{selected_platform} 链接")
                columns_to_show.append("error")
                display_df = display_df[columns_to_show]
                # 展示表格
                st.dataframe(display_df, use_container_width=True)
                # 导出当前平台数据
                csv = display_df.to_csv(index=False).encode('utf-8')
                st.download_button('导出数据', csv, file_name='contacts_export.csv', mime='text/csv')
            
            st.markdown('</div>', unsafe_allow_html=True)

# Tab 3: 邮件群发
with tab3:
    st.markdown('<h2 style="color: #1E293B; margin-bottom: 1.5rem;">邮件群发</h2>', unsafe_allow_html=True)
    
    # 添加每日发送数量警示提醒
    st.markdown(
        '<div style="background-color: #FFFBEB; color: #9A6C00; border: 1px solid #FAD14A; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem;">'
        '<h5>⚠️ 邮件发送数量警示</h5>'
        '<p>请注意，使用个人邮箱（如 Gmail）的 SMTP 服务进行大量群发邮件，<br>'
        '**有很高风险被服务提供商暂停发送功能甚至封号。**'
        '建议每日发送量控制在 **50 封以内**，并适当拉长发送间隔。<br>'
        '如果您有大量发送需求，请考虑使用专业的邮件营销服务。</p>'
        '</div>',
        unsafe_allow_html=True
    )

    if st.session_state.contacts is None or len(st.session_state.contacts) == 0:
        # 美化警告信息
        st.markdown(
            '<div style="background-color: #FEF3C7; color: #92400E; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">'            
            '<h3 style="font-size: 1.2rem; margin-bottom: 0.5rem;">⚠️ 未找到联系人数据</h3>'            
            '<p>请先在"爬取联系方式"选项卡中获取联系人信息。</p>'            
            '</div>',            
            unsafe_allow_html=True
        )
        
        # 添加快速跳转按钮
        if st.button('前往爬取联系方式', use_container_width=True):
            # 使用JavaScript切换到第二个选项卡
            st.markdown(
                """<script>document.querySelectorAll('[data-baseweb="tab"]')[1].click();</script>""",
                unsafe_allow_html=True
            )
    else:
        # 检查是否有邮箱地址
        has_emails = False
        email_count = 0
        all_target_emails = [] # 收集所有可发送的邮箱
        for _, row in st.session_state.contacts.iterrows():
            if row['emails'] and isinstance(row['emails'], list) and len(row['emails']) > 0:
                all_target_emails.extend(row['emails'])
        all_target_emails = list(set(all_target_emails)) # 去重
        email_count = len(all_target_emails)
        
        if email_count > 0:
            has_emails = True

        if not has_emails:
            # 美化警告信息
            st.markdown(
                '<div style="background-color: #FEF2F2; color: #991B1B; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">'                
                '<h3 style="font-size: 1.2rem; margin-bottom: 0.5rem;">❌ 未找到邮箱地址</h3>'                
                '<p>爬取的联系人数据中没有包含任何邮箱地址，无法发送邮件。请尝试爬取更多网站或检查爬取设置。</p>'                
                '</div>',                
                unsafe_allow_html=True
            )
        else:
            # 创建两列布局
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # 邮件模板设置卡片
                st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); margin-bottom: 1.5rem;">',
                            unsafe_allow_html=True)
                st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">✉️ 邮件模板设置</h3>', unsafe_allow_html=True)
                
                # 邮件主题
                email_subject = st.text_input('邮件主题', '您好，这是一封商务合作邮件')
                
                # 邮件模板
                st.markdown('<p style="color: #64748B; margin-bottom: 0.5rem;">邮件内容模板</p>', unsafe_allow_html=True)
                st.markdown('<p style="color: #64748B; font-size: 0.8rem; margin-bottom: 0.5rem;">可使用以下变量进行个性化：<code>{website_name}</code> (网站名称), <code>{url}</code> (完整网址)</p>', unsafe_allow_html=True)
                email_template = st.text_area('', DEFAULT_EMAIL_TEMPLATE, height=300, label_visibility="collapsed")
                
                # 模板预览
                with st.expander("📝 模板预览"):
                    # 使用示例数据进行预览
                    preview_template_content = email_template.replace('{website_name}', '示例公司').replace('{url}', 'https://www.example.com')
                    st.markdown(f"<div style='background-color: #F8FAFC; padding: 1rem; border-radius: 5px;'>{preview_template_content}</div>", unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)
                
                # SMTP配置检查
                # 获取侧边栏的SMTP配置
                configured_smtp_email = st.session_state.get('smtp_email', '')
                configured_smtp_password = st.session_state.get('smtp_password', '')

                if not st.session_state.smtp_configured or not configured_smtp_email or not configured_smtp_password:
                    st.markdown(
                        '<div style="background-color: #FEF2F2; color: #991B1B; padding: 1rem; border-radius: 10px; margin-bottom: 1rem;">'                        
                        '<h3 style="font-size: 1.2rem; margin-bottom: 0.5rem;">⚠️ SMTP未配置</h3>'                        
                        '<p>请在侧边栏中配置并测试SMTP设置后再发送邮件。</p>'                        
                        '</div>',                        
                        unsafe_allow_html=True
                    )
                else:
                    # 确保使用最新的SMTP配置
                    try:
                        smtp_config = configure_smtp(
                            server=smtp_server, # 从侧边栏获取
                            port=smtp_port,     # 从侧边栏获取
                            email=smtp_email,   # 从侧边栏获取
                            password=smtp_password, # 从侧边栏获取
                            use_tls=use_tls     # 从侧边栏获取
                        )
                    except Exception as e:
                        st.error(f"SMTP配置加载失败，请重新测试配置: {str(e)}")
                        smtp_config = None
                        st.session_state.smtp_configured = False # 标记为未配置，阻止发送

                    if smtp_config: # 只有当SMTP配置成功时才显示发送界面
                        # 发送邮件控制面板
                        st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);">',
                                    unsafe_allow_html=True)
                        
                        if not st.session_state.sending:
                            st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">📤 开始发送</h3>', unsafe_allow_html=True)
                            st.markdown(f'<p style="color: #64748B; margin-bottom: 1rem;">准备向 <strong>{email_count}</strong> 个邮箱地址发送邮件</p>', unsafe_allow_html=True)
                            
                            # 发送邮件按钮
                            send_col1, send_col2 = st.columns([3, 1])
                            with send_col1:
                                start_send = st.button('开始群发邮件', key='start_send', use_container_width=True)
                            with send_col2:
                                st.markdown(f'<div style="background-color: #DCFCE7; color: #166534; padding: 0.5rem; border-radius: 5px; text-align: center; margin-top: 0.2rem;">✓ SMTP已配置</div>', unsafe_allow_html=True)
                            
                            if start_send:
                                st.session_state.sending = True
                                
                                # 开始发送邮件
                                with st.spinner('正在发送邮件...'):
                                    send_log = send_bulk_email(
                                        contacts=st.session_state.contacts,
                                        smtp_config=smtp_config,
                                        email_template=email_template,
                                        email_subject=email_subject,
                                        daily_limit=daily_limit,
                                        interval_seconds=interval_seconds
                                    )
                                
                                # 显示发送结果
                                st.success('✅ 邮件发送完成！')
                                
                                # 显示发送统计
                                success_count = sum(1 for _, row in send_log.iterrows() if row['status'] == 'success')
                                failed_count = sum(1 for _, row in send_log.iterrows() if row['status'] == 'failed')
                                
                                st.markdown('<div style="display: flex; justify-content: space-around; margin: 1rem 0;">',
                                            unsafe_allow_html=True)
                                st.markdown(f'<div style="text-align: center;"><span style="font-size: 1.5rem; font-weight: bold; color: #4F6DF5;">{len(send_log.index)}</span><br><span style="color: #64748B;">总计发送尝试</span></div>', unsafe_allow_html=True)
                                st.markdown(f'<div style="text-align: center;"><span style="font-size: 1.5rem; font-weight: bold; color: #047857;">{success_count}</span><br><span style="color: #64748B;">成功</span></div>', unsafe_allow_html=True)
                                st.markdown(f'<div style="text-align: center;"><span style="font-size: 1.5rem; font-weight: bold; color: #B91C1C;">{failed_count}</span><br><span style="color: #64748B;">失败</span></div>', unsafe_allow_html=True)
                                st.markdown('</div>', unsafe_allow_html=True)
                                
                                # 显示发送日志
                                st.markdown('<h4 style="color: #1E293B; font-size: 1rem; margin: 1rem 0;">📋 发送日志</h4>', unsafe_allow_html=True)
                                st.markdown('<div class="dataframe-container">', unsafe_allow_html=True)
                                st.dataframe(send_log, use_container_width=True)
                                st.markdown('</div>', unsafe_allow_html=True)
                                
                                # 导出日志按钮
                                if st.button('导出发送日志', key='export_log'):
                                    # 生成带时间戳的文件名
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    log_filename = f'email_log_{timestamp}.csv'
                                    log_csv = send_log.to_csv(index=False).encode('utf-8')
                                    log_b64 = base64.b64encode(log_csv).decode()
                                    log_href = f'<a href="data:file/csv;base64,{log_b64}" download="{log_filename}" class="download-link" style="color: var(--primary-color); text-decoration: none;">点击下载 {log_filename}</a>'
                                    st.markdown(f'✅ 日志已导出: {log_href}', unsafe_allow_html=True)
                                
                                st.session_state.sending = False
                                st.rerun() # Refresh to clear sending state and allow re-sending
                        
                        st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                # 邮件发送统计卡片
                st.markdown('<div style="background-color: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05); height: 100%;">',
                            unsafe_allow_html=True)
                st.markdown('<h3 style="color: #1E293B; font-size: 1.2rem; margin-bottom: 1rem;">📊 邮件统计</h3>', unsafe_allow_html=True)
                
                # 显示统计信息
                st.markdown('<div style="background-color: #F8FAFC; padding: 1rem; border-radius: 5px; margin-bottom: 1rem;">', unsafe_allow_html=True)
                st.markdown(f'<p><strong>可发送邮箱数量:</strong> <span style="color: #4F6DF5; font-weight: bold;">{email_count}</span></p>', unsafe_allow_html=True)
                st.markdown(f'<p><strong>每日发送上限:</strong> <span style="color: #4F6DF5;">{daily_limit}</span></p>', unsafe_allow_html=True)
                st.markdown(f'<p><strong>发送间隔:</strong> <span style="color: #4F6DF5;">{interval_seconds}秒</span></p>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                # 邮件发送提示
                st.markdown('<h4 style="color: #1E293B; font-size: 1rem; margin-bottom: 0.5rem;">📝 发送提示</h4>', unsafe_allow_html=True)
                st.markdown('<ul style="color: #64748B; padding-left: 1.5rem;">', unsafe_allow_html=True)
                st.markdown('<li>确保SMTP服务器配置正确</li>', unsafe_allow_html=True)
                st.markdown('<li>适当设置发送间隔，避免被标记为垃圾邮件</li>', unsafe_allow_html=True)
                st.markdown('<li>邮件模板中可使用变量个性化内容</li>', unsafe_allow_html=True)
                st.markdown('<li>发送前检查邮件预览效果</li>', unsafe_allow_html=True)
                st.markdown('<li>请勿用于发送垃圾邮件或非法活动</li>', unsafe_allow_html=True)
                st.markdown('</ul>', unsafe_allow_html=True)
                
                st.markdown('</div>', unsafe_allow_html=True)

# 页脚
st.markdown('<div class="footer" style="margin-top: 3rem; text-align: center; color: #64748B; padding-top: 1rem; border-top: 1px solid #E2E8F0;">', unsafe_allow_html=True)
st.markdown('<p>📧 批量联系方式爬取与群发工具 | 版本 1.1.1 (社媒筛选优化)</p>', unsafe_allow_html=True)
st.markdown(f'<p>© {datetime.now().year} All Rights Reserved</p>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)