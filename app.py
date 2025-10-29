import io
from datetime import datetime

import pandas as pd
import streamlit as st

from crawler import crawl_contacts
from mailer import DEFAULT_EMAIL_TEMPLATE, configure_smtp, send_bulk_email
from utils import load_website_list


st.set_page_config(
    page_title="批量联系方式爬取与群发工具",
    page_icon="📧",
    layout="wide",
)


def init_state():
    st.session_state.setdefault("website_df", pd.DataFrame())
    st.session_state.setdefault("crawl_result", pd.DataFrame())
    st.session_state.setdefault("smtp_config", None)
    st.session_state.setdefault("send_log", pd.DataFrame())


def render_header():
    st.title("📧 批量联系方式爬取与邮件群发")
    st.caption(
        "上传或粘贴网址列表，自动爬取邮箱/社交链接，并可直接发送批量邮件。"
    )


def render_url_input():
    st.markdown("### 1. 导入网址列表")
    col1, col2 = st.columns(2)
    with col1:
        uploaded = st.file_uploader("上传CSV或TXT文件", type=["csv", "txt"])
    with col2:
        text_input = st.text_area(
            "或直接粘贴网址（每行一个，支持逗号分隔）",
            height=140,
            placeholder="https://example.com\nexample.org/contact",
        )

    if st.button("解析网址", type="primary"):
        if not uploaded and not text_input.strip():
            st.error("请上传文件或粘贴至少一个网址。")
            return
        try:
            source = uploaded if uploaded else io.StringIO(text_input)
            websites = load_website_list(source)
            st.session_state.website_df = websites
            st.success(f"成功导入 {len(websites)} 个网址。")
        except Exception as exc:  # noqa: BLE001
            st.error(f"解析网址失败：{exc}")

    if not st.session_state.website_df.empty:
        st.dataframe(st.session_state.website_df, use_container_width=True, height=200)


def render_crawl_section():
    st.markdown("### 2. 爬取联系方式")
    if st.session_state.website_df.empty:
        st.info("请先导入网址列表。")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        max_pages = st.number_input("每个网站最大爬取页面数", 1, 20, value=5)
    with col2:
        delay = st.number_input("页面间隔秒数", 0.0, 5.0, value=1.0, step=0.5)
    with col3:
        timeout = st.number_input("请求超时（秒）", 5, 60, value=12)

    if st.button("开始爬取", type="primary"):
        with st.spinner("爬取中，请稍候..."):
            result = crawl_contacts(
                st.session_state.website_df["url"].tolist(),
                max_pages_per_site=int(max_pages),
                delay=float(delay),
                timeout=int(timeout),
            )
            st.session_state.crawl_result = result
        st.success("爬取完成。")

    if not st.session_state.crawl_result.empty:
        result = st.session_state.crawl_result.copy()
        result["emails"] = result["emails"].apply(
            lambda emails: ", ".join(emails) if emails else "无"
        )
        result["social_summary"] = result["social_links"].apply(
            lambda links: ", ".join(
                f"{platform}({len(urls)})" for platform, urls in links.items()
            )
            if isinstance(links, dict) and links
            else "无"
        )
        result_display = result[
            ["url", "visited_pages", "emails", "social_summary", "error"]
        ]
        st.dataframe(result_display, use_container_width=True, height=320)

        csv_bytes = st.session_state.crawl_result.to_csv(index=False).encode("utf-8")
        st.download_button(
            "导出爬取结果",
            csv_bytes,
            file_name=f"contact_results_{datetime.now():%Y%m%d%H%M%S}.csv",
            mime="text/csv",
        )


def render_mail_section():
    st.markdown("### 3. 邮件群发")
    if st.session_state.crawl_result.empty:
        st.info("请先完成爬取并确认存在邮箱。")
        return

    col1, col2 = st.columns(2)
    with col1:
        smtp_server = st.text_input("SMTP服务器", value="smtp.gmail.com")
        smtp_port = st.number_input("端口", min_value=1, max_value=65535, value=587)
        use_tls = st.checkbox("使用TLS", value=True)
    with col2:
        smtp_email = st.text_input("登录邮箱")
        smtp_password = st.text_input("密码或授权码", type="password")

    if st.button("测试并保存SMTP配置"):
        try:
            config = configure_smtp(
                smtp_server, int(smtp_port), smtp_email, smtp_password, use_tls
            )
            st.session_state.smtp_config = config
            st.success("SMTP配置验证成功。")
        except Exception as exc:  # noqa: BLE001
            st.error(f"SMTP验证失败：{exc}")

    st.markdown("#### 邮件模板")
    subject = st.text_input("邮件主题", value="合作机会")
    template = st.text_area("邮件正文模板", value=DEFAULT_EMAIL_TEMPLATE, height=200)
    daily_limit = st.number_input("每日最大发送数量", 1, 500, value=50)
    interval = st.number_input("每封间隔（秒）", 0, 600, value=60)

    if st.button("开始群发邮件", type="primary"):
        if st.session_state.smtp_config is None:
            st.error("请先配置并验证SMTP。")
        else:
            emails_available = st.session_state.crawl_result[
                st.session_state.crawl_result["emails"].apply(lambda x: len(x) > 0)
            ]
            if emails_available.empty:
                st.error("当前结果中没有可用邮箱。")
            else:
                with st.spinner("发送中，请勿关闭页面..."):
                    log = send_bulk_email(
                        emails_available,
                        smtp_config=st.session_state.smtp_config,
                        email_template=template,
                        email_subject=subject,
                        daily_limit=int(daily_limit),
                        interval_seconds=int(interval),
                    )
                    st.session_state.send_log = log
                st.success("发送流程结束，请查看发送日志。")

    if not st.session_state.send_log.empty:
        st.markdown("#### 发送日志")
        st.dataframe(st.session_state.send_log, use_container_width=True, height=260)


def main():
    init_state()
    render_header()
    render_url_input()
    st.divider()
    render_crawl_section()
    st.divider()
    render_mail_section()
    st.write("")
    st.caption(f"版本 2.0 · 最后更新于 {datetime.now():%Y-%m-%d}")


if __name__ == "__main__":
    main()
