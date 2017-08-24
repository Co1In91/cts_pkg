import os
import sys
import logging
import re
import yaml
import time
import markup
import getopt
import urllib2
import urllib
from qcloud_cos import StatFileRequest, UploadFileRequest, CosClient

proxy = None
cos_info = yaml.load(open('cos.yaml', 'r'))
app_id = int(cos_info['app_id'])
secret_id = unicode(cos_info['secret_id'])
secret_key = unicode(cos_info['secret_key'])
region = unicode(cos_info['region'])
bucket = unicode(cos_info['bucket'])
cts_url = cos_info['cts_url']

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s: %(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)


class Package(object):
    def __init__(self, url):
        self.url = url
        self.filename = url.split('/')[-1]

    @property
    def status(self):
        """
        :return: need update, not exist, newest
        """
        if not self.exist():
            if 'android-cts-7.1' in os.listdir(os.path.join('packages', 'CTS')):
                return 'need update'
            else:
                return 'not exist'
        else:
            return 'newest'

    def exist(self):
        if os.path.exists(os.path.join('packages', 'CTS', self.filename)):
            return True
        else:
            return False

    @property
    def file_type(self):
        """ 'media' or 'test' """
        if 'android-cts-media' in self.filename:
            return 'media'
        elif 'verifier' in self.filename:
            return 'verifier'
        else:
            return 'test'

    @property
    def android_version(self):
        # android-cts-7.1_r7-linux_x86-arm.zip
        if 'android-cts-media' not in self.filename:
            if 'verifier' in self.filename:
                return re.search(r'android-cts-verifier-(.+?)_', self.filename).group(1)
            return re.search(r'android-cts-(.+?)_', self.filename).group(1)

    @property
    def release(self):
        if 'android-cts-media' not in self.filename:
            return re.search(r'_(r\d*?)-', self.filename).group(1)

    @property
    def os(self):
        if 'android-cts-media' not in self.filename:
            return re.search(r'r\d{1,2}-(.+).zip', self.filename).group(1)


def all_packages_info(packages):
    cts_packages_info(packages)
    verifier_packages_info(packages)
    media_packages_info(packages)


def cts_packages_info(packages):
    cts_packages = filter(lambda x: x.file_type == 'test', packages)
    print '[CTS packages]'
    print 'OS               Release      Platform           Local         URL'
    for p in cts_packages:
        print '%-16s %-12s %-18s %-13s %s' % \
              (str('Android ' + p.android_version), str(p.release), str(p.os), p.status, p.url)


def verifier_packages_info(packages):
    verifier_packages = filter(lambda x: x.file_type == 'verifier', packages)
    print '\n\n[CTS Verifier packages]'
    print 'OS               Release      Platform           Local         URL'
    for p in verifier_packages:
        print '%-16s %-12s %-18s %-13s %s' % \
              (str('Android ' + p.android_version), str(p.release), str(p.os), p.status, p.url)


def media_packages_info(packages):
    media_packages = filter(lambda x: x.file_type == 'media', packages)
    print '\n\n[Media packages]'
    print 'Package Name                                     Local         URL'
    for p in media_packages:
        print '%-48s %-13s %s' % \
              (str(p.filename), p.status, p.url)


def parse_packages_url(html_content):
    parsed_urls = re.findall(r'(https://dl.google.com/.+.zip)', html_content)
    return parsed_urls


def generate_html(packages):
    page = markup.page()
    page.init(title="CTS Packages",
           )
    page.pre()
    for package in packages:
        page.a(package.filename, href=cos_info['cos_url'] + package.filename)
    page.pre.close()
    with open('index.html', 'w') as t:
        t.write(str(page))
        t.close()
    cos_client = CosClient(app_id, secret_id, secret_key, region)
    request = UploadFileRequest(bucket, unicode('/cts/index.html'), unicode('index.html'))
    upload_file_ret = cos_client.upload_file(request)
    print upload_file_ret


def read_html():
    if proxy:
        proxy_handler = urllib2.ProxyHandler({"https": proxy})
        opener = urllib2.build_opener(proxy_handler)
        urllib2.install_opener(opener)
    else:
        pass
    response = urllib2.urlopen(cts_url, timeout=5).read()
    return response


def retrieve_packages():
    packages = []
    html = read_html()
    urls = parse_packages_url(html)
    for url in urls:
        packages.append(Package(url))
    return packages


def report(count, block_size, total_size):
    percent = int(count * block_size * 100 / total_size)
    sys.stdout.write("\r%d%%" % percent + ' complete')
    sys.stdout.flush()


def update_packages(url_list):
    cos_client = CosClient(app_id, secret_id, secret_key, region)
    for package in url_list:
        print package.filename
        if package.status == 'need update':
            print 'update'
        elif package.status == 'not exist':
            print 'downloading', package.filename
            urllib.urlretrieve(package.url, os.path.join('packages', 'CTS', package.filename), reporthook=report)
            sys.stdout.flush()
        else:
            print 'skip', package.filename

        request = StatFileRequest(bucket, unicode('/cts/' + package.filename))
        stat_file_ret = cos_client.stat_file(request)
        if stat_file_ret['code'] != 0:
            file_path = os.path.join(os.path.dirname(__file__), 'packages', 'CTS', package.filename)
            request = UploadFileRequest(bucket, unicode('/cts/' + package.filename), unicode(file_path))
            upload_file_ret = cos_client.upload_file(request)
            print upload_file_ret


if __name__ == '__main__':
    try:
        options, args = getopt.getopt(
            sys.argv[1:],
            'hlup:d:s:',
            ['help', 'list', 'update', 'proxy', 'download', 'search']
        )
    except getopt.GetoptError as err:
        print err
        sys.exit(0)

    for name, value in options:
        if name in ('-p', '--proxy'):
            proxy = value
        if name in ('-l', '--list'):
            all_packages_info(retrieve_packages())
        if name in ('-u', '--update'):
            update_packages(retrieve_packages())
        if name in ('-d', '--download'):
            packages = retrieve_packages()
            update_packages(filter(lambda x: x.filename == value, packages))
        if name in ('-s', '--search'):
            packages = retrieve_packages()
            for package in packages:
                if package.android_version == value:
                    print package.filename
        if name in ('-h', '--html'):
            packages = retrieve_packages()
            generate_html(packages)
