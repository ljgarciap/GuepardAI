
import os
from jinja2 import Template

# Mock Slide Data (Walmart Case Study from previous screenshots)
slide_data = {
    "title": "Global Case Study: Walmart (US) – Loyalty as a Growth Engine",
    "section_label": "Financial Impact",
    "primary_image": "https://images.unsplash.com/photo-1534452286302-5f56ee13b2c3?q=80&w=2070", # Retail context
    "agency_logo": "../../assets/agency/L-founders_logo.png",
    "primary_color": "#002D62", # Tesco Navy
    "secondary_color": "#E31837", # Tesco Red
    "bullets": [
        "Membership ecosystem as the cornerstone of digital transformation.",
        "Data engagement at scale driving higher purchase frequency.",
        "Strategic alignment with long-term commercial goals."
    ],
    "metrics": [
        {"label": "Membership Growth", "value": "32M", "growth": "+20% YoY"},
        {"label": "Incremental Revenue", "value": "3%", "growth": "Loyalty-Driven"},
        {"label": "Retail Media Revenue", "value": "$4B+", "growth": "+50% YoY"}
    ]
}

def render_poc():
    template_path = "templates/artistic_v1.html"
    output_path = "outputs/poc_html/walmart_slide.html"
    
    with open(template_path, "r") as f:
        template_str = f.read()
    
    template = Template(template_str)
    rendered_html = template.render(**slide_data)
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(rendered_html)
    
    print(f"✔ PoC Rendered: {output_path}")

if __name__ == "__main__":
    render_poc()
