"""
聊天记录导出 — 手动模式
你先打开微信的聊天窗口，脚本只负责滚动+读取，不会最小化或跳转
"""
import csv
import os
import time
import re
from datetime import datetime

from wx4py.core import uiautomation as uia

TARGET = input("请输入要导出联系人名称(仅用于文件名): ").strip()
MAX_MSG = input("最多导出多少条(默认500): ").strip()
MAX_MSG = int(MAX_MSG) if MAX_MSG else 500

os.makedirs("data/training", exist_ok=True)
OUTPUT = f"data/training/{TARGET}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

print(f"\n请确保:")
print(f"  1. 微信已打开，并手动点击进入与「{TARGET}」的聊天")
print(f"  2. 微信窗口可见，不要最小化")
input("\n准备好了按回车开始...")

# 找到微信窗口
wx = uia.WindowControl(searchDepth=1, ClassName="mmui::MainWindow")
if not wx.Exists(0, 0):
    wx = uia.WindowControl(searchDepth=1, Name="微信")
if not wx.Exists(0, 0):
    print("找不到微信窗口！"); exit(1)

# 找到消息列表
msg_list = None
for depth in range(3, 10):
    try:
        ml = wx.ListControl(searchDepth=depth, AutomationId="chat_message_list")
        if ml.Exists(0, 0.5):
            msg_list = ml
            break
    except:
        pass

if not msg_list:
    print("找不到消息列表！请确保已打开聊天窗口"); exit(1)

# 获取消息列表位置用于滚动
rect = msg_list.BoundingRectangle
cx = (rect.left + rect.right) // 2
cy = (rect.top + rect.bottom) // 2

print(f"开始采集，最多 {MAX_MSG} 条...")
print("过程中不要动鼠标键盘...")

collected = []
seen = set()

# 先滚到底
for _ in range(10):
    msg_list.WheelDown(20, waitTime=0.1)
time.sleep(0.5)

while len(collected) < MAX_MSG:
    # 读取当前可见消息
    new_count = 0
    children = msg_list.GetChildren()
    for child in children:
        try:
            name = child.Name
            cls = child.ClassName
            if cls in ("mmui::ChatTextItemView", "mmui::ChatBubbleItemView") and name:
                if name not in seen:
                    seen.add(name)
                    collected.append({"content": name})
                    new_count += 1
        except:
            pass

    if new_count == 0:
        break  # 没有新消息了

    print(f"  已采集 {len(collected)} 条...")

    # 向上滚动
    for _ in range(5):
        msg_list.WheelUp(8, waitTime=0.05)
    time.sleep(0.3)

# 写入 CSV
print(f"\n共采集 {len(collected)} 条，写入文件...")

with open(OUTPUT, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["类型", "内容"])
    for m in collected:
        w.writerow(["text", m["content"]])

print(f"完成! {OUTPUT}")
print(f"共 {len(collected)} 条消息")
