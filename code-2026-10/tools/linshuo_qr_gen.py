# -*- coding: utf-8 -*-
"""为 linshuo profile 生成微信绑定二维码 v3 (快速扫码版)"""
import qrcode, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

QR_VAL = "25175726f1c55d8ca360be4501288ea7"
QR_URL = "https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=25175726f1c55d8ca360be4501288ea7&bot_type=3"
OUT = "D:/hermes/data/wechat_qr_linshuo.png"

qr = qrcode.QRCode(version=2, box_size=8, border=3)
qr.add_data(QR_VAL)
qr.make(fit=True)
img = qr.make_image(fill_color="black", back_color="white")
img.save(OUT)
print(f"✅ PNG: {OUT}")

qr2 = qrcode.QRCode(version=2, box_size=1, border=2)
qr2.add_data(QR_VAL)
qr2.make(fit=True)
qr2.print_ascii(invert=True)

print(f"\n🔗 链接: {QR_URL}")
print(f"\n⚠️ 二维码35秒内有效, 请立即扫码!")
print(f"扫码后运行: python D:/hermes/analysis/linshuo_weixin_bind.py {QR_VAL}")
