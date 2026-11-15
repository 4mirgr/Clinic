from datetime import datetime
from urllib.parse import quote

from cryptography.fernet import Fernet
from django.conf import settings
from django.utils import timezone
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from requests import RequestException

SCOPES = ['https://www.googleapis.com/auth/calendar.events.owned','https://www.googleapis.com/auth/calendar.freebusy']
TOKEN_URI = 'https://oauth2.googleapis.com/token'
API_ROOT = 'https://www.googleapis.com/calendar/v3'


class CalendarUnavailable(Exception):
    def __init__(self,message='ارتباط با گوگل کامل نشد؛ نوبت تأییدشده محسوب نمی‌شود.'):
        super().__init__(message)


def configured():
    if not all(getattr(settings,key,'') for key in ['GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_TOKEN_ENCRYPTION_KEY']):
        return False
    try:
        Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode())
    except (ValueError,TypeError):
        return False
    return settings.GOOGLE_REDIRECT_URI.startswith('https://')


def timestamp(value):
    result = datetime.fromisoformat(value.replace('Z','+00:00'))
    if timezone.is_naive(result):
        raise ValueError('Timezone required')
    return result


class GoogleCalendar:
    def __init__(self,connection,session=None):
        self.connection = connection
        if session is None:
            if not configured() or not connection.active:
                raise CalendarUnavailable('تقویم گوگل متصل نیست.')
            credentials = Credentials(token=None,refresh_token=connection.get_refresh_token(),token_uri=TOKEN_URI,client_id=settings.GOOGLE_CLIENT_ID,client_secret=settings.GOOGLE_CLIENT_SECRET,scopes=SCOPES)
            session = AuthorizedSession(credentials,refresh_timeout=15)
        self.session = session
        self.events_url = f'{API_ROOT}/calendars/{quote(connection.calendar_id,safe="")}/events'

    def request(self,method,url,**kwargs):
        try:
            return self.session.request(method,url,timeout=15,**kwargs)
        except (RequestException,GoogleAuthError,ValueError):
            # Never expose OAuth response bodies, client secrets or tokens to logs/UI.
            raise CalendarUnavailable() from None

    def free_busy(self,start,end):
        response = self.request('POST',API_ROOT+'/freeBusy',json={'timeMin':start.isoformat(),'timeMax':end.isoformat(),'timeZone':'Asia/Tehran','items':[{'id':self.connection.calendar_id}]})
        if response.status_code != 200:
            raise CalendarUnavailable()
        try:
            calendar = response.json()['calendars'][self.connection.calendar_id]
            if calendar.get('errors'):
                raise ValueError()
            intervals = [(timestamp(item['start']),timestamp(item['end'])) for item in calendar['busy']]
            if any(end <= start for start,end in intervals):
                raise ValueError()
            return intervals
        except (KeyError,ValueError,TypeError,AttributeError):
            raise CalendarUnavailable() from None

    def find_event(self,appointment):
        response = self.request('GET',self.events_url+'/'+appointment.pk.hex)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise CalendarUnavailable()
        try:
            event = response.json()
            if (event.get('status') == 'cancelled' or event['id'] != appointment.pk.hex
                or event['extendedProperties']['private']['appointment_id'] != str(appointment.pk)
                or timestamp(event['start']['dateTime']) != appointment.starts_at
                or timestamp(event['end']['dateTime']) != appointment.ends_at):
                raise ValueError()
            return event
        except (KeyError,TypeError,ValueError,AttributeError):
            raise CalendarUnavailable('رویداد تقویم با این نوبت تطابق ندارد؛ بررسی لازم است.') from None

    def insert_event(self,appointment):
        payload = {'id':appointment.pk.hex,'summary':'نوبت مطب','visibility':'private','transparency':'opaque',
                   'start':{'dateTime':appointment.starts_at.isoformat(),'timeZone':'Asia/Tehran'},
                   'end':{'dateTime':appointment.ends_at.isoformat(),'timeZone':'Asia/Tehran'},
                   'extendedProperties':{'private':{'appointment_id':str(appointment.pk)}},
                   'reminders':{'useDefault':False,'overrides':[{'method':'popup','minutes':10}]}}
        response = self.request('POST',self.events_url,json=payload,params={'sendUpdates':'none'})
        if response.status_code == 409:
            event = self.find_event(appointment)
            if event:
                return event
            raise CalendarUnavailable()
        if response.status_code not in (200,201):
            raise CalendarUnavailable()
        try:
            event = response.json()
            if event['id'] != appointment.pk.hex:
                raise ValueError()
            return event
        except (KeyError,ValueError,TypeError):
            raise CalendarUnavailable() from None

    def delete_event(self,appointment):
        response = self.request('DELETE',self.events_url+'/'+appointment.pk.hex,params={'sendUpdates':'none'})
        if response.status_code not in (204,404,410):
            raise CalendarUnavailable()
