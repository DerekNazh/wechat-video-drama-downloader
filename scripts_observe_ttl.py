# -*- coding: utf-8 -*-
"""TTL 观察任务（临时测试点）：每天检查 TikHub 返回的视频直链是否仍有效，直到发现过期。
零成本：直接探测 wxapp.tc.qq.com CDN（不调 TikHub API、不扣费）。
链接来源：2026-10-27 实测 fetch_video_detail(share_url=As68wzqwSd) 返回的 media.full_url。
幂等：同一天重复运行不重复记录。过期判定：HTTP 403/404/410 = 已过期。
"""
import datetime
import os
import sys
import urllib.request
import urllib.error

FULL_URL = "http://wxapp.tc.qq.com/251/20302/stodownload?encfilekey=Cvvj5Ix3eewQsFvYyicia1J2LkxedwDYuRfwzqiaTJ2Mw7RibjEPlxT0Y6mJKSA4MvY1loEUeTaGSYt2sHyvN8LW4P4iaUU6R74PXlnq0Xico92zsL0oJ5fFstNA&hy=SZ&idx=1&m=fbf6f232a55a5fab172b57b12d31e692&uzid=7b5d4&token=ic1n0xDG6aw9J8ElNRzpCdDuMnd6eyUIicHgOtkHnbKH0MoTniaE8pRpZSxlEnVmddwhajlgnmgqWZialuGhLDHfs3Rg3dLZOT9iaBWxeoL7lK7uEecPBSzydicmpt5s9nbCF5MeARSgB3yeGmgPnvCfpcIglfX4s9hUSmGCtuVibqZiczkm6OXeyOXichgO2icRLAOF9tgQzAuzR4Fm89p6lSuXt1gw2Ub2f0f7G5KSbpWQBs3OU&basedata=CAMSBnhXVDExMiI2CgoKBnhXVDExMhABCgoKBnhXVDExMhABCgoKBnhXVDExMRAACgcKA3hBMBAACgcKA3hBMhAAMAE6BAgCEAJCMK0FQ7JxYPA1eNQcdd7T22ZzIlZFArcEjghscTfo9L8cNQ_otiVMQWBk15UJJWxM50j0_YLXBg&sign=M13KOSKXQUuQj_eUgbIiHIsd4cKq1ezcQhYI9aFbwb-Gus2P3i7E_nGSo9gIRVRZQD5M9nVC1Cq4lYjN2-8Ylw&extg=1074c00&svrbypass=AAuL%2FQsFAAABAAAAAADNkSDj0bxbnMgb9L7gahAAAADnaHZTnGbFfAj9RgZXfw6VQKTup4A8WnBdIdVXbcMfSQX1pOxv2LiekOlOAmn%2FWq5xAY7FU20Uxo0%3D&svrnonce=1793113844"

LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_ttl_observation.log")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def check():
    headers = {"User-Agent": UA, "Range": "bytes=0-0"}
    req = urllib.request.Request(FULL_URL, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return -1, str(e)


now = datetime.datetime.now()
today = now.strftime("%Y-%m-%d")

# 幂等：当天已有记录则跳过（定时任务重跑/手跑不重复记）
if os.path.exists(LOG):
    with open(LOG, encoding="utf-8") as f:
        if today in f.read():
            print("already recorded today:", today)
            sys.exit(0)

status, err = check()
expired = status in (403, 404, 410)
detail = "HTTP %s" % status if err is None else "HTTP -1 (%s)" % err
line = "%s | %s | %s" % (now.strftime("%Y-%m-%d %H:%M:%S"), detail,
                         "EXPIRED-已过期" if expired else "VALID-仍有效")
with open(LOG, "a", encoding="utf-8") as f:
    f.write(line + "\n")
print(line)
if expired:
    print("TTL 观察完成：链接已过期。首个 403 日期见日志。")
