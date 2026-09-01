"""Convert docs/showcase_hld_flowchart.pdf -> PNG at 2x scale."""
import pymupdf

SRC = "docs/showcase_hld_flowchart.pdf"
OUT = "docs/showcase_hld_flowchart.png"

doc = pymupdf.open(SRC)
page = doc[0]
pix = page.get_pixmap(dpi=200)
pix.save(OUT)
print(OUT, pix.width, "x", pix.height)
