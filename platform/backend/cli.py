import argparse
import getpass
import sqlite3
from .config import Settings
from .db import Database
from .security import create_user


def main():
    parser = argparse.ArgumentParser(description='MOSS Studio 本地账号初始化')
    parser.add_argument('command', choices=['create-admin'])
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    password = getpass.getpass('管理员密码（至少10位）: ')
    if password != getpass.getpass('再次输入密码: '):
        parser.error('两次密码不一致')
    try:
        create_user(Database(Settings().db_path),args.username,password,'admin')
    except (ValueError,sqlite3.IntegrityError) as exc:
        parser.error('创建失败：账号重复或格式/密码不符合要求')
    print('管理员已创建。请在登录页使用该账号；密码不会保存到配置文件。')


if __name__ == '__main__':
    main()
