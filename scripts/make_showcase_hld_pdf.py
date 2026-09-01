"""Showcase HLD v2: PulseGrid -> LogPulse -> TracePulse (polished one-page PDF)."""
import math
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(A4)
OUT = "docs/showcase_hld_flowchart.pdf"

# palette
BG = (0.965, 0.965, 0.97)
HEADER_BG = (0.09, 0.11, 0.18)
INK = (0.10, 0.10, 0.14)
MUTED = (0.42, 0.44, 0.50)

CARDS = [
    dict(
        title="PULSEGRID", tag="DETECT", color=(0.16, 0.42, 0.85), light=(0.90, 0.94, 1.0),
        subtitle="Observability & alerting layer",
        feats=["Alertmanager alerts", "CRM <-> ERP reconciliation\nmismatch detection", "Newman API-test failures"],
    ),
    dict(
        title="LOGPULSE", tag="CLASSIFY", color=(0.88, 0.52, 0.10), light=(1.0, 0.95, 0.86),
        subtitle="AI log classification service",
        feats=["Reads raw log / alert text", "Predicts issue category", "Confidence score per triage"],
    ),
    dict(
        title="TRACEPULSE", tag="MANAGE", color=(0.12, 0.60, 0.32), light=(0.88, 0.98, 0.91),
        subtitle="AI incident management",
        feats=["AI Root-Cause Analysis (LLM)", "Similar-incident vector search", "SLA clocks + auto-escalation",
               "Engineer assignment + Slack alert"],
    ),
]


def arrow(c, x1, y1, x2, y2, color=INK):
    c.setStrokeColorRGB(*color)
    c.setFillColorRGB(*color)
    c.setLineWidth(3)
    c.line(x1, y1, x2, y2)
    ang = math.atan2(y2 - y1, x2 - x1)
    L = 12
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - L * math.cos(ang - 0.42), y2 - L * math.sin(ang - 0.42))
    p.lineTo(x2 - L * math.cos(ang + 0.42), y2 - L * math.sin(ang + 0.42))
    p.close()
    c.drawPath(p, stroke=0, fill=1)


def draw_card(c, x, y, w, h, card, step_no):
    color, light = card["color"], card["light"]
    # shadow
    c.setFillColorRGB(0.0, 0.0, 0.0)
    c.setFillAlpha(0.10)
    c.roundRect(x + 4, y - 6, w, h, 14, stroke=0, fill=1)
    c.setFillAlpha(1)
    # body
    c.setFillColorRGB(*light)
    c.setStrokeColorRGB(*color)
    c.setLineWidth(1.5)
    c.roundRect(x, y, w, h, 14, stroke=1, fill=1)
    # header band
    c.setFillColorRGB(*color)
    c.roundRect(x, y + h - 52, w, 52, 14, stroke=0, fill=1)
    c.rect(x, y + h - 52, w, 20, stroke=0, fill=1)
    # step badge
    c.setFillColorRGB(1, 1, 1)
    c.circle(x + 28, y + h - 26, 14, stroke=0, fill=1)
    c.setFillColorRGB(*color)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(x + 28, y + h - 31, str(step_no))
    # title
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(x + 50, y + h - 32, card["title"])
    # tag pill
    c.setFont("Helvetica-Bold", 8.5)
    tag = card["tag"]
    tw = c.stringWidth(tag, "Helvetica-Bold", 8.5) + 10
    c.setFillColorRGB(1, 1, 1)
    c.roundRect(x + w - tw - 12, y + h - 36, tw, 17, 8, stroke=0, fill=1)
    c.setFillColorRGB(*color)
    c.drawCentredString(x + w - 12 - tw / 2, y + h - 31.5, tag)
    # subtitle
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica-Oblique", 9.5)
    c.drawCentredString(x + w / 2, y + h - 70, card["subtitle"])
    # features
    ty = y + h - 95
    for f in card["feats"]:
        for i, ln in enumerate(f.split("\n")):
            if i == 0:
                c.setFillColorRGB(*color)
                c.setFont("Helvetica-Bold", 10.5)
                c.drawString(x + 20, ty, "•")
            c.setFillColorRGB(*INK)
            c.setFont("Helvetica", 10.5)
            c.drawString(x + 32, ty, ln)
            ty -= 14.5
        ty -= 2


c = canvas.Canvas(OUT, pagesize=landscape(A4))
c.setTitle("AI Incident Pipeline - PulseGrid to LogPulse to TracePulse")

# background
c.setFillColorRGB(*BG)
c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

# header band
c.setFillColorRGB(*HEADER_BG)
c.rect(0, PAGE_H - 100, PAGE_W, 100, stroke=0, fill=1)
c.setFillColorRGB(1, 1, 1)
c.setFont("Helvetica-Bold", 23)
c.drawCentredString(PAGE_W / 2, PAGE_H - 48, "AI Incident Pipeline - from Alert to Resolution")
c.setFillColorRGB(0.72, 0.76, 0.85)
c.setFont("Helvetica", 12.5)
c.drawCentredString(PAGE_W / 2, PAGE_H - 72,
                    "Three integrated services:  PulseGrid detects  ->  LogPulse classifies  ->  TracePulse manages & resolves")

# cards
CW, CH = 320, 260
GAP = 120
total = 3 * CW + 2 * GAP
x0 = (PAGE_W - total) / 2
CY = PAGE_H / 2 - CH / 2 - 45
xs = [x0 + i * (CW + GAP) for i in range(3)]
for i, (card, x) in enumerate(zip(CARDS, xs)):
    draw_card(c, x, CY, CW, CH, card, i + 1)

# arrows between cards
for i in range(2):
    ay = CY + CH / 2
    arrow(c, xs[i] + CW + 12, ay, xs[i + 1] - 12, ay)
    labels = ["alert / log text", "category + confidence"]
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawCentredString((xs[i] + CW + xs[i + 1]) / 2, ay + 10, labels[i])

# learning loop
loop_y = CY - 55
lx1, lx2 = xs[0] + CW / 2, xs[2] + CW / 2
c.setStrokeColorRGB(0.55, 0.58, 0.65)
c.setLineWidth(2)
c.setDash(5, 5)
c.line(lx2, CY - 8, lx2, loop_y)
c.line(lx2, loop_y, lx1, loop_y)
c.setDash()
arrow(c, lx1, loop_y, lx1, CY - 8, color=(0.55, 0.58, 0.65))
# loop label pill
c.setFillColorRGB(1, 1, 1)
c.setStrokeColorRGB(0.75, 0.77, 0.82)
c.setLineWidth(1)
label = "Learning loop - engineer resolutions are stored and improve future RCA & similarity matches"
lw = c.stringWidth(label, "Helvetica-Oblique", 10) + 24
c.roundRect(PAGE_W / 2 - lw / 2, loop_y - 12, lw, 24, 12, stroke=1, fill=1)
c.setFillColorRGB(*MUTED)
c.setFont("Helvetica-Oblique", 10)
c.drawCentredString(PAGE_W / 2, loop_y - 4, label)

# outcome strip at bottom
sy = 42
c.setFillColorRGB(*HEADER_BG)
c.roundRect(x0, sy, total, 30, 8, stroke=0, fill=1)
c.setFillColorRGB(1, 1, 1)
c.setFont("Helvetica-Bold", 11)
c.drawCentredString(PAGE_W / 2, sy + 10,
                    "OUTCOME:  every incident auto-diagnosed, matched with history, SLA-tracked, routed to the right engineer")

c.save()
print(OUT)
