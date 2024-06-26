

import os
import random
import re
import sys
import time
import argparse
import requests
import platform
import subprocess
import shutil
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from tqdm import tqdm
import zipfile
from datetime import datetime, timedelta
import sqlite3 as sq
import mimetypes

# 创建数据库
def CreateDataBase():
    con = sq.connect("Twitter.db")
    result = con.execute("""CREATE TABLE IF NOT EXISTS TwittersIoC (
        Account TEXT,
        LinkToTweet TEXT,
        DateTime TEXT,
        Hashtag TEXT,
        TypeIoC TEXT,
        IoC TEXT
    )""").fetchone()
    con.commit()
    return con


# 插入数据并进行去重查询
def Insert(con, name, linkTweet, DTime, Hashtag, Type, IoC_list):
    for ioc in IoC_list:
        insert_info_list = [(str(name), str(linkTweet), str(DTime), str(Hashtag), str(Type), str(ioc))]
        cur = con.cursor()
        if ioc:
            cur.execute("select * from TwittersIoC where  IoC=?", [str(ioc)])
            if cur.fetchone() is None:
                con.executemany("""INSERT INTO TwittersIoC VALUES (?, ?, ?, ?, ?, ?)""", insert_info_list)
                con.commit()


# 下载chrome_driver, 如果没有对应的版本, 则找一个相近的版本
def download_chrome_driver():
    small_version_number = 100
    system = platform.system()
    arch = platform.architecture()[0].replace('bit', '')
    print('system = ', system)
    if system == "Windows":
        platform_name = f"win32"
    elif system == 'Darwin':
        platform_name = f'mac{arch}'
    else:
        raise Exception('不支持的操作系统')
    print('platform_name = ', platform_name)
    chrome_version = subprocess.run('reg query "HKEY_CURRENT_USER\\Software\\Google\\Chrome\\BLBeacon" /v version',
                                    stdout=subprocess.PIPE, shell=True,
                                    text=True).stdout.strip().split()[-1]
    print('chrome_version = ', chrome_version)
    chrome_version_int = chrome_version.rsplit('.', 1)[0]
    download_url = (f'https://storage.googleapis.com/chrome-for-testing-public/'
                    f'{chrome_version}/{platform_name}/chromedriver-{platform_name}.zip')
    response = None
    while small_version_number < 200:
        # noinspection PyBroadException
        try:
            session = requests.session()
            session.trust_env = False
            response = session.get(url=download_url, stream=True)
            if response.status_code == 200:
                break
            small_version_number += 1
            download_url = (f'https://storage.googleapis.com/chrome-for-testing-public/'
                            f'{chrome_version_int}.{small_version_number}/{platform_name}/'
                            f'chromedriver-{platform_name}.zip')
        except Exception as _:
            small_version_number += 1
            download_url = (f'https://storage.googleapis.com/chrome-for-testing-public/'
                            f'{chrome_version_int}.{small_version_number}/{platform_name}/'
                            f'chromedriver-{platform_name}.zip')

    print('download_url = ', download_url)

    content_disposition = response.headers.get('Content-Disposition')
    if content_disposition:
        filename = content_disposition.split('filename=')[-1].strip('"')
    else:
        filename = download_url.split("/")[-1]

    total_size_in_bytes = int(response.headers.get('content-length', 0))
    progress_bar = tqdm(total=total_size_in_bytes, unit='B', unit_scale=True)

    with open(filename, 'wb') as fname:
        for data in response.iter_content(chunk_size=1024):
            fname.write(data)
            progress_bar.update(len(data))
    progress_bar.close()

    with zipfile.ZipFile(filename, 'r') as zip_ref:
        # Extract all files
        for zfile in zip_ref.namelist():
            print(os.path.basename(zfile))
            zip_ref.extract(zfile, "./")
            if not os.path.basename(zfile).startswith('chromedriver'):
                continue

            source = os.path.join("./", zfile)
            dest = os.path.join("./", os.path.basename(zfile))
            os.rename(source, dest)
    try:
        os.remove(os.path.basename(filename))
        shutil.rmtree(os.path.basename(filename.split('.', 1)[0]))
        print(f"Deleted file: {os.path.basename(filename)}")
    except OSError as e:
        print(f"Error deleting file: {os.path.basename(filename)} - {e}")
    print(f'本地已安装的 Chrome {chrome_version} 对应的 WebDriver 已下载并保存到 {os.getcwd()} 目录。')


# twitter 登录
def login_twitter():
    try:
        # 设置浏览器窗口大小
        # driver.set_window_size(126, 512)  # 替换为你需要的宽度和高度
        driver.get('https://x.com/i/flow/login')

        time.sleep(6)
        print('正在输入账号')
        # 输入账号
        username_input = driver.find_element(By.XPATH, '//input[@autocomplete="username"]')
        # 提交表单
        username_input.send_keys(account)
        username_input.send_keys(Keys.RETURN)

        time.sleep(3)
        print('正在输入手机号或用户名')
        # 输入手机号或用户名
        phone_or_username_input = driver.find_element(By.XPATH, '//input[@data-testid="ocfEnterTextTextInput"]')
        # 提交表单
        phone_or_username_input.send_keys(phone_or_username)
        phone_or_username_input.send_keys(Keys.RETURN)

        time.sleep(3)
        print('正在输入密码')
        # 输入密码
        password_input = driver.find_element(By.XPATH, '//input[@name="password"]')
        # 提交表单
        password_input.send_keys(password)
        password_input.send_keys(Keys.RETURN)

        # 登录
        print('正在登录')
        time.sleep(6)
        content = driver.page_source
        if 'Unlock more posts by subscribing' in content:
            sys.exit('已达到今天查看帖子的限制, 请稍后重试.')
        print("Logged in successfully")
        return True
    except Exception as e:
        return False


# 模拟向下滚动的函数
def scroll_down(scroll_pause_time=3, max_scrolls=1, con=None, link=None):
    last_height = driver.execute_script("return document.body.scrollHeight")
    scrolls = 0

    check_scroll = deal_articles_info_insert_db(con, link)
    if not check_scroll:
        return False

    while scrolls < max_scrolls:
        # 向下滚动到页面底部
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(scroll_pause_time)

        # 计算新的滚动高度并与上一次的滚动高度进行比较
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break  # 如果高度没有变化，说明已经到底部
        last_height = new_height

        # 处理博主文章信息并进行数据插入
        check_scroll = deal_articles_info_insert_db(con, link)
        if not check_scroll:
            break
        scrolls += 1


def is_filename(domain):
    # 检查是否有文件扩展名
    if '.' in domain:
        ext = os.path.splitext(domain)[1]
        # 如果扩展名在mimetypes中能找到对应的类型，则认为是文件名
        if mimetypes.types_map.get(ext.lower()) or ext == '.lnk' or ext == '.docx':
            return True
    return False


# 处理文章内容并进行入库
def deal_articles_info_insert_db(con, link):
    # 获取博主页面的内容
    # content = driver.page_source
    # print(f'content = {content}')

    articles = driver.find_elements(By.CSS_SELECTOR, 'article')
    check_scroll = True
    for article in articles:
        try:
            content = ((article.find_element(By.CSS_SELECTOR, 'div[lang]').text
                        .replace('\n', '======').replace('[', '')
                        .replace(']', '').replace('\\.', '.'))
                       .replace('hxxp', 'http').replace('hXXp', 'http'))
        except Exception as e:
            content = ''
        try:
            time_element = datetime.strptime(article.find_element(By.TAG_NAME, 'time').get_attribute('datetime')
                                             , "%Y-%m-%dT%H:%M:%S.%fZ")

        # 输出每篇文章的链接
            link_elements = (article.find_element(By.LINK_TEXT, article.find_element(By.TAG_NAME, 'time').text)
                             .get_property('href'))
            print(f'link_elements = {link_elements}')
            print('time_element = ', time_element)
        except Exception as e:
            return True

        # 判断时间是否早于设定时间
        if time_element < limit_time:
            # print(f'time_element < limit_time = {time_element} < {limit_time}')
            check_scroll = False
            continue
        else:
            check_scroll = True
        print('article = ', content)

        # 匹配需要的各个信息
        hashtaglist = re.findall(r'#.{0,2}[-\w]+', content)
        hashtaglist = ','.join(hashtag for hashtag in hashtaglist if hashtag)

        urllist = re.findall(
            r'(h.{2}ps?:/{0,2}([0-9a-zA-Z][-a-zA-Z0-9]{0,62}\.)?[a-zA-Z0-9][-a-zA-Z0-9]{0,62}\.[a-zA-Z]{0,62}(=|((dev|space|com|li|org|biz|site|life|cn|xyz|live|net|ru|cc|fun|quest|shop|store|pub)+[a-zA-Z]{0,3}\b)))',
            content)
        url_list = []
        if url_list:
            for dm in urllist:
                dm_url = str(dm[0])
                domain_check = re.search(f'{dm_url}.*?…', content)
                if (not domain_check or dm_url.endswith('=')) and not dm_url.replace('=', '').endswith('.'):
                    url_list.append(dm_url.replace('=', ''))

        maillist = re.findall(r'\w+@\w+\[.]\w+', content)
        sha256list = re.findall(r'\b[a-zA-Z0-9]{64}\b', content)
        sha1list = re.findall(r'\b[a-zA-Z0-9]{40}\b', content)
        md5list = re.findall(r'\b[a-zA-Z0-9]{32}\b', content)
        domainlist = re.findall(
            r'(([0-9a-zA-Z][-a-zA-Z0-9]{0,62}\.)?[a-zA-Z0-9][-a-zA-Z0-9]{0,62}\.[a-zA-Z]{0,62}(=|((dev|space|com|li|org|biz|site|life|cn|xyz|live|net|ru|cc|fun|quest|shop|store|pub)+[a-zA-Z]{0,3}\b)))',
            content)
        # print(f'urllist = {urllist}')
        # print(f'domainlist = {domainlist}')
        domain_list = []
        if domainlist:
            for dm in domainlist:
                dm_domain = str(dm[0]).replace(' ', '')
                domain_check = re.search(f'{dm_domain}.*?…', content)
                if (not domain_check or dm_domain.endswith('=')) and not dm_domain.replace('=', '').endswith('.') and not is_filename(dm_domain.replace('=', '')):
                    domain_list.append(dm_domain.replace('=', ''))

        IPV4_RE = re.compile(r"""
                                                            (?:^|
                                                                (?![^\d\.])
                                                            )
                                                            (?:
                                                                (?:[1-9]?\d|1\d\d|2[0-4]\d|25[0-5])
                                                                [\[\(\\]*?\.[\]\)]*?
                                                            ){3}
                                                            (?:[1-9]?\d|1\d\d|2[0-4]\d|25[0-5])
                                                            (?:(?=[^\d\.])|$)
                                                        """, re.VERBOSE)
        ipv4list = IPV4_RE.findall(content)

        # 数据入库
        Insert(con, link, link_elements, time_element, hashtaglist, 'Url', url_list)
        Insert(con, link, link_elements, time_element, hashtaglist, 'Mail', maillist)
        Insert(con, link, link_elements, time_element, hashtaglist, 'Domain', domain_list)
        Insert(con, link, link_elements, time_element, hashtaglist, 'Md5', md5list)
        Insert(con, link, link_elements, time_element, hashtaglist, 'sha256', sha256list)
        Insert(con, link, link_elements, time_element, hashtaglist, 'sha1', sha1list)
        Insert(con, link, link_elements, time_element, hashtaglist, 'ip', ipv4list)
        print(f'Url = {url_list}\nMail = {maillist}\nDomain = {domain_list}\nMd5 = {md5list}\nsha256 = {sha256list}\n'
              f'sha1 = {sha1list}\nip = {ipv4list}\n')
        print('-' * 20)
    time.sleep(random.randint(3, 6))
    return check_scroll


def get_ioc_type_info(link, con, scroll_num):
    driver.get(f'{link}')
    time.sleep(random.randint(3, 6))
    print(f'scroll_num = {scroll_num}')
    scroll_down(scroll_pause_time=6, max_scrolls=scroll_num, con=con, link=link)


def get_content(con):
    global limit_time, proxy, driver, blogger_username_set
    print('开始登录twitter')
    # 登录twitter, 如果连续登录失败超过三次这退出停止程序
    try_agin_number = 3
    scroll_num = 3
    while try_agin_number > 0:
        if login_twitter():
            break
        print(f'try_agin_number = {try_agin_number}')
        try_agin_number -= 1
    if try_agin_number <= 0:
        sys.exit('Twitter 三次登录失败')
    for blogger_username in blogger_username_set:
        # 访问指定博主的页面
        link = f'https://x.com/{blogger_username}'
        print('link = ', link)
        get_ioc_type_info(link, con, scroll_num)

    print('已经爬取完成')
    driver.quit()


def get_blogget_info(bfilename):
    if not os.path.exists(bfilename):
        sys.exit(f'{bfilename} is not exist')
    with open(bfilename, 'r+', encoding='utf-8') as bfile:
        return {binfo.replace('\n', '') for binfo in bfile.readlines() if binfo.replace('\n', '')}


if __name__ == '__main__':
    parse = argparse.ArgumentParser()
    parse.add_argument('-bz', '--blogger', default='blogger_name.txt', help='存储博主的文件名, 默认值:blogger_name.txt')
    parse.add_argument('-n', '--ndays', default=30, help='提取多少天前的情报, 默认30天。')
    parse.add_argument('-pr', '--proxy', default='None', help='配置http代理, 默认值: 127.0.0.1:10809, 若不用代理则设为None')
    parse.add_argument('-a', '--account', default='test@163.com', help='账号,  默认值:test@163.com')
    parse.add_argument('-pw', '--password', default='test', help='密码, 默认值:test')
    parse.add_argument('-pu', '--phone_or_username', default='test', help='手机号或用户名, 默认值:test')

    args = parse.parse_args()
    blogger_filename = args.blogger
    ndays = args.ndays
    proxy = args.proxy
    start_time = int(time.time())
    limit_time = datetime.now() - timedelta(days=ndays)

    print('limit_time = ', limit_time)

    account = args.account
    password = args.password
    phone_or_username = args.phone_or_username
    blogger_username_set = get_blogget_info(blogger_filename)

    # 下载chrome 版本
    if not os.path.exists('chromedriver.exe'):
        download_chrome_driver()

    print(f'blogger_username_set len = {len(blogger_username_set)}\nblogger_username_set = {blogger_username_set}')
    db_con = CreateDataBase()
    service = ChromeService(executable_path='./chromedriver.exe')
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 后台运行模式
    if 'None' not in proxy:
        chrome_options.add_argument(f'--proxy-server=http=http://{proxy}')
        chrome_options.add_argument(f'--proxy-server=https=http://{proxy}')
    else:
        print('不使用代理')
    driver = webdriver.Chrome(service=service, options=chrome_options)

    get_content(db_con)
    print(f'spendtime = {int(time.time()) - start_time}')
