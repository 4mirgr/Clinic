"""Plain-text handout structure and language-neutral search; never render raw HTML."""
import re
import unicodedata

SPECIALTIES = [
 ('cardiology','قلب و عروق','Cardiology'), ('endocrinology','غدد و متابولیسم','Endocrinology'),
 ('gastroenterology','گوارش و کبد','Gastroenterology'), ('pulmonology','ریه','Pulmonology'),
 ('nephrology','کلیه','Nephrology'), ('hematology','خون','Hematology'),
 ('rheumatology','روماتولوژی','Rheumatology'), ('infectious','بیماری‌های عفونی','Infectious diseases'),
 ('allergy','آلرژی و ایمنی','Allergy immunology'), ('oncology','سرطان و مراقبت حمایتی','Oncology'),
 ('geriatrics','طب سالمندی','Geriatrics'), ('sleep','طب خواب','Sleep medicine'),
]
CHOICES = [(key, fa) for key,fa,en in SPECIALTIES]


def normalize_search(value):
    value = unicodedata.normalize('NFKC', str(value)).casefold().translate(str.maketrans('يك٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', 'یک01234567890123456789'))
    value = ''.join(c for c in value if unicodedata.category(c) != 'Mn' and c != 'ـ')
    return re.sub(r'\s+', ' ', value.replace('\u200c',' ').replace('\u200f',' ')).strip()


def search_document(advice):
    specialty = next((' '.join(row) for row in SPECIALTIES if row[0] == advice.specialty), advice.specialty)
    return normalize_search(' '.join([advice.title, advice.title_en, advice.tags, advice.body, specialty]))


def sections(body):
    result=[]
    current={'heading':'', 'items':[]}
    for raw in body.splitlines():
        line=raw.strip()
        if not line:
            continue
        if line.startswith('## '):
            if current['items'] or current['heading']:
                result.append(current)
            current={'heading':line[3:].strip(), 'items':[]}
        else:
            current['items'].append(line[2:] if line.startswith('- ') else line)
    if current['items'] or current['heading']:
        result.append(current)
    return result
