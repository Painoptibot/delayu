"""Sync home_dashboard.html content block from Materio index.html (structure source of truth)."""
import re
from pathlib import Path

MATERIO = Path(
    r"D:\Materialize 13.11.1 – Next.js, Vuejs, Nuxt, HTML, Laravel, Django, Asp.Net Material Design Admin Template"
    r"\html-version\full-version\html\vertical-menu-template\index.html"
)
TEMPLATE = Path(__file__).resolve().parents[1] / "delayu" / "templates" / "platform" / "home_dashboard.html"

materio = MATERIO.read_text(encoding="utf-8")
m = re.search(
    r'<div class="container-xxl flex-grow-1 container-p-y">\s*(.*?)\s*</div>\s*<!-- / Content -->',
    materio,
    re.S,
)
if not m:
    raise SystemExit("Materio content block not found")
content = m.group(1).strip()

# Materio → Django static paths
content = content.replace("../../assets/", "{% static '")
content = re.sub(
    r"{% static '([^']+)'\}",
    lambda mm: "{% static '" + mm.group(1).replace("{% static '", "") + "' %}",
    content,
)
# fix double conversion - simpler approach:
content = m.group(1).strip()
content = re.sub(r'\.\./\.\./assets/([^"\']+)', r"{% static '\1' %}", content)

# Theme-aware john illustration (match existing django template)
content = re.sub(
    r'<img\s+src="\{% static \'img/illustrations/illustration-john-light\.png\' %\}"\s+height="186"\s+class="scaleX-n1-rtl"\s+alt="View Profile"\s+data-app-light-img="illustrations/illustration-john-light\.png"\s+data-app-dark-img="illustrations/illustration-john-dark\.png"\s*/>',
    '<img src="{% static \'img/illustrations/illustration-john-\' %}{{ COOKIES.theme|default:theme }}.png" height="186" class="scaleX-n1-rtl" alt="View Profile" data-app-light-img="illustrations/illustration-john-light.png" data-app-dark-img="illustrations/illustration-john-dark.png" />',
    content,
    flags=re.S,
)

# CEO line uses django theme variable
content = re.sub(
    r"<small>CEO of [^<]+</small>",
    "<small>CEO of {% get_theme_variables 'creator_name' %}</small>",
    content,
)

# Materio index.html: content inside container-xxl starts at 14 spaces
MATERIO_BASE = 14
dedented = []
for line in content.splitlines():
    if not line.strip():
        dedented.append("")
        continue
    cur = len(line) - len(line.lstrip())
    dedented.append(line[min(cur, MATERIO_BASE) :])
content = "\n".join(dedented)

header = """{% extends layout_path %}

{% load static %}
{% load i18n %}

{% block title %}Dashboard - Analytics{% endblock title %}

{% block vendor_css %}
{{ block.super }}
<link rel="stylesheet" href="{% static 'vendor/libs/apex-charts/apex-charts.css' %}" />
<link rel="stylesheet" href="{% static 'vendor/libs/swiper/swiper.css' %}" />
{% endblock vendor_css %}

{% block vendor_js %}
{{ block.super }}
<script src="{% static 'vendor/libs/apex-charts/apexcharts.js' %}"></script>
<script src="{% static 'vendor/libs/swiper/swiper.js' %}"></script>
{% endblock vendor_js %}

{% block page_css %}
{{ block.super }}
<link rel="stylesheet" href="{% static 'vendor/css/pages/cards-statistics.css' %}" />
{% endblock page_css %}

{% block page_js %}
{{ block.super }}
<script src="{% static 'js/dashboards-analytics.js' %}"></script>
{% endblock page_js %}

{% block content %}
"""

footer = "\n{% endblock %}\n"

TEMPLATE.write_text(header + content + footer, encoding="utf-8")
print("synced", TEMPLATE.stat().st_size)
