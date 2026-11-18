from PIL import Image

def analyze_cutout(filename):
    im = Image.open('static/uploads/' + filename).convert('RGBA')
    # Check edges
    alpha = im.split()[-1]
    # Check corner pixels
    corners = [
        alpha.getpixel((0, 0)),
        alpha.getpixel((im.width-1, 0)),
        alpha.getpixel((0, im.height-1)),
        alpha.getpixel((im.width-1, im.height-1))
    ]
    print(filename, "size:", im.size, "corners alpha:", corners)

analyze_cutout('benz_1907.png')
analyze_cutout('benz_1870.png')
analyze_cutout('mercedes_benz_hero.png')
