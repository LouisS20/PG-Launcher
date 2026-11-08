from PIL import Image, ImageDraw, ImageFont

def make_green_glitch_logo():
    # Dimension haute résolution
    size = (512, 512)
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Fond sombre (#1b2838) avec bordure bleu/vert (#00ff88)
    draw.rounded_rectangle([16, 16, 496, 496], radius=80, fill='#1b2838', outline='#00ff88', width=16)

    # 2. Fonte
    font_size = 220
    try:
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    text = "CI"

    # Centrage du texte
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (512 - text_width) / 2
    y = (512 - text_height) / 2 - 25

    # 3. Layer Glitch Vert Néon (décalé à gauche)
    draw.text((x - 12, y), text, fill='#00ff88', font=font)

    # 4. Layer Glitch Cyan (décalé à droite)
    draw.text((x + 12, y), text, fill='#00e5ff', font=font)

    # 5. Texte Principal (#66c0f4)
    draw.text((x, y), text, fill='#66c0f4', font=font)

    # 6. Coupures horizontales Style Glitch
    draw.rectangle([30, 160, 480, 180], fill='#1b2838')
    draw.text((x - 18, y), text, fill='#00ff88', font=font)
    
    draw.rectangle([30, 330, 480, 345], fill='#1b2838')
    draw.text((x + 18, y), text, fill='#00e5ff', font=font)

    # Masque pour bordures arrondies propres
    final_img = Image.new('RGBA', size, (0,0,0,0))
    mask = Image.new('L', size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([16, 16, 496, 496], radius=80, fill=255)
    
    final_img.paste(img, (0, 0), mask)

    # Sauvegarde
    final_img.save('icon.ico', format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("✓ Icône avec glitch vert générée sous 'icon.ico' !")

if __name__ == '__main__':
    make_green_glitch_logo()