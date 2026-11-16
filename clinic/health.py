from django.db import DatabaseError, connection
from django.http import HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """Upstream hosting probe only; never a claim of completed clinical setup."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        response=HttpResponse('ok',content_type='text/plain')
    except DatabaseError:
        response=HttpResponse('unavailable',status=503,content_type='text/plain')
    response['Cache-Control']='no-store'
    response['X-Robots-Tag']='noindex,nofollow'
    return response
