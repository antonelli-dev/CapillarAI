#!/usr/bin/env python3
"""Manual test for donor analysis."""
import json
import urllib.request
import urllib.error
import io
from PIL import Image

BASE_URL = 'http://localhost:8013'

def main():
    print("Testing donor analysis with 3 zones...")
    
    # Create 3 test images
    imgs = {}
    for name, color in [('coronilla', 'red'), ('left', 'blue'), ('right', 'green')]:
        img = Image.new('RGB', (100, 100), color=color)
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        imgs[name] = img_bytes.getvalue()
    
    # Build multipart form
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = io.BytesIO()
    
    files = [
        ('coronilla_image', 'coronilla.png', imgs['coronilla']),
        ('left_temporal_image', 'left.png', imgs['left']),
        ('right_temporal_image', 'right.png', imgs['right']),
    ]
    
    for field, filename, content in files:
        body.write(f'--{boundary}\r\n'.encode())
        body.write(f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode())
        body.write(f'Content-Type: image/png\r\n\r\n'.encode())
        body.write(content)
        body.write(b'\r\n')
    
    body.write(f'--{boundary}--\r\n'.encode())
    
    url = f'{BASE_URL}/v1/donor-analysis?recipient_area_cm2=50'
    req = urllib.request.Request(url, data=body.getvalue())
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
    
    print(f'URL: {url}')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            print(f'Status: 200')
            print(f'Zones analyzed: {data.get("zones_analyzed")}')
            print(f'Total grafts: {data.get("estimated_grafts")}')
            print(f'Recommendation: {data.get("recommendation")}')
            if data.get("zone_breakdown"):
                print(f'Breakdown: {len(data["zone_breakdown"])} zones')
                for zone in data["zone_breakdown"]:
                    print(f'  - {zone["zone_name"]}: {zone["estimated_grafts"]} grafts')
            print('\n[PASS] SUCCESS')
            return 0
    except urllib.error.HTTPError as e:
        print(f'HTTP Error: {e.code}')
        print(f'Response: {e.read().decode()[:500]}')
        return 1
    except Exception as e:
        print(f'Error: {str(e)}')
        return 1

if __name__ == '__main__':
    exit(main())
