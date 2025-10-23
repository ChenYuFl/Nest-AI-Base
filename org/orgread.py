import os
import yaml
import configparser
import difflib

# 全局变量（供外部模块使用）
read_url = ""
read_d_name = ""


def load_config(config_path="config.ini"):
    """
    读取配置文件
    :param config_path: 配件文件路径
    :return:临时存储各个配置项的值
    """
    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")
    return config


def read_yml(file_path):
    """
    读取yml文件内容
    :param file_path: 读取文件路径
    :return: 返回文件内容/报错
    """
    try:
        with open(file_path, "r", encoding="utf-8") as yml:
            data = yaml.safe_load(yml)
            return data
    except Exception as e:
        print(f"读取 YAML 失败: {e}")
        return None


def search_by_name(data, search_name):
    """模糊查找 name"""
    if not isinstance(data, dict):
        print("数据格式错误！")
        return []

    matches = []
    for key, value in data.items():
        name = value.get("name", "")
        if search_name.lower() in name.lower() or difflib.SequenceMatcher(None, name.lower(), search_name.lower()).ratio() > 0.5:
            matches.append((key, value))
    return matches


def mode_name():
    """
    主函数：获取 name 对应的 url 和 d_name
    """
    # 调用常量
    global read_url, read_d_name

    # 读取配置文件的值
    config = load_config()
    yml_dir = config["DEFAULT"]["data_yml"]
    target_file = os.path.join(yml_dir, config["DEFAULT"]["target_file"])
    default_name = config["DEFAULT"]["mode_name"]

    # 读取文件中的数据
    data = read_yml(target_file)
    if not data:
        print("YAML 文件加载失败。")
        return None

    # 读取name
    name = input(f"请输入要查找的 name（留空使用配置文件中的 {default_name}）：").strip()
    if not name:
        name = default_name

    matches = search_by_name(data, name)
    if not matches:
        print(f"未找到与 name = '{name}' 匹配的源。")
        return None

    if len(matches) > 1:
        print("\n找到多个匹配项：")
        for i, (k, v) in enumerate(matches, start=1):
            print(f"{i}. {v.get('name', '未知')} - {v.get('introduction', '无介绍')}")
        while True:
            try:
                idx = int(input("请输入要选择的序号："))
                if 1 <= idx <= len(matches):
                    key, value = matches[idx - 1]
                    break
                else:
                    print("输入超出范围，请重新输入。")
            except ValueError:
                print("请输入数字。")
    else:
        key, value = matches[0]

    # 将读取到的url和d_name进行存储常量
    read_url = value.get("url", "")
    read_d_name = value.get("d_name", "")

    # 测试调用
    # print(f"\n已选择：{value.get('name', '未知')} ({read_d_name})")
    # print(f"下载地址：{read_url}\n")

    return {"url": read_url, "d_name": read_d_name}


# 如果被其他文件导入，则自动运行 mode_name() 并设置全局变量
if __name__ != "__main__":
    result = mode_name()
    if result:
        read_url = result["url"]
        read_d_name = result["d_name"]
