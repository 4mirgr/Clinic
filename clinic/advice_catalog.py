import json
import uuid
from pathlib import Path
from .advice_text import normalize_search
from .models import Advice


def load_defaults(actor):
    data=json.loads((Path(__file__).parent/'data/advice_defaults.json').read_text())
    count=0
    for item in data['handouts']:
        body='\n\n'.join('## '+s['heading']+'\n'+'\n'.join('- '+x for x in s['items']) for s in item['sections'])
        source='\n'.join([item['publisher'], item['source'], *item.get('extra_sources',[]), 'دریافت منابع: '+data['retrieved_on']+' | متن فارسی تألیفی؛ نیازمند بازبینی پزشک'])
        _,created=Advice.objects.get_or_create(catalog_key=item['key'], defaults={
            'id':uuid.uuid5(uuid.NAMESPACE_URL,'https://drgerami-md.ir/clinic/advice/'+item['key']),
            'title':item['title'],'title_en':item['title_en'],'specialty':item['specialty'],
            'tags':'، '.join(item['tags']),'body':body,'source':source,'updated_by':actor,
            'source_metadata':{'publisher':item['publisher'],'url':item['source'],'retrieved_on':data['retrieved_on'],'catalog_revision':data['schema_version']},
        })
        count+=created
    return count


def search_advice(query='', specialty=''):
    records=Advice.objects.all()
    if specialty:
        records=records.filter(specialty=specialty)
    for token in normalize_search(query[:200]).split():
        records=records.filter(search_text__contains=token)
    return records
