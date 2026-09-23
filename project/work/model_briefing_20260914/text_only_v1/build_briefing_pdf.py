"""Render the explanatory markdown as a portable, typeset internal briefing."""
from pathlib import Path
import re
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'CZK_CPI_FORECASTING_LATEST_MODELS_2026-09-14.md'
DEST=ROOT/'output/pdf/CZK_CPI_FORECASTING_LATEST_MODELS_2026-09-14.pdf'
FONT=Path('C:/Windows/Fonts')
pdfmetrics.registerFont(TTFont('Brief',str(FONT/'segoeui.ttf')))
pdfmetrics.registerFont(TTFont('BriefBold',str(FONT/'segoeuib.ttf')))
pdfmetrics.registerFontFamily('Brief',normal='Brief',bold='BriefBold',italic='Brief',boldItalic='BriefBold')
NAVY=colors.HexColor('#193c52');TEAL=colors.HexColor('#177e89');GRAY=colors.HexColor('#52616b')
body=ParagraphStyle('body',fontName='Brief',fontSize=9.5,leading=13.1,textColor=colors.HexColor('#243642'),spaceAfter=8)
title=ParagraphStyle('title',parent=body,fontName='BriefBold',fontSize=21,leading=25,textColor=NAVY,spaceAfter=9)
head=ParagraphStyle('head',parent=body,fontName='BriefBold',fontSize=14.2,leading=18,textColor=NAVY,spaceBefore=4,spaceAfter=12,keepWithNext=True)
small=ParagraphStyle('small',parent=body,fontSize=8.1,leading=10.7,textColor=GRAY)
cell=ParagraphStyle('cell',parent=body,fontSize=8.25,leading=10.6,spaceAfter=0)
th=ParagraphStyle('th',parent=cell,fontName='BriefBold',textColor=colors.white)


def inline(text):
    # ASCII punctuation makes extraction and sharing robust across renderers.
    text=text.replace('\u2011','-').replace('\u2013','-').replace('\u2014','-').replace('\u2018',"'").replace('\u2019',"'").replace('\u201c','"').replace('\u201d','"')
    links=[]
    def save(m):
        label,url=m.group(1),m.group(2)
        if not url.startswith(('http://','https://')):
            url=(ROOT/url).resolve().as_uri()
        links.append(f'<a href="{escape(url)}" color="#177e89">{escape(label)}</a>')
        return f'LINKTOKEN{len(links)-1}END'
    text=re.sub(r'\[([^]]+)\]\(([^)]+)\)',save,text)
    text=escape(text)
    text=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'`([^`]+)`',r'<font name="Brief">\1</font>',text)
    for i,link in enumerate(links):text=text.replace(f'LINKTOKEN{i}END',link)
    return text


def make_table(lines,width):
    rows=[]
    for line in lines:
        cells=[x.strip() for x in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-+:?',x) for x in cells):continue
        rows.append(cells)
    n=len(rows[0]);assert all(len(r)==n for r in rows)
    if n==2:ratios=[.39,.61]
    elif n==3:ratios=[.21,.34,.45]
    elif n==4:ratios=[.34,.22,.22,.22]
    elif n==5:ratios=[.36,.16,.16,.16,.16]
    elif n==6:ratios=[.30,.14,.14,.14,.14,.14]
    else:ratios=[1/n]*n
    data=[[Paragraph(inline(t),th if i==0 else cell) for t in row] for i,row in enumerate(rows)]
    table=Table(data,colWidths=[width*r for r in ratios],repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#edf4f6'),colors.white]),
        ('LINEBELOW',(0,-1),(-1,-1),.5,colors.HexColor('#c8d8df'))]))
    return table


def footer(canvas,doc):
    canvas.saveState();w,h=A4
    canvas.setFillColor(GRAY);canvas.setFont('Brief',7.3)
    canvas.drawString(42,27,'Czech CPI | Independent research and historical evaluation | 14 September 2026')
    canvas.drawRightString(w-42,27,str(doc.page))
    if doc.page>1:
        canvas.setFillColor(NAVY);canvas.setFont('BriefBold',8)
        canvas.drawString(42,h-26,'CZK Cpi Forecasting - Latest models')
        canvas.setStrokeColor(TEAL);canvas.setLineWidth(.7);canvas.line(42,h-33,w-42,h-33)
    canvas.restoreState()


def main():
    DEST.parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(str(DEST),pagesize=A4,leftMargin=42,rightMargin=42,topMargin=47,bottomMargin=43,
        title='CZK Cpi Forecasting - Latest models',author='Czech CPI research',pageCompression=1)
    lines=SOURCE.read_text(encoding='utf-8').splitlines();story=[];i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line=='<!-- PAGEBREAK -->':story.append(PageBreak());i+=1;continue
        if line.startswith('# '):story.append(Paragraph(inline(line[2:]),title));i+=1;continue
        if line.startswith('## '):story.append(Paragraph(inline(line[3:]),head));i+=1;continue
        if line.startswith('|'):
            table=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                table.append(lines[i]);i+=1
            story.extend([make_table(table,doc.width),Spacer(1,10)]);continue
        block=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','<!--')):
            block.append(lines[i].strip());i+=1
        text=' '.join(block)
        style=small if text.startswith(('Source:','Evidence:','Model explanation')) else body
        story.append(Paragraph(inline(text),style))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    reader=PdfReader(DEST)
    print('PDF:',DEST,'pages:',len(reader.pages))
    for i,page in enumerate(reader.pages,1):
        text=page.extract_text();assert len(text)>350,(i,len(text))
        print(i,len(text),text[:85].replace('\n',' '))


if __name__=='__main__':main()
