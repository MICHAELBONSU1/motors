import urllib.request
import re

# Try downloading a few well known pngimg ids for Mercedes
ids = [1900, 1901, 1902, 1903, 1905, 1906, 1907, 1908, 1910, 1915, 1920, 1870, 1875, 1880, 1885]
found = []

for i in ids:
    url = f"https://pngimg.com/d/mercedes_PNG{i}.png"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            if len(data) > 50000:
                found.append((i, len(data)))
                with open(f"static/uploads/mercedes_{i}.png", "wb") as f:
                    f.write(data)
                print(f"Downloaded ID {i}: {len(data)} bytes")
    except Exception as e:
        pass

print("Total downloaded:", len(found))
