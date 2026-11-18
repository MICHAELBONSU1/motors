import urllib.request
import re

url = "https://purepng.com/search?q=mercedes+amg+gt"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
try:
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        hrefs = [h for h in re.findall(r'href="([^"]+)"', html) if 'mercedes' in h.lower()]
        imgs = [i for i in re.findall(r'src="([^"]+)"', html) if 'mercedes' in i.lower() or 'upload' in i.lower()]
        print("Hrefs:", hrefs[:10])
        print("Imgs:", imgs[:10])
except Exception as e:
    print("Error:", e)
