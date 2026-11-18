import urllib.request
import re

url = "https://pngimg.com/uploads/mercedes/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})

try:
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        pngs = re.findall(r'href="([^"]+mercedes_PNG\d+\.png)"', html)
        if not pngs:
            pngs = re.findall(r'src="([^"]+mercedes_PNG\d+\.png)"', html)
        print("Found PNGs:", len(pngs))
        for p in pngs[:10]:
            print(p)
except Exception as e:
    print("Error:", e)
