from pathlib import Path

base_path = Path("./templates/base_html.html")
base_fn = lambda body, sign: f"{base_path.read_text(encoding='utf-8')}"

body_path = Path("./templates/body_html.html")
body_fn = f"{body_path.read_text(encoding='utf-8')}"

sign_path = Path("./templates/sign_html.html")
sign_fn = lambda images: f"{sign_path.read_text(encoding='utf-8')}"

body = body_fn(body_images)
sign = sign_fn(sign_images)
base = base_fn(body, sign)